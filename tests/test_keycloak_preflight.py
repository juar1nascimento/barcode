from __future__ import annotations

import json
from urllib.error import URLError

import scripts.keycloak_preflight as preflight


def _discovery() -> bytes:
    return json.dumps(
        {
            "issuer": "https://id.example.test/realms/gti-sesa",
            "authorization_endpoint": "https://id.example.test/realms/gti-sesa/protocol/openid-connect/auth",
            "token_endpoint": "https://id.example.test/realms/gti-sesa/protocol/openid-connect/token",
            "jwks_uri": "https://id.example.test/realms/gti-sesa/protocol/openid-connect/certs",
        }
    ).encode()


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return _discovery()


def test_preflight_accepts_valid_https_discovery(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.example.test/realms/gti-sesa/.well-known/openid-configuration",
    )
    monkeypatch.setattr(preflight.urllib.request, "urlopen", lambda *args, **kwargs: _Response())
    assert preflight.main() == 0


def test_preflight_rejects_non_https():
    old = os.environ.get("KEYCLOAK_SERVER_METADATA_URL")
    os.environ["KEYCLOAK_SERVER_METADATA_URL"] = "http://id.example.test/realms/gti-sesa/.well-known/openid-configuration"
    try:
        assert preflight.main() == 1
    finally:
        if old is None:
            os.environ.pop("KEYCLOAK_SERVER_METADATA_URL", None)
        else:
            os.environ["KEYCLOAK_SERVER_METADATA_URL"] = old


def test_preflight_rejects_insecure_discovered_endpoint(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.example.test/realms/gti-sesa/.well-known/openid-configuration",
    )

    class InsecureResponse(_Response):
        def read(self):
            data = json.loads(_discovery())
            data["jwks_uri"] = "http://id.example.test/certs"
            return json.dumps(data).encode()

    monkeypatch.setattr(preflight.urllib.request, "urlopen", lambda *args, **kwargs: InsecureResponse())
    assert preflight.main() == 1


def test_preflight_reports_network_failure(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.example.test/realms/gti-sesa/.well-known/openid-configuration",
    )
    monkeypatch.setattr(
        preflight.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    assert preflight.main() == 1
