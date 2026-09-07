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
| kelos        | Helm chart `kelos-dev/kelos` v0.55.0 (+ console) | controller + console in `kelos-system` (+ Tailscale) |
| caretta      | Helm chart `groundcover/caretta` 0.0.16 (eBPF net map + Grafana) | `caretta.caretta.svc` |
| radar        | Helm chart `skyhook/radar` | `radar.radar.svc:9280` (+ Tailscale) |

Radar's chart creates a **ClusterRole** to read the cluster; the AppProject
whitelists `ClusterRole`/`ClusterRoleBinding` (plus `tailscale.com Connector`
and `external-secrets.io ClusterSecretStore`) for that. Cert-manager tracks
the latest release with Helm-managed CRDs (`installCRDs=true` so controller
and CRDs move together).

## DNS

Point these to the k3s node (`192.168.1.116`): `argocd`, `registry`,
`pantrywise`, `rustfs` (console), `radar` — all as
`<name>.k3s.lab.danielsson.us.com`.

## Notes

- **Traefik**: k3s-bundled, currently running (reinstalled by the k3s
  upgrade) but **unused** — all UIs are served via Tailscale Ingresses
  instead, and `apps/ingress` (Traefik IngressRoutes) stays staged/disabled.
  The ArgoCD Traefik route was removed from `infra/argocd` (CRDs gone at the
  time); do not re-add it without verifying the CRDs exist.
- **metrics-server** (k3s-bundled): if the `v1beta1.metrics.k8s.io`
  APIService goes unavailable and pods can't reach host IPs (`No route to
  host` to `192.168.1.116`), the cause is firewalld putting the CNI
  interfaces in the `public` zone. k3s requires them in `trusted`
  (host-level fix, not gitops — run via a debug pod or on the node):
  ```bash
  kubectl debug node/agent47.lab.danielsson.us.com --image=busybox:1.38 --profile=sysadmin -- \
    chroot /host sh -c "firewall-cmd --permanent --zone=trusted --change-interface=cni0 && firewall-cmd --permanent --zone=trusted --change-interface=flannel.1 && firewall-cmd --reload"
  ```
  Then `kubectl -n kube-system scale deploy metrics-server --replicas=1`.
  Same root cause takes down the node/kubelet Prometheus targets.
- **TLS** not configured yet (Traefik serves HTTP on the `web` entrypoint).
  cert-manager is installed and ready; a **Let's Encrypt ClusterIssuer is
  staged (commented)** in `apps/cert-manager` — uncomment it once Traefik is up
  to issue real certs for `*.k3s.lab.danielsson.us.com`.
- Radar's chart has **auth mode `none`** by default — do not expose it outside
  the cluster until auth (proxy/OIDC) is configured.
- **Hermes** (`apps/hermes`) exposes an OpenAI-compatible API (8642) +
  dashboard (9119) over Tailscale and runs the **Telegram** gateway in-cluster
  (bot days from the `k3s/hermes-env` Vaultwarden item). Telegram polling is
  outbound, so the pod needs egress to `api.telegram.org`. The node's **native**
  Hermes gateway must be stopped once the cluster one is up — two gateways on
  the same bot token conflict. Image tracks the floating `latest` build via a
  digest pin (`nousresearch/hermes-agent:latest@sha256:...`); Renovate opens
  digest-update PRs as builds move, or version PRs when a newer `v20YY.M.D`
  tag gets cut.
