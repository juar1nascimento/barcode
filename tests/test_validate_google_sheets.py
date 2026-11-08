import json

import pytest

from scripts import validate_google_sheets as validator


def _env(**overrides):
    credentials = {
        "type": "service_account",
        "project_id": "gti-test",
        "private_key": "not-a-real-private-key",
        "client_email": "gti-test@gti-test.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    values = {
        "GTI_GOOGLE_SERVICE_ACCOUNT_JSON": json.dumps(credentials),
        "GTI_GOOGLE_SPREADSHEET_ID": "a" * 44,
    }
    values.update(overrides)
    return values


def test_google_config_is_independent_from_postgres_credentials():
    info, spreadsheet_id = validator.validate_config(_env())
    assert info["type"] == "service_account"
    assert spreadsheet_id == "a" * 44


def test_google_config_reports_missing_credentials():
    with pytest.raises(validator.ValidationError, match="GTI_GOOGLE_SERVICE_ACCOUNT_JSON"):
        validator.validate_config(_env(GTI_GOOGLE_SERVICE_ACCOUNT_JSON=""))


def test_google_config_rejects_invalid_json():
    with pytest.raises(validator.ValidationError, match="JSON inválido"):
        validator.validate_config(_env(GTI_GOOGLE_SERVICE_ACCOUNT_JSON="{"))


def test_google_config_rejects_sheet_url_instead_of_id():
    with pytest.raises(validator.ValidationError, match="somente o ID"):
        validator.validate_config(
            _env(GTI_GOOGLE_SPREADSHEET_ID="https://docs.google.com/spreadsheets/d/" + "a" * 44)
        )


def test_google_readonly_validation_does_not_call_write_methods():
    calls = {"opened": None, "writes": 0}

    class Spreadsheet:
        def worksheets(self):
            return ["Inventário"]

        def update(self, *_args, **_kwargs):
            calls["writes"] += 1

    class Client:
        def open_by_key(self, spreadsheet_id):
            calls["opened"] = spreadsheet_id
            return Spreadsheet()

    result = validator.validate_readonly(
        _env(),
        credentials_factory=lambda info, scopes: object(),
        authorizer=lambda credentials: Client(),
    )
    assert result["worksheet_count"] == 1
    assert calls["opened"] == "a" * 44
    assert calls["writes"] == 0
