# k3s_lab — GitOps for the k3s homelab cluster

GitOps source for `*.k3s.lab.danielsson.us.com` (single-node k3s on
`agent47.lab.danielsson.us.com`). ArgoCD is the engine: installing it is a
**single command**, and ArgoCD then syncs every app below from this repo.

## Install / bootstrap

```console
kubectl apply -k .
```

That single `apply`:
1. Installs **ArgoCD** (namespace `argocd`).
2. Creates the ArgoCD **AppProject** (`k3s-lab`) and the **Applications**.
3. ArgoCD then reconciles each app from this repository (self-healing /
   auto-prune).

ArgoCD admin password (auto-generated):

```console
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
```

## Developer setup (pre-commit)

```console
brew install pre-commit        # or: uv tool install pre-commit
pre-commit install             # one-time per clone
```

Every commit is scanned by **gitleaks** (blocks hardcoded secrets) and the
standard hooks (trailing whitespace, EOF, YAML, merge-conflict, private keys).

## Secrets

All app secrets live in **Vaultwarden** (synced by External Secrets Operator).
See **[SECRETS.md](SECRETS.md)** for the `k3s/` item names/inputs to create and
the Vaultwarden API credential setup.

## Layout

| Path                  | Purpose                                                    |
|-----------------------|------------------------------------------------------------|
| `infra/argocd`        | ArgoCD install + its Traefik IngressRoute                  |
| `infra/argocd-apps`   | AppProject + ArgoCD `Application` resources (incl. Radar via Helm) |
| `apps/registry`       | Container registry (deploy/svc/**50Gi** PVC, NodePort 30500)|
| `apps/pantrywise`     | PantryWise (server/web + postgres + redis)                 |
| `apps/rustfs`         | RustFS S3 object storage (deploy/10Gi PVC/console)         |
| `apps/cert-manager`   | **Let's Encrypt ClusterIssuer — DISABLED** (commented)     |
| `apps/ingress`        | **All apps' Traefik IngressRoutes — DISABLED** (commented) |
| `apps/hermes`         | Hermes Agent gateway (official `nousresearch/hermes-agent` image) |

## Running apps (ArgoCD)

| App        | Image / source           | In-cluster endpoint                |
|------------|--------------------------|------------------------------------|
| registry   | `registry:2`             | `registry.registry.svc:5000`       |
| pantrywise | registry images (server+web) | `pantrywise-web.pantrywise.svc` |
| rustfs     | `rustfs/rustfs` (Helm-less) | `rustfs.rustfs.svc:9000/:9001`  |
| radar      | Helm chart `skyhook/radar` | `radar.radar.svc:9280`           |
| cert-manager | Helm chart `jetstack/cert-manager` v1.15.3 | issuer CRDs, controllers |
| glance       | `glanceapp/glance` | `glance.glance.svc:8080` (NodePort 31080)      |
| netalertx    | `netalertx/netalertx` | `netalertx.netalertx.svc:20211` (hostNetwork) |
| netdata      | `netdata/netdata` | `netdata.netdata.svc:19999` (hostNetwork)      |
| hermes       | `nousresearch/hermes-agent` | `hermes.hermes.svc:8642/:9119` (+ Tailscale) |

Radar's chart creates a **ClusterRole** to read the cluster; the AppProject
whitelists `ClusterRole`/`ClusterRoleBinding` for that. Cert-manager is pinned
to **v1.15.3** (newer needs Kubernetes ≥1.30; this is k3s 1.26) and its **CRDs
are applied out-of-band** (ArgoCD's chart render doesn't manage them reliably;
`prune` is disabled on that app to protect them).

## DNS

Point these to the k3s node (`192.168.1.116`): `argocd`, `registry`,
`pantrywise`, `rustfs` (console), `radar` — all as
`<name>.k3s.lab.danielsson.us.com`.

## Notes

- **Traefik is DISABLED** (controller scaled to 0) because the cluster's
  pod-to-pod networking is broken and ingress 502s. All app IngressRoutes are
  staged (commented) in `apps/ingress`. To enable ingress:
  1. Fix the host CNI + `kubectl -n kube-system scale deploy traefik --replicas=1`.
  2. Uncomment `apps/ingress/ingressroute.yaml`, its resource in
     `apps/ingress/kustomization.yaml`, and `application-ingress.yaml` +
     its line in `infra/argocd-apps/kustomization.yaml`.
  3. `kubectl apply -k .`
- **TLS** not configured yet (Traefik serves HTTP on the `web` entrypoint).
  cert-manager is installed and ready; a **Let's Encrypt ClusterIssuer is
  staged (commented)** in `apps/cert-manager` — uncomment it once Traefik is up
  to issue real certs for `*.k3s.lab.danielsson.us.com`.
- Radar's chart has **auth mode `none`** by default — do not expose it outside
  the cluster until auth (proxy/OIDC) is configured.
- **Hermes** (`apps/hermes`) exposes an OpenAI-compatible API (8642) +
  dashboard (9119) over Tailscale. Telegram runs on the existing **native**
  gateway on the node — the in-cluster instance leaves `platforms.telegram`
  disabled so the two never pull the same bot token. To move Telegram into the
  cluster: stop the native gateway, set `telegram.enabled: true` in
  `apps/hermes/configmap.yaml`, and add the `TELEGRAM_*` fields to the
  `k3s/hermes-env` Vaultwarden item. The image is pinned to tag
  `v2026.8.31` (update the `image:` in the deployment to upgrade).
