# Custom Omnigent images — built in-cluster, pinned to an upstream base.

Two images live here, both `FROM` a pinned upstream base with a single,
deliberate change each. Neither forks the source tree: the changes are a
one-line source patch and an upstream-supported npm install, so they track
upstream instead of drifting from it.

## Why they exist

- **`Dockerfile.omnigent-server-opencode`** — the UI picker omits
  `opencode-native` because `harness_labels` in `omnigent/harness_plugins.py`
  has no entry for it. The harness is already in `valid_harnesses()` (27
  entries), so the catalog filter was never the blocker; the missing *label* is.
  Without a row the harness is unselectable, so it can never be tested.

- **`Dockerfile.omnigent-host-opencode`** — the official `omnigent-host` image
  ships claude / codex / pi / kiro-cli / agy and **no opencode binary**, so a
  sandbox that picks opencode-native has nothing to launch. Upstream's own
  `install-harness-cli.sh` row installs it; the Dockerfile just calls it.
  The same image carries two source patches for the **direct OpenCode Go lane**:
  the runner's tunnel hello frame now advertises `opencode-native` (without that
  row the server never offers the harness on a managed sandbox, even though
  `configured_harness_map()` already reports it ready), and the synthesized
  `@ai-sdk/openai-compatible` provider gets `x-opencode-session` /
  `x-opencode-client` headers — OpenCode Go answers `400 MissingSessionID`
  without a stable per-conversation session id. Both patches assert their anchors
  at build time and drop stale bytecode for the two edited modules.

## Building

```
python3 build-in-cluster.py            # both images, :latest tags
python3 build-in-cluster.py --base=... # re-pin the upstream base
```

Kaniko runs in the `registry` namespace and pushes to the in-cluster registry
(`registry.registry.svc:5000`). The build needs no git credential: the context
is inlined, and everything else comes from the pinned base.

## Traps worth knowing before you edit these

- **The server package is an EDITABLE install.** The module resolves to
  `/build/omnigent/harness_plugins.py`, **not** into site-packages, and it is
  plain source — so a `sed` is enough and there is no `.pyc` to invalidate. An
  earlier plan looked for the file under site-packages and concluded the image
  was compiled bytecode. It is not.
- **Assert in the build, and again against the pushed image.** The first build
  of the server image silently skipped its verification `RUN` and still reported
  success; only a probe pod on the pushed tag proved the patch was really there.
  Treat "kaniko finished" as "layers pushed", never as "the change is in".
- **`harness_labels` is keyed by the picker id**, so adding a row is what makes
  a harness selectable. Flipping `valid_harnesses` does nothing for the catalog.
- **A picker row is not a working session.** The runner advertises its own
  harness list in the hello frame (`runner/transports/ws_tunnel/serve.py`) and
  dispatches through its own tables; the row only lets a session be *created*.
  The hello-frame patch above is what closes that gap for `opencode-native`.
