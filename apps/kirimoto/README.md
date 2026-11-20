# Kiri:Moto

Browser-based slicer for 3D printers (FDM/SLA), CNC mills and laser cutters:
<https://kirimoto.tail7f3c08.ts.net/kiri/>.

Everything that matters runs **client-side** — the pod only serves the static
app bundle, so there is no storage, no GPU and no session state in the cluster.
The build is upstream `GridSpace/grid-apps` `src/dock/Dockerfile`, unmodified,
built in-cluster by Kaniko and pushed to `registry.registry.svc:5000/kirimoto`.

## Layout

- `image/build-in-cluster.py` — Kaniko job that builds the upstream image.
- `deployment.yaml` — two containers: upstream app server on 8080, and an
  `nginx:alpine` sidecar on 8081 that redirects `/` to `/kiri/`. The upstream
  server answers **404 at `/`** and serves the app only at `/kiri/`, so the
  service targets the sidecar and a bare hostname link works.
- `tailscale-ingress.yaml` — tailnet-only ingress; also registers the app on
  Homepage.

## Rebuilding after upstream changes

```
python3 image/build-in-cluster.py refs/heads/master 0.1.1
```

then bump `image:` in `deployment.yaml`. Builds take ~2–3 minutes and are
cached in `registry/kirimoto-cache`.
