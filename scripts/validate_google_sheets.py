"""Validação Google Sheets independente e somente leitura.

Usa uma service account fornecida pelo ambiente. Não cria, atualiza ou apaga células.
"""
from __future__ import annotations

import json
import os
import re

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CREDENTIAL_ENV = "GTI_GOOGLE_SERVICE_ACCOUNT_JSON"
SPREADSHEET_ENV = "GTI_GOOGLE_SPREADSHEET_ID"
SPREADSHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,200}$")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


class ValidationError(ValueError):
    """Configuração inválida ou incompleta, sem conteúdo secreto."""


def validate_config(environ=None) -> tuple[dict, str]:
    env = os.environ if environ is None else environ
    missing = [
        name for name in (CREDENTIAL_ENV, SPREADSHEET_ENV)
        if not str(env.get(name, "")).strip()
    ]
    if missing:
        raise ValidationError("Configuração Google ausente: " + ", ".join(missing))

    try:
        credentials_info = json.loads(str(env[CREDENTIAL_ENV]))
    except json.JSONDecodeError:
        raise ValidationError(f"{CREDENTIAL_ENV} contém JSON inválido.") from None

    if not isinstance(credentials_info, dict):
        raise ValidationError(f"{CREDENTIAL_ENV} deve conter um objeto JSON.")

    required = ("type", "project_id", "private_key", "client_email", "token_uri")
    missing_fields = [
        field for field in required
        if not str(credentials_info.get(field, "")).strip()
    ]
    if missing_fields:
        raise ValidationError(
            "Credencial Google incompleta; campos ausentes: "
            + ", ".join(missing_fields)
        )
    if credentials_info.get("type") != "service_account":
        raise ValidationError("A credencial Google deve ser do tipo service_account.")
    if not str(credentials_info["client_email"]).endswith(
        ".iam.gserviceaccount.com"
    ):
        raise ValidationError("client_email não corresponde a uma service account.")
    if not str(credentials_info["token_uri"]).startswith("https://"):
        raise ValidationError("token_uri da service account deve usar HTTPS.")

    spreadsheet_id = str(env[SPREADSHEET_ENV]).strip()
    if not SPREADSHEET_ID_RE.fullmatch(spreadsheet_id):
        raise ValidationError(
            f"{SPREADSHEET_ENV} deve conter somente o ID da planilha, não a URL."
        )
    return credentials_info, spreadsheet_id


def validate_readonly(
    environ=None, credentials_factory=None, authorizer=None, drive_factory=None
):
    info, spreadsheet_id = validate_config(environ)
    factory = credentials_factory or Credentials.from_service_account_info
    authorize = authorizer or gspread.authorize
    drive_builder = drive_factory or build
    credentials = factory(info, scopes=SCOPES)

    # Leitura de metadados e abas: nenhuma célula é criada ou alterada.
    client = authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheets = spreadsheet.worksheets()

    # Drive capabilities confirma permissão de edição sem executar uma escrita.
    drive = drive_builder("drive", "v3", credentials=credentials, cache_discovery=False)
    metadata = (
        drive.files()
        .get(
            fileId=spreadsheet_id,
            supportsAllDrives=True,
            fields="id,mimeType,capabilities(canEdit,canModifyContent)",
        )
        .execute()
    )
    capabilities = metadata.get("capabilities", {})
    if not capabilities.get("canEdit") or not capabilities.get("canModifyContent"):
        raise ValidationError(
            "A conta de serviço acessa a planilha, mas não possui permissão de edição."
        )
    if not worksheets:
        raise ValidationError(
            "A planilha foi acessada, mas não contém abas disponíveis."
        )
    return {"worksheet_count": len(worksheets)}


def main() -> int:
    try:
        result = validate_readonly()
    except ValidationError as exc:
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        # Não imprime a mensagem da biblioteca: pode conter URL ou dados sensíveis.
        raise SystemExit(
            "Validação Google Sheets falhou; diagnóstico sem dados sensíveis: "
            + type(exc).__name__
        ) from None
    print(
        "GOOGLE_SHEETS_VALIDATION_OK: "
        f"readonly_metadata=true editor_capability=true worksheets={result['worksheet_count']}"
    )
    return 0


if __name__ == "__main__":
    main()
