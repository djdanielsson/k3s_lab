#!/usr/bin/env python3
"""Build the custom Omnigent server image (opencode-native picker row) in-cluster.

Same pattern as the host-image build: an init container stages a tiny build
context into an emptyDir and Kaniko builds it against the in-cluster registry.
No git credential is needed — the context is one Dockerfile, and everything else
comes from the pinned base image.

The build asserts the patch worked (harness_catalog() must contain
opencode-native), so a green build is evidence, not just a pushed layer.

Usage:
    k8s-build-omnigent-server.py               # build + push :latest
    k8s-build-omnigent-server.py v1            # custom tag
    k8s-build-omnigent-server.py --base ghcr.io/omnigent-ai/omnigent-server-kubernetes:v0.16.0
"""
from __future__ import annotations

import base64
import os
import sys
import time

sys.path.insert(0, "/opt/data/work")
from kubehelp import req  # noqa: E402

NAMESPACE = "registry"
REGISTRY = "registry.registry.svc:5000"
IMAGE = "omnigent-server-opencode"
JOB = "omnigent-server-opencode-build"
DOCKERFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "Dockerfile.omnigent-server-opencode")

TAG = "latest"
for a in sys.argv[1:]:
    if a.startswith("--base="):
        continue
    if not a.startswith("--"):
        TAG = a
BASE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--base=")), None)


def dockerfile_text() -> str:
    text = open(DOCKERFILE).read()
    if BASE:
        text = text.replace(
            "ARG SERVER_BASE_IMAGE=ghcr.io/omnigent-ai/omnigent-server-kubernetes:v0.16.0",
            f"ARG SERVER_BASE_IMAGE={BASE}",
        )
    return text


def job_body(df_b64: str) -> dict:
    stage = (
        "set -eu; "
        f'echo "{df_b64}" | base64 -d > /work/Dockerfile; '
        "wc -c /work/Dockerfile"
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": JOB, "namespace": NAMESPACE, "labels": {"app": IMAGE}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 86400,
            "template": {
                "metadata": {"labels": {"app": IMAGE}},
                "spec": {
                    "restartPolicy": "Never",
                    "initContainers": [
                        {
                            "name": "context",
                            "image": "alpine:3.20",
                            "command": ["/bin/sh", "-c"],
                            "args": [stage],
                            "volumeMounts": [{"name": "work", "mountPath": "/work"}],
                        }
                    ],
                    "containers": [
                        {
                            "name": "build",
                            "image": "gcr.io/kaniko-project/executor:v1.23.2",
                            "args": [
                                "--context=dir:///work",
                                "--dockerfile=Dockerfile",
                                f"--destination={REGISTRY}/{IMAGE}:{TAG}",
                                "--insecure",
                                "--verbosity=info",
                                "--cache=true",
                                f"--cache-repo={REGISTRY}/{IMAGE}-cache",
                            ],
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "1Gi"},
                                "limits": {"cpu": "4", "memory": "8Gi"},
                            },
                            "volumeMounts": [{"name": "work", "mountPath": "/work"}],
                        }
                    ],
                    "volumes": [{"name": "work", "emptyDir": {}}],
                },
            },
        },
    }


def main() -> int:
    df_b64 = base64.b64encode(dockerfile_text().encode()).decode()
    print(f"== job {JOB} (tag {TAG}, base {BASE or 'pinned default'}) ==")
    req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs/{JOB}", method="DELETE")
    for _ in range(60):
        if "__error__" in req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs/{JOB}"):
            break
        time.sleep(2)
    out = req(f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs", method="POST", body=job_body(df_b64))
    print("  create:", "ok" if "__error__" not in out else out)
    return 0 if "__error__" not in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
