"""NetMap - tiny nmap LAN scanner with a web UI.

Sweeps a subnet for hosts (ARP/ping) via nmap, stores results in SQLite, and
serves a small web page. Running in the k8s host network namespace so nmap can
reach the LAN.
"""
import json
import os
import sqlite3
import subprocess
import threading
import time

SUBNET = os.environ.get("SCAN_SUBNET", "192.168.1.0/24")
INTERVAL = int(os.environ.get("SCAN_INTERVAL", "900"))
DB = os.environ.get("DB_PATH", "/data/netmap.db")

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


def dbconn():
    c = sqlite3.connect(DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS hosts("
        "ip TEXT PRIMARY KEY, mac TEXT, hostname TEXT, vendor TEXT, status TEXT, "
        "first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS service_ports("
        "ip TEXT, port INT, proto TEXT, name TEXT, service TEXT, PRIMARY KEY(ip,port))"
    )
    return c


def run_nmap(args):
    out = ""
    try:
        res = subprocess.run(["nmap"] + args, capture_output=True, text=True, timeout=900)
        out = res.stdout
    except Exception as e:  # noqa: BLE001
        print("nmap error:", e)
    return out


def parse_hosts(out):
    hosts = []
    try:
        data = json.loads(out)
    except Exception:  # noqa: BLE001
        return hosts
    for h in (data.get("nmaprun") or {}).get("host") or []:
        addrs = h.get("address") or []
        ip = next((a.get("addr") for a in addrs if a.get("addrtype") == "ipv4"), None)
        if not ip:
            continue
        macs = [a for a in addrs if a.get("addrtype") == "mac"]
        hostname = ""
        for hn in (h.get("hostnames") or {}).get("hostname") or []:
            hostname = hn.get("name", "")
            break
        hosts.append(
            {
                "ip": ip,
                "mac": macs[0].get("addr") if macs else None,
                "vendor": macs[0].get("vendor") if macs else None,
                "hostname": hostname,
                "status": (h.get("status") or {}).get("state", "unknown"),
            }
        )
    return hosts


def scan_sweep():
    out = run_nmap(["-sn", "-n", SUBNET, "-oJ", "-"])
    hosts = parse_hosts(out)
    c = dbconn()
    for h in hosts:
        c.execute(
            "INSERT INTO hosts(ip,mac,hostname,vendor,status,last_seen) "
            "VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(ip) DO UPDATE SET mac=excluded.mac, hostname=excluded.hostname, "
            "vendor=excluded.vendor, status=excluded.status, last_seen=CURRENT_TIMESTAMP",
            (h["ip"], h["mac"], h["hostname"], h["vendor"], h["status"]),
        )
    c.commit()
    c.close()
    return len(hosts)


def scan_ports(ip):
    out = run_nmap(["-sV", "-p", "1-1000", "-n", ip, "-oJ", "-"])
    ports = []
    try:
        data = json.loads(out)
    except Exception:  # noqa: BLE001
        return ports
    for h in (data.get("nmaprun") or {}).get("host") or []:
        for port in ((h.get("ports") or {}).get("port") or []):
            if (port.get("state") or {}).get("state") == "open":
                svc = port.get("service") or {}
                ports.append(
                    {
                        "port": port.get("portid"),
                        "proto": port.get("protocol"),
                        "name": svc.get("name"),
                        "service": svc.get("product", ""),
                    }
                )
    c = dbconn()
    c.execute("DELETE FROM service_ports WHERE ip=?", (ip,))
    for p in ports:
        c.execute(
            "INSERT OR REPLACE INTO service_ports VALUES(?,?,?,?,?)",
            (ip, p["port"], p["proto"] or "tcp", p["name"], p["service"]),
        )
    c.commit()
    c.close()
    return ports


def scanner_loop():
    while True:
        try:
            scan_sweep()
        except Exception as e:  # noqa: BLE001
            print("loop error:", e)
        time.sleep(INTERVAL)


@app.get("/", response_class=HTMLResponse)
def index():
    c = dbconn()
    rows = c.execute("SELECT * FROM hosts ORDER BY ip").fetchall()
    c.close()
    table = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1] or ''}</td><td>{r[2] or ''}</td>"
        f"<td>{r[3] or ''}</td><td>{r[4]}</td><td>{r[6]}</td>"
        f"<td><a href='/host/{r[0]}'>ports</a></td></tr>"
        for r in rows
    )
    return f"""<!doctype html><html><head><meta charset=utf-8><title>NetMap</title>
<style>body{{font-family:sans-serif;margin:2rem}}a{{color:#06c}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px;text-align:left}}th{{background:#eee}}</style></head><body>
<h1>NetMap — LAN hosts <small>({SUBNET})</small></h1>
<p><a href='/scan'>Scan now</a> &nbsp; <a href='/api/json'>JSON</a></p>
<table><tr><th>IP</th><th>MAC</th><th>Hostname</th><th>Vendor</th><th>Status</th><th>Last seen</th><th></th></tr>{table}</table>
</body></html>"""


@app.get("/scan", response_class=HTMLResponse)
def scan_now():
    n = scan_sweep()
    return HTMLResponse(f"<p>Scan done: {n} hosts found. <a href='/'>back</a></p>")


@app.get("/api/json")
def api_json():
    c = dbconn()
    rows = c.execute(
        "SELECT ip,mac,hostname,vendor,status,last_seen FROM hosts ORDER BY ip"
    ).fetchall()
    c.close()
    return [
        {"ip": r[0], "mac": r[1], "hostname": r[2], "vendor": r[3], "status": r[4], "last_seen": r[5]}
        for r in rows
    ]


@app.get("/host/{ip}", response_class=HTMLResponse)
def host_page(ip: str):
    c = dbconn()
    rows = c.execute(
        "SELECT port,proto,name,service FROM service_ports WHERE ip=? ORDER BY port", (ip,)
    ).fetchall()
    c.close()
    tr = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>" for r in rows
    ) or "<tr><td colspan=4>no port data yet</td></tr>"
    return f"""<!doctype html><html><body>
<h1>{ip}</h1>
<p><a href='/portscan/{ip}'>Run port scan (ports 1-1000)</a> &nbsp; <a href='/'>back</a></p>
<table><tr><th>Port</th><th>Proto</th><th>Name</th><th>Service</th></tr>{tr}</table>
</body></html>"""


@app.get("/portscan/{ip}", response_class=HTMLResponse)
def portscan(ip: str):
    threading.Thread(target=scan_ports, args=(ip,), daemon=True).start()
    return HTMLResponse(f"<p>Port scan started for {ip}. <a href='/host/{ip}'>back</a></p>")


threading.Thread(target=scanner_loop, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
