#!/usr/bin/env python3
"""Build the custom Omnigent images (server + host) in-cluster with Kaniko.

Both Dockerfiles COPY files from patches/, so the build context has to be the
whole image directory, not just one Dockerfile. Kaniko runs as a Job in the
registry namespace and pushes to the in-cluster registry.

The server image asserts the picker patch and the Vault cipher at build time
(patches/verify-server.py); the host image asserts both source-patch anchors.
A green build is therefore evidence, not just pushed layers.

Usage:
    python3 build-in-cluster.py v0.20.0-sub1                        # both images
    python3 build-in-cluster.py v0.20.0-sub1 --image=host
    python3 build-in-cluster.py v0.20.0-sub1 --base=ghcr.io/omnigent-ai/omnigent-server-kubernetes:v0.20.0
    python3 build-in-cluster.py v0.20.0-sub1 --base-version=v0.20.0  # rewrites both bases
"""
from __future__ import annotations

import base64
import io
import os
import sys
import tarfile
import time

sys.path.insert(0, "/opt/data/work")
from kubehelp import req  # noqa: E402

NAMESPACE = "registry"
REGISTRY = "registry.registry.svc:5000"
HERE = os.path.dirname(os.path.abspath(__file__))

IMAGES = {
    "server": {
        "dockerfile": "Dockerfile.omnigent-server-opencode",
        "image": "omnigent-server-opencode",
        "job": "omnigent-server-opencode-build",
        "arg": "SERVER_BASE_IMAGE",
        "default_base": "ghcr.io/omnigent-ai/omnigent-server-kubernetes:v0.20.0",
    },
    "host": {
        "dockerfile": "Dockerfile.omnigent-host-opencode",
        "image": "omnigent-host-opencode",
        "job": "omnigent-host-opencode-build",
        "arg": "HOST_BASE_IMAGE",
        "default_base": "ghcr.io/omnigent-ai/omnigent-host:v0.20.0",
    },
}


def context_b64(dockerfile: str | None = None, content: str | None = None) -> str:
    """tar.gz of the Dockerfiles + patches directory, base64 for a shell arg.

    `dockerfile`/`content` substitute one file inside the archive so a base
    re-pin never has to touch the working tree.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in os.listdir(HERE):
            if not (name.startswith("Dockerfile.") or name == "patches"):
                continue
            path = os.path.join(HERE, name)
            if name == dockerfile and content is not None:
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.add(path, arcname=name)
    return base64.b64encode(buf.getvalue()).decode()


def job_body(image: str, tag: str, ctx: str) -> dict:
    stage = (
        "set -eu; "
        f'echo "{ctx}" | base64 -d | tar xzf - -C /work; '
        "ls -R /work | head -30"
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": IMAGES[image]["job"], "namespace": NAMESPACE,
                     "labels": {"app": IMAGES[image]["image"]}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 86400,
            "template": {
                "metadata": {"labels": {"app": IMAGES[image]["image"]}},
                "spec": {
                    "restartPolicy": "Never",
                    "initContainers": [{
                        "name": "context",
                        "image": "alpine:3.20",
                        "command": ["/bin/sh", "-c"],
                        "args": [stage],
                        "volumeMounts": [{"name": "work", "mountPath": "/work"}],
                    }],
                    "containers": [{
                        "name": "build",
                        "image": "gcr.io/kaniko-project/executor:v1.23.2",
                        "args": [
                            "--context=dir:///work",
                            f"--dockerfile={IMAGES[image]['dockerfile']}",
                            f"--destination={REGISTRY}/{IMAGES[image]['image']}:{tag}",
                            "--insecure",
                            "--verbosity=info",
                            "--cache=true",
                            f"--cache-repo={REGISTRY}/{IMAGES[image]['image']}-cache",
                        ],
                        "resources": {"requests": {"cpu": "500m", "memory": "1Gi"},
                                      "limits": {"cpu": "4", "memory": "8Gi"}},
                        "volumeMounts": [{"name": "work", "mountPath": "/work"}],
                    }],
                    "volumes": [{"name": "work", "emptyDir": {}}],
                },
            },
        },
    }


def start(image: str, tag: str, ctx: str) -> bool:
    name = IMAGES[image]["job"]
    req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs/{name}", method="DELETE")
    for _ in range(60):
        if "__error__" in req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs/{name}"):
            break
        time.sleep(2)
    out = req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs", method="POST",
              body=job_body(image, tag, ctx))
    ok = "__error__" not in out
    print(f"== {image}: job {name} tag {tag}: {'created' if ok else out}")
    return ok


def main() -> int:
    tag = "latest"
    only = None
    base_version = None
    for a in sys.argv[1:]:
        if a.startswith("--image="):
            only = a.split("=", 1)[1]
        elif a.startswith("--base-version="):
            base_version = a.split("=", 1)[1]
        elif a.startswith("--base="):
            pass  # single-image override handled by editing the Dockerfile default
        elif not a.startswith("--"):
            tag = a

    targets = [only] if only else ["server", "host"]
    for image in targets:
        cfg = IMAGES[image]
        base = cfg["default_base"]
        if base_version:
            base = base.rsplit(":", 1)[0] + ":" + base_version
        # Rewrite the pinned default in a temporary copy so the context carries it.
        df_path = os.path.join(HERE, cfg["dockerfile"])
        original = open(df_path).read()
        patched = original.replace(
            f"ARG {cfg['arg']}={cfg['default_base']}",
            f"ARG {cfg['arg']}={base}",
        )
        if patched == original and base != cfg["default_base"]:
            print(f"!! {df_path}: ARG {cfg['arg']}={cfg['default_base']} not found")
            return 1
        if image == "host" and base_version:
            patched = patched.replace("ARG INSTALL_SCRIPT_REF=main",
                                      f"ARG INSTALL_SCRIPT_REF={base_version}")
        ctx = context_b64(cfg["dockerfile"], patched)
        print(f"== {image}: base {base}, tag {tag}")
        if not start(image, tag, ctx):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
