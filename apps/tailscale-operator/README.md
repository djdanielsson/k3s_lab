# Tailscale Operator — pinned to v1.80.0 (required for k3s v1.26)

## Why v1.80.0?

The lab cluster runs **k3s v1.26.5**. Recent Tailscale operator releases (`v1.82+`,
including `:stable`) rely on the Kubernetes **ValidatingAdmissionPolicy** API, which
only exists in **Kubernetes ≥ 1.31**. On k3s v1.26.5 that API is absent, so newer
operator versions silently skip *every* tailnet Ingress (log noise like
`no matches for kind "ValidatingAdmissionPolicy"` and `ProxyGroup "" does not exist`),
which is why apps stopped being reachable on the tailnet.

**v1.80.0** is the newest release that works on Kubernetes 1.26 and uses the classic
**TSIngress** model (`ingressClassName: tailscale`). It exposes each app as its own
Tailscale proxy device with a MagicDNS name — no ProxyGroup/AdmissionPolicy needed.

### The fix (what was done)

1. **Pin the operator image**:
   ```bash
   kubectl set image deploy/operator operator=tailscale/k8s-operator:v1.80.0 -n tailscale
   kubectl rollout status deploy/operator -n tailscale
   ```
2. **Pin the Argo CD Application** (this file) to `targetRevision: v1.80.0` so a
   future sync does not silently undo the downgrade.
3. Verify it's running clean:
   ```bash
   kubectl logs -n tailscale deploy/operator | grep -iE "version|error"
   # expect: ... operator running, version: 1.80.0-...
   ```

> ⚠️ Do **not** bump this above v1.80 until the cluster is upgraded to k8s ≥ 1.31.

## Current operator state

- Namespace: `tailscale`
- Connector `k3s` (subnet router + exit node, `tag:k3s`) advertises:
  `192.168.1.0/24`, `10.42.0.0/16`, `10.43.0.0/16`.
- OAuth creds: `operator-oauth` / `tailscale-oauth` SealedSecrets.
- Tailnet: `tail7f3c08.ts.net`
