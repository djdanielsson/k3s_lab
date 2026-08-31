# Tailscale Ingress — how to expose an app on the tailnet

Each app gets a **TSIngress** pushed up to the tailnet, reachable from any of your
Tailscale devices at a MagicDNS hostname (no public exposure).

## How it works

The Tailscale operator (pinned to **v1.80.0** — see
[`../tailscale-operator/README.md`](../tailscale-operator/README.md)) watches
`Ingress` resources with **`ingressClassName: tailscale`**. For each one it:

1. creates a Tailscale proxy device (`tailscale` StatefulSet + headless Service in
   `tailscale` ns),
2. joins it to your tailnet (`tail7f3c08.ts.net`),
3. serves the app over HTTPS (valid MagicDNS cert) with the hostname
   `https://<namespace>-<ingress-name>-ingress.tail7f3c08.ts.net`.

The app keeps its normal Traefik LAN ingress too — the TSIngress is additive.

## Enable an app (the pattern)

Add this to an app's directory and reference it in its `kustomization.yaml`:

```yaml
# apps/<app>/tailscale-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <app>-ts
  namespace: <app>
spec:
  ingressClassName: tailscale
  defaultBackend:
    service:
      name: <service>
      port:
        number: <port>
```

Then add it to `apps/<app>/kustomization.yaml` resources. Argo CD auto-syncs it
(these apps are `automated` with `prune`+`selfHeal`).

Proxies are created in `tailscale` ns; remove the Ingress to tear the proxy down.

> The MagicDNS hostname is derived from `namespace` + `ingress name`
> (e.g. `pantrywise-pantrywise-ts-ingress.tail7f3c08.ts.net`). The
> `tailscale.com/hostname` annotation is **ignored** at v1.80 — name the Ingress to
> get the hostname you want.

## Current exposed apps

| App | Service:port | TSIngress |
|-----|--------------|-----------|
| pantrywise | `web:80` | pantrywise-ts |
| forgejo | `forgejo:3000` | forgejo-ts |
| glance | `glance:8080` | glance-ts |
| netdata | `netdata:19999` | netdata-ts |
| netalertx | `netalertx:20211` | netalertx-ts |
| rustfs | `rustfs:9001` (console) | rustfs-ts |
| registry | `registry:5000` | registry-ts |
| radar | `radar:9280` | radar-ts |
| spiritual-gifts | `web:80` | spiritual-gifts-ts |

## Prerequisites / notes

- Operator must be **v1.80.0** (k8s 1.26). Do not upgrade it until the cluster hits
  k8s ≥ 1.31 (see the operator README).
- Every app's proxy device is tagged `tag:k3s` (ACL must allow the operator to own
  that tag — already the case for the Connector).
- This replaces the old, now-broken `tailscale.com/ingress: "true"` annotation
  approach (that model only worked on pre-v1.80 operators; on v1.80 the same
  Ingress must instead use `ingressClassName: tailscale`).
