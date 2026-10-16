"""Renders of the Helm chart k8s/wikidb: the SSPCloud render stays fixed, the Nubonyxia additions stay off by default."""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "k8s" / "wikidb"
SNAPSHOT = Path(__file__).parent / "snapshots" / "chart-sspcloud.yaml"
DIGESTS = ["--set", "image.digest=sha256:" + "a" * 64, "--set", "export.image.digest=sha256:" + "b" * 64]

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")


def render(*args, sspcloud=True):
    values = ["-f", str(CHART / "values-sspcloud.yaml")] if sspcloud else ["--set", "postgresql.host=db",
                                                                            "--set", "postgresql.secretName=db-app",
                                                                            "--set", "ingress.hostname=wiki.example.org"]
    out = subprocess.run(["helm", "template", "wikidb", str(CHART), *values, *DIGESTS, *args],
                         capture_output=True, text=True, check=True)
    return out.stdout


def test_sspcloud_render_is_unchanged():
    assert render() == SNAPSHOT.read_text()


def test_pull_secret_set():
    args = ["--set", "imageCredentials.registry=harbor.example.org", "--set", "imageCredentials.username=robot",
            "--set", "imageCredentials.token=t0ken"]
    out = render(*args)
    pull = render(*args, "--show-only", "templates/pull-secret.yaml")
    assert "type: kubernetes.io/dockerconfigjson" in pull
    config = json.loads(base64.b64decode(pull.split(".dockerconfigjson: ")[1].strip()))
    assert config["auths"]["harbor.example.org"]["auth"] == base64.b64encode(b"robot:t0ken").decode()
    assert out.count("imagePullSecrets:\n        - name: wikidb-pull") == 2


def test_pull_secret_unset():
    out = render()
    assert "imagePullSecrets" not in out and "dockerconfigjson" not in out


def test_app_secrets_enabled():
    value = base64.b64encode(b"s3cret").decode()
    args = ["--set", "appSecrets.enabled=true", "--set", "appSecrets.secrets[0].name=OIDC_SECRET",
            "--set", f"appSecrets.secrets[0].valueBase64={value}"]
    secret = render(*args, "--show-only", "templates/app-secret.yaml")
    assert f'OIDC_SECRET: "{value}"' in secret
    wiki = render(*args, "--show-only", "templates/deployment.yaml")
    assert "secretName: wikidb-app-secrets\n            defaultMode: 0400" in wiki


def test_app_secrets_fallback():
    wiki = render("--show-only", "templates/deployment.yaml")
    assert "secretName: wikidb-app\n" in wiki
    assert "templates/app-secret.yaml" not in render()


def test_postgresql_default_keys():
    wiki = render("--show-only", "templates/deployment.yaml", sspcloud=False)
    assert "key: dbname}" in wiki and "key: username}" in wiki and "key: password}" in wiki


def test_postgresql_discoverable_keys():
    wiki = render("--set", "postgresql.keys.database=postgres-database", "--set", "postgresql.keys.username=postgres-username",
                  "--show-only", "templates/deployment.yaml", sspcloud=False)
    assert "name: DB_DATABASE\n              valueFrom: {secretKeyRef: {name: db-app, key: postgres-database}}" in wiki
    assert "key: postgres-username}" in wiki and "key: password}" in wiki
