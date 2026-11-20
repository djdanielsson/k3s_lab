# Trident

Self-hosted slicer with a web UI, built on OrcaSlicer's engine (AGPL-3.0):
<https://trident.tail7f3c08.ts.net>.

Unlike Kiri:Moto, slicing happens **in the pod**, not in the browser, so this
has real resource requests and needs storage for models, output and OrcaSlicer's
data directory.

## Layout

- One PVC (`trident-data`, 20Gi `local-path`) mounted three times via
  `subPath`: `/data/models`, `/data/output`, `/data/orcaslicer-datadir`.
- One container, `mugenoesis/trident:0.9.0`, port 8000, single-user mode.
- `tailscale-ingress.yaml` — tailnet-only ingress, also registers the app on
  Homepage.

## Printer wiring (not in Git)

Printer definitions, saved materials and settings profiles live in the PVC, so
they are **not** captured by these manifests and do not survive a PVC wipe.
They were created through the HTTP API, and can be recreated the same way:

1. `POST /auth/setup {"mode":"single"}` — first-run mode. Skipping this leaves
   the UI in its setup flow.
2. `POST /printers/klipper-import {"print_host":"http://192.168.2.105:7125"}` —
   read-only import from Moonraker. Note the **required scheme**: an address
   without `http://` is rejected with a 502 "missing an 'http://' or 'https://'
   protocol". It returns the bed size, nozzle, max speed/accel, retraction,
   `START_PRINT`/`END_PRINT` macros and a `findings` list naming the klipper.cfg
   key behind each value.
3. `POST /printers` with the imported values plus
   `machine_profile`/`process_profile`/`filament_profiles` names from
   `GET /profiles`.

The saved printer for the lab is a Sovol SV08 at `192.168.2.105:7125` (Moonraker
on a separate `192.168.2.0/24` segment, reached through the tailnet subnet route
advertised by `truenas-scale`).

## Reaching the printer

The printer is on `192.168.2.0/24`, which is not routed from the lab LAN. Reach
it only because `truenas-scale` advertises that subnet on the tailnet and the
k3s node has `--accept-routes` enabled (routes land in table 52). If the printer
becomes unreachable, check those two things before touching this app — the
`/printers/{id}/status` endpoint is the quickest probe (it reads Moonraker
server-side).

Moonraker is reachable without an API key from here because the userspace
subnet router re-dials from its own `192.168.2.x` address, which Moonraker
already trusts.

## Verified

- `POST /sample-models/calibration-cube/load` → `POST /jobs` → `succeeded`
  ("All done, Success") in ~5s.
- `POST /printers/{id}/send/{job_id} {"start_print": false}` → `200 {"ok":true}`,
  and the sliced 2.1MB `plate_1.gcode` appeared in Moonraker's
  `/server/files/list?root=gcodes`. Test file deleted afterwards.
