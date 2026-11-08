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


def _drive_factory(can_edit=True):
    class Request:
        def execute(self):
            return {
                "capabilities": {
                    "canEdit": can_edit,
                    "canModifyContent": can_edit,
                }
            }

    class Files:
        def get(self, **kwargs):
            assert kwargs["supportsAllDrives"] is True
            assert "capabilities(canEdit,canModifyContent)" in kwargs["fields"]
            return Request()

    class Drive:
        def files(self):
            return Files()

    return lambda *args, **kwargs: Drive()


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


def test_google_readonly_validation_checks_editor_capability_without_writes():
    calls = {"opened": None, "writes": 0, "scopes": None}

    class Spreadsheet:
        def worksheets(self):
            return ["Inventário"]

        def update(self, *_args, **_kwargs):
            calls["writes"] += 1

    class Client:
        def open_by_key(self, spreadsheet_id):
            calls["opened"] = spreadsheet_id
            return Spreadsheet()

    def credentials_factory(info, scopes):
        calls["scopes"] = scopes
        return object()

    result = validator.validate_readonly(
        _env(),
        credentials_factory=credentials_factory,
        authorizer=lambda credentials: Client(),
        drive_factory=_drive_factory(),
    )
    assert result["worksheet_count"] == 1
    assert calls["opened"] == "a" * 44
    assert calls["writes"] == 0
    assert "https://www.googleapis.com/auth/spreadsheets.readonly" in calls["scopes"]
    assert "https://www.googleapis.com/auth/drive.metadata.readonly" in calls["scopes"]


def test_google_validation_rejects_service_account_without_editor_capability():
    with pytest.raises(validator.ValidationError, match="permissão de edição"):
        validator.validate_readonly(
            _env(),
            credentials_factory=lambda info, scopes: object(),
            authorizer=lambda credentials: type(
                "Client",
                (),
                {"open_by_key": lambda self, _key: type(
                    "Spreadsheet", (), {"worksheets": lambda self: ["Inventário"]}
                )()},
            )(),
            drive_factory=_drive_factory(can_edit=False),
        )
