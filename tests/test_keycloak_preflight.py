from __future__ import annotations

from requests import RequestException

import scripts.keycloak_preflight as preflight


def _discovery() -> dict:
    return {
        "issuer": "https://id.gti.example/realms/gti-sesa",
        "authorization_endpoint": "https://id.gti.example/realms/gti-sesa/protocol/openid-connect/auth",
        "token_endpoint": "https://id.gti.example/realms/gti-sesa/protocol/openid-connect/token",
        "jwks_uri": "https://id.gti.example/realms/gti-sesa/protocol/openid-connect/certs",
    }


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return _discovery()


def test_preflight_accepts_valid_https_discovery(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.gti.example/realms/gti-sesa/.well-known/openid-configuration",
    )
    monkeypatch.setattr(preflight.requests, "get", lambda *args, **kwargs: _Response())
    assert preflight.main() == 0


def test_preflight_rejects_non_https(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "http://id.gti.example/realms/gti-sesa/.well-known/openid-configuration",
    )
    assert preflight.main() == 1


def test_preflight_rejects_insecure_discovered_endpoint(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.gti.example/realms/gti-sesa/.well-known/openid-configuration",
    )

    class InsecureResponse(_Response):
        def json(self):
            data = _discovery()
            data["jwks_uri"] = "http://id.gti.example/certs"
            return data

    monkeypatch.setattr(preflight.requests, "get", lambda *args, **kwargs: InsecureResponse())
    assert preflight.main() == 1


def test_preflight_reports_network_failure(monkeypatch):
    monkeypatch.setenv(
        "KEYCLOAK_SERVER_METADATA_URL",
        "https://id.gti.example/realms/gti-sesa/.well-known/openid-configuration",
    )
    monkeypatch.setattr(
        preflight.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RequestException("offline")),
    )
    assert preflight.main() == 1
