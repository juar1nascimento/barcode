"""Testes locais e sem credenciais para o downloader seguro de fotos do Drive."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "download_drive_photos_local.py"
SPEC = importlib.util.spec_from_file_location("download_drive_photos_local", SCRIPT)
downloader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(downloader)


def test_safe_component_neutraliza_traversal_e_caracteres_invalidos():
    assert downloader.safe_component("../foto:1?.jpg") == ".._foto_1_.jpg"
    assert downloader.safe_component("..") == "_sem_nome"
    assert "/" not in downloader.safe_component("unidade/saude")


def test_unique_names_diferencia_arquivos_com_nome_repetido():
    items = [
        {"id": "abc123456", "name": "foto.jpg"},
        {"id": "def987654", "name": "foto.jpg"},
    ]
    result = downloader.unique_names(items)
    assert result["abc123456"] == "foto.jpg__abc12345"
    assert result["def987654"] == "foto.jpg__def98765"


def test_drive_service_bloqueia_sem_credencial(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)
    with pytest.raises(RuntimeError, match="Configure GOOGLE_SERVICE_ACCOUNT_FILE"):
        downloader.drive_service()


def test_list_children_pagina_ate_o_fim():
    service = Mock()
    first = service.files.return_value.list.return_value
    first.execute.side_effect = [
        {"files": [{"id": "1"}], "nextPageToken": "pagina-2"},
        {"files": [{"id": "2"}]},
    ]
    result = downloader.list_children(service, "folder-id")
    assert result == [{"id": "1"}, {"id": "2"}]
    assert service.files.return_value.list.call_count == 2


def test_nao_classifica_documentos_como_imagens():
    items = [
        {"id": "1", "name": "foto.jpg", "mimeType": "image/jpeg"},
        {"id": "2", "name": "relatorio.pdf", "mimeType": "application/pdf"},
        {"id": "3", "name": "planilha", "mimeType": "application/vnd.google-apps.spreadsheet"},
    ]
    images = [
        item for item in items
        if str(item.get("mimeType", "")).startswith(downloader.IMAGE_PREFIX)
        and not item.get("shortcutDetails")
    ]
    assert [item["name"] for item in images] == ["foto.jpg"]
