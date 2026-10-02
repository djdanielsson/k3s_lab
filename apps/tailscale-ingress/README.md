# Tailscale Ingress — how to expose an app on the tailnet

Each app gets a **TSIngress** pushed up to the tailnet, reachable from any of your
Tailscale devices at a MagicDNS hostname (no public exposure).

## How it works

The Tailscale operator (currently **v1.102.3** — the old v1.80 pin was lifted
with the k3s 1.36 upgrade) watches
`Ingress` resources with **`ingressClassName: tailscale`**. For each one it:

1. creates a Tailscale proxy device (`tailscale` StatefulSet + headless Service in
   `tailscale` ns),
2. joins it to your tailnet (`tail7f3c08.ts.net`),
3. serves the app over HTTPS (valid MagicDNS cert) with the hostname
   `https://<name>.tail7f3c08.ts.net`.

The app keeps its normal Traefik LAN ingress too — the TSIngress is additive.

## Naming the hostname

`spec.tls[0].hosts[0]` decides the MagicDNS name: the operator takes the **first
label** of that host as the device name and appends the tailnet domain, so
`forgejo.tail7f3c08.ts.net` yields `https://forgejo.tail7f3c08.ts.net`.

Without `spec.tls`, the hostname falls back to
`<namespace>-<ingress-name>-ingress` — which is how every TSIngress here was named
before, and why the Ingress objects mostly still carry a `-ts` suffix. The
`tailscale.com/hostname` annotation is still ignored; TLS hosts are the supported
lever.

Renaming spends a new Let's Encrypt certificate for a *new* name, which is fine:
the tailnet-domain limit is 50 certificates per week, and the five-per-week limit
only applies to re-requesting the same name. Old proxy devices linger in the
tailnet until they expire — remove them in the admin console if they clutter the
machine list.

## Enable an app (the pattern)

Add this to an app's directory and reference it in its `kustomization.yaml`:

```yaml
# apps/<app>/tailscale-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <app>-ts
  namespace: <app>
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: <App>
    gethomepage.dev/group: <Platform|Applications|Agents>
    gethomepage.dev/icon: <icon>
    gethomepage.dev/description: <one line>
    gethomepage.dev/href: https://<app>.tail7f3c08.ts.net
spec:
  ingressClassName: tailscale
  tls:
    - hosts:
        - <app>.tail7f3c08.ts.net
  defaultBackend:
    service:
      name: <service>
      port:
        number: <port>
```

Then add it to `apps/<app>/kustomization.yaml` resources. Argo CD auto-syncs it
(these apps are `automated` with `prune`+`selfHeal`).

Proxies are created in `tailscale` ns; remove the Ingress to tear the proxy down.

## The dashboard picks it up automatically

`apps/homepage` runs Homepage with `kubernetes.yaml` set to `mode: cluster` and
`ingress: true`, so every Ingress annotated `gethomepage.dev/enabled: "true"`
becomes a tile at `https://homepage.tail7f3c08.ts.net`. The annotations above are the whole
registration — there is no services list to edit.

Two things to know:

- **`gethomepage.dev/href` is mandatory on a TSIngress.** Homepage derives a tile
  URL from `spec.rules[0].host` when no href is given, and these Ingresses use a
  `defaultBackend` with no rules, so the lookup throws — and because the error is
  caught per integration, one such Ingress silently empties the *entire*
  Kubernetes-discovered group.
- Homepage caches the page it renders, so a new or changed annotation shows up
  within a minute or two (or immediately after
  `kubectl -n homepage rollout restart deploy/homepage`).

Anything that cannot be discovered from an Ingress (an app with no TSIngress, a
non-Kubernetes link) goes in `apps/homepage/config/services.yaml` instead.

## Current exposed apps

| App | Service:port | Hostname |
|-----|--------------|----------|
| argocd | `argocd-server:80` | `https://argocd.tail7f3c08.ts.net` |
| prometheus | `kube-prometheus-stack-prometheus:9090` | `https://prometheus.tail7f3c08.ts.net` |
| registry | `registry:5000` | `https://registry.tail7f3c08.ts.net` |
| rustfs | `rustfs:9001` (console) | `https://rustfs.tail7f3c08.ts.net` |
| litellm | `litellm:4000` | `https://litellm.tail7f3c08.ts.net` |
| forgejo | `forgejo:3000` | `https://forgejo.tail7f3c08.ts.net` |
| pantrywise | `web:80` | `https://pantrywise.tail7f3c08.ts.net` |
| netalertx | `netalertx:20211` | `https://netalertx.tail7f3c08.ts.net` |
| netdata | `netdata:19999` | `https://netdata.tail7f3c08.ts.net` |
| radar | `radar:9280` | `https://radar.tail7f3c08.ts.net` |
| omnigent | `omnigent:80` | `https://omnigent.tail7f3c08.ts.net` |
| hermes | `hermes:9119` | `https://hermes.tail7f3c08.ts.net` |
| hermes (API) | `hermes:8642` | `https://hermes-api.tail7f3c08.ts.net` |
| glance | `glance:8080` | `https://glance.tail7f3c08.ts.net` (not a Homepage tile) |
| homepage | `homepage:80` | `https://homepage.tail7f3c08.ts.net` |

## Prerequisites / notes

- Operator tracks the latest release (Renovate-managed, chart + `image.tag`
  in lockstep).
- Every app's proxy device is tagged `tag:k3s` (ACL must allow the operator to own
  that tag — already the case for the Connector).
- This replaces the old, now-broken `tailscale.com/ingress: "true"` annotation
  approach (that model only worked on pre-v1.80 operators; on v1.80 the same
  Ingress must instead use `ingressClassName: tailscale`).
