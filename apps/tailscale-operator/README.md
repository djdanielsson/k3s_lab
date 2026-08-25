# Tailscale operator — scaffold

Exposes Services on your tailnet (`*.ts.net`, over WireGuard) so you can reach
the apps from any of your devices, anywhere. Deployed **alongside Traefik**
(Traefik stays for local-LAN access).

> Status: **scaffold only** — namespace + SealedSecret are in place, but the
> operator Helm chart is not installed yet (its chart endpoint 404'd from our
> sandbox; install it from the official docs once credentials are ready).

## 1. Create a Tailscale OAuth client
1. Admin Console → **Settings → Keys → Generate… → OAuth clients**
2. Name: `k3s-operator`, scope **"Read and Write"**
3. Copy the **Client ID** and **Client Secret**.
4. Ensure **MagicDNS** is enabled (Admin Console → DNS → on).

## 2. Configure the SealedSecret (do this with your real credentials)
This is the part you fill in. From a machine with `kubeseal`:

```bash
# a) write a plain Secret with YOUR values (this file never gets committed)
cat > /tmp/ts-secret.yaml <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: tailscale-oauth
  namespace: tailscale
type: Opaque
stringData:
  client_id: <YOUR_CLIENT_ID>
  client_secret: <YOUR_CLIENT_SECRET>
EOF

# b) seal it into the SealedSecret that lives in this repo
#    (kubeseal is at ~/.local/bin/kubeseal; grab the controller cert if needed:
#     kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
#       -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/ss-cert.pem )
~/.local/bin/kubeseal --cert /tmp/ss-cert.pem --format yaml \
  < /tmp/ts-secret.yaml > apps/tailscale-operator/sealed-secret.yaml

# c) commit + push — ArgoCD applies it, the controller updates the Secret in-cluster
git add apps/tailscale-operator/sealed-secret.yaml
git commit -m "tailsk: real oauth creds"
git push origin gitops-fresh
```

The placeholder in the repo currently decrypts to `client_id=REPLACE_WITH_OAUTH_CLIENT_ID`.

## 3. Install the operator (once the chart/creds are ready)
Per the official docs:
```bash
helm repo add tailscale https://pkgs.tailscale.com/helm-charts
helm upgrade --install operator tailscale/tailscale-operator \
  --namespace tailscale --create-namespace \
  --set-string oauth.clientId=<client-id> \
  --set-string oauth.clientSecret=<client-secret>
```
(or configure it to read the `tailscale-oauth` Secret above).

## 4. Expose an app (opt-in per Service)
Add to any app's Service:
```yaml
metadata:
  annotations:
    tailscale.com/manage: "true"
    tailscale.com/hostname: radar        # -> radar.<tailnet>.ts.net
```
Its Service proxy gets a MagicDNS name reachable from any Tailscale device.
