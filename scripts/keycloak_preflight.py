#!/usr/bin/env python3
"""Pré-flight isolado do discovery OIDC do Keycloak.

Uso:
  KEYCLOAK_SERVER_METADATA_URL="https://host/realms/gti-sesa/.well-known/openid-configuration" \
    python scripts/keycloak_preflight.py

Este script não lê nem imprime client_secret, cookie_secret ou tokens.
Ele não é importado pelo app e não altera o fluxo de produção.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import requests

TIMEOUT_SECONDS = 8
REQUIRED_FIELDS = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def main() -> int:
    url = os.environ.get("KEYCLOAK_SERVER_METADATA_URL", "").strip()
    if not url:
        return fail("KEYCLOAK_SERVER_METADATA_URL não foi informado.")

    parsed = urlparse(url)
    if parsed.scheme != "https":
        return fail("O endpoint OIDC deve usar HTTPS.")
    if not parsed.hostname:
        return fail("O endpoint OIDC não possui hostname válido.")

    lowered = url.lower()
    placeholders = ("seu-keycloak", "seu-endereco", "example.com", "localhost")
    if any(item in lowered for item in placeholders):
        return fail("O endpoint informado ainda parece ser um placeholder.")

    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "gti-sesa-keycloak-preflight/1",
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        if response.status_code != 200:
            return fail(f"Discovery respondeu HTTP {response.status_code}.")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "desconhecido"
        return fail(f"Discovery respondeu HTTP {status}.")
    except requests.RequestException as exc:
        return fail(f"Não foi possível acessar o discovery: {type(exc).__name__}.")
    except Exception as exc:
        return fail(f"Erro inesperado ao acessar o discovery: {type(exc).__name__}.")

    try:
        metadata = response.json()
    except ValueError:
        return fail("A resposta do discovery não é JSON válido.")

    if not isinstance(metadata, dict):
        return fail("A resposta do discovery não é um objeto JSON.")

    missing = [
        field
        for field in REQUIRED_FIELDS
        if not isinstance(metadata.get(field), str) or not metadata[field].strip()
    ]
    if missing:
        return fail("Metadados obrigatórios ausentes: " + ", ".join(missing))

    issuer = metadata["issuer"].strip()
    issuer_parsed = urlparse(issuer)
    if issuer_parsed.scheme != "https" or not issuer_parsed.hostname:
        return fail("O issuer informado pelo Keycloak não é HTTPS ou não possui hostname válido.")

    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = str(metadata[field]).strip()
        endpoint_parsed = urlparse(endpoint)
        if endpoint_parsed.scheme != "https" or not endpoint_parsed.hostname:
            return fail(f"{field} não é um endpoint HTTPS válido.")

    print("OK: discovery OIDC do Keycloak está acessível e contém os endpoints obrigatórios.")
    print(f"Issuer: {issuer}")
    print("Endpoints: authorization_endpoint, token_endpoint e jwks_uri presentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
