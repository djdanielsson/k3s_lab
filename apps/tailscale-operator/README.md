# Tailscale Operator — v1.102.3 (k3s v1.36)

## History: the v1.80.0 pin (lifted 2026-09-07)

The lab cluster used to run **k3s v1.26.5**. Tailscale operator releases
`v1.82+` rely on the Kubernetes **ValidatingAdmissionPolicy** API (k8s ≥ 1.31);
on 1.26 newer operators silently skipped every tailnet Ingress, so the
operator was pinned to **v1.80.0** (newest release using the classic TSIngress
model, `ingressClassName: tailscale`).

After the cluster upgrade to **k3s v1.36**, the pin was lifted: the Application
tracks the latest release (Renovate keeps chart + `image.tag` in lockstep, see
`renovate.json`), currently **v1.102.3**. Proxy image stays on the `:stable`
tag. If tailnet Ingresses ever stop reconciling after an operator bump, check
`kubectl logs -n tailscale deploy/operator` for missing-API noise — that's the
signature of this class of breakage.

## Current operator state

- Namespace: `tailscale`
- Connector `k3s` (subnet router + exit node, `tag:k3s`) advertises:
  `192.168.1.0/24`, `10.42.0.0/16`, `10.43.0.0/16`.
- OAuth creds: `operator-oauth` / `tailscale-oauth` SealedSecrets.
- Tailnet: `tail7f3c08.ts.net`
