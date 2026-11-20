#!/usr/bin/env python3
"""Build the Kiri:Moto image into the in-cluster registry with Kaniko.

The build context is the upstream repo itself (kaniko's git context), so there
is nothing vendored here: src/dock/Dockerfile in GridSpace/grid-apps is the
image, unmodified.

Usage:
    python3 build-in-cluster.py                # master -> 0.1.0
    python3 build-in-cluster.py v4.7.0 4.7.0   # ref, tag

Afterwards bump apps/kirimoto/deployment.yaml to the tag you pushed.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/opt/data/work")
from kubehelp import req  # noqa: E402

NS = "registry"
REGISTRY = "registry.registry.svc:5000"
IMAGE = "kirimoto"
JOB = "kirimoto-build"
REF = sys.argv[1] if len(sys.argv) > 1 else "refs/heads/master"
TAG = sys.argv[2] if len(sys.argv) > 2 else "0.1.0"

body = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {"name": JOB, "namespace": NS, "labels": {"app": IMAGE}},
    "spec": {
        "backoffLimit": 0,
        "ttlSecondsAfterFinished": 172800,
        "template": {
            "metadata": {"labels": {"app": IMAGE}},
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "build",
                        "image": "gcr.io/kaniko-project/executor:v1.23.2",
                        "args": [
                            f"--context=git://github.com/GridSpace/grid-apps.git#{REF}",
                            "--dockerfile=src/dock/Dockerfile",
                            f"--destination={REGISTRY}/{IMAGE}:{TAG}",
                            "--insecure",
                            "--verbosity=info",
                            "--cache=true",
                            f"--cache-repo={REGISTRY}/{IMAGE}-cache",
                        ],
                        "resources": {
                            "requests": {"cpu": "1", "memory": "2Gi"},
                            "limits": {"cpu": "6", "memory": "12Gi"},
                        },
                    }
                ],
            },
        },
    },
}

old = req(f"/apis/batch/v1/namespaces/{NS}/jobs/{JOB}")
if "__error__" not in old:
    req(f"/apis/batch/v1/namespaces/{NS}/jobs/{JOB}?propagationPolicy=Background", method="DELETE")

created = req(f"/apis/batch/v1/namespaces/{NS}/jobs", method="POST", body=body)
print("job:", created.get("metadata", {}).get("name"), created.get("__error__", ""))
