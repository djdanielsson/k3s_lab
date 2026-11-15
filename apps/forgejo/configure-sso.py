"""Configure Forgejo using its native CLI inside a Kubernetes Job."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def main():
    issuer = "https://sso.tail7f3c08.ts.net/realms/lab"
    with urllib.request.urlopen(issuer + "/.well-known/openid-configuration", timeout=20) as response:
        if json.load(response).get("issuer") != issuer:
            raise RuntimeError("Unexpected SSO issuer")
    secret = Path("/credentials/client-secret").read_text()
    if not secret:
        raise RuntimeError("Missing OIDC credential")
    cli = ["/tools/gitea", "--work-path", "/var/lib/gitea", "--config",
           "/var/lib/gitea/custom/conf/app.ini", "admin", "auth"]
    for attempt in range(24):
        result = subprocess.run(cli + ["list"], capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError("Forgejo database/config is not ready")
    ids = [parts[0] for line in result.stdout.splitlines()
           if len(parts := line.split()) >= 2 and parts[1] == "lab-sso"]
    if len(ids) > 1:
        raise RuntimeError("Ambiguous Forgejo SSO source")
    operation = ["update-oauth", "--id", ids[0]] if ids else ["add-oauth"]
    arguments = ["--name", "lab-sso", "--provider", "openidConnect", "--key", "forgejo",
                 "--secret", secret, "--auto-discover-url", issuer + "/.well-known/openid-configuration",
                 "--scopes", "openid", "--scopes", "profile", "--scopes", "email",
                 "--group-claim-name", "groups", "--admin-group", "lab-admins"]
    result = subprocess.run(cli + operation + arguments, capture_output=True, timeout=60)
    if result.returncode:
        # CLI stderr and argv can contain client credentials; never print them.
        raise RuntimeError("Forgejo OIDC source configuration failed")
    print("Forgejo lab-sso OIDC source reconciled.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Forgejo SSO reconciliation failed; check issuer, database, config and mounted credentials", file=sys.stderr)
        sys.exit(1)
