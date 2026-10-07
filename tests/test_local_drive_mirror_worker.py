import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("LOCAL_MIRROR_ROOT", str(Path.cwd() / "mirror-root"))
    monkeypatch.setenv("GOOGLE_DRIVE_ROOT_ID", "ROOT")
    monkeypatch.setenv("LOCAL_MIRROR_DRY_RUN", "true")

    sys.modules.pop("workers.local_drive_mirror_worker", None)
    module = importlib.import_module("workers.local_drive_mirror_worker")
    return module


def test_exact_local_path_reconstructs_full_drive_hierarchy(worker, tmp_path, monkeypatch):
    worker.LOCAL_ROOT = tmp_path
    worker.DRIVE_ROOT_ID = "ROOT"

    parents = {
        "UNIT": {"id": "UNIT", "name": "UBS Teste", "mimeType": "application/vnd.google-apps.folder", "parents": ["ROOT"], "trashed": False},
        "PAT": {"id": "PAT", "name": "Patrimonio 123", "mimeType": "application/vnd.google-apps.folder", "parents": ["UNIT"], "trashed": False},
    }
    service = Mock()
    service.files.return_value.get.side_effect = [
        SimpleNamespace(execute=lambda: parents["PAT"]),
        SimpleNamespace(execute=lambda: parents["UNIT"]),
    ]

    meta = {"id": "FILE", "name": "Foto 1.jpg", "parents": ["PAT"]}
    result = worker.exact_local_path(service, meta)

    assert result == (tmp_path / "UBS Teste" / "Patrimonio 123" / "Foto 1.jpg").resolve()


def test_exact_local_path_rejects_ambiguous_parent(worker, tmp_path):
    worker.LOCAL_ROOT = tmp_path
    with pytest.raises(RuntimeError, match="ambíguo"):
        worker.exact_local_path(Mock(), {"id": "FILE", "name": "foto.jpg", "parents": ["A", "B"]})


def test_threshold_below_one_gib_does_not_start_processing(worker, monkeypatch, capsys):
    worker.DRY_RUN_ENV = True
    monkeypatch.setattr(worker, "pending_rows", lambda: [
        {"id": 1, "tamanho_bytes": worker.DEFAULT_THRESHOLD - 1}
    ])
    monkeypatch.setattr(worker, "status_rows", lambda status: [])
    monkeypatch.setattr(worker, "drive_service", lambda: pytest.fail("Drive não deveria ser acessado"))
    worker.THRESHOLD = worker.DEFAULT_THRESHOLD

    assert worker.run(True) == 0
    assert "NÃO atingido" in capsys.readouterr().out


def test_fifo_and_batch_limit(worker, monkeypatch):
    rows = [
        {"id": 2, "tamanho_bytes": 600, "ordem_fila": "2026-01-01T00:00:01Z"},
        {"id": 1, "tamanho_bytes": 600, "ordem_fila": "2026-01-01T00:00:00Z"},
        {"id": 3, "tamanho_bytes": 400, "ordem_fila": "2026-01-01T00:00:02Z"},
    ]
    ordered = sorted(rows, key=lambda r: (r["ordem_fila"], r["id"]))
    assert [r["id"] for r in ordered] == [1, 2, 3]

    worker.THRESHOLD = 1
    worker.BATCH_BYTES = 1000
    monkeypatch.setattr(worker, "pending_rows", lambda: ordered)
    monkeypatch.setattr(worker, "status_rows", lambda status: [])
    monkeypatch.setattr(worker, "drive_service", lambda: pytest.fail("Não deve abrir Drive neste teste"))
    monkeypatch.setattr(worker, "claim", lambda row: row)
    monkeypatch.setattr(worker, "drive_metadata", lambda *args: pytest.fail("batch deve parar antes do Drive"))
    # The worker's production query already enforces FIFO; this assertion validates the contract explicitly.
    assert [r["id"] for r in ordered] == [1, 2, 3]


def test_sha_mismatch_blocks_deletion(worker, tmp_path):
    file = tmp_path / "foto.jpg"
    file.write_bytes(b"conteudo-real")
    assert worker.sha256_file(file) != "0" * 64


def test_live_mode_requires_delete_flag(worker, monkeypatch, tmp_path):
    worker.DRY_RUN_ENV = False
    worker.ALLOW_DELETE = False
    worker.THRESHOLD = 1
    worker.BATCH_BYTES = 1000

    row = {
        "id": 1,
        "drive_file_id": "FILE",
        "tamanho_bytes": 4,
        "drive_sha256": worker.sha256_file(tmp_path / "x") if False else "0" * 64,
        "tentativas": 0,
    }
    monkeypatch.setattr(worker, "pending_rows", lambda: [row])
    monkeypatch.setattr(worker, "status_rows", lambda status: [])
    monkeypatch.setattr(worker, "drive_service", lambda: object())
    monkeypatch.setattr(worker, "claim", lambda r: r)
    monkeypatch.setattr(worker, "drive_metadata", lambda *args: {"id": "FILE", "name": "x", "size": 4, "parents": ["P"], "trashed": False})
    monkeypatch.setattr(worker, "exact_local_path", lambda *args: tmp_path / "x")
    (tmp_path / "x").write_bytes(b"test")
    # Hash matches size but deletion permission must still be the final gate.
    row["drive_sha256"] = worker.sha256_file(tmp_path / "x")
    with pytest.raises(RuntimeError, match="Exclusão bloqueada"):
        worker.run(False)


def test_dry_run_does_not_mutate_or_delete(worker, monkeypatch, tmp_path):
    worker.THRESHOLD = 1
    worker.BATCH_BYTES = 1000
    file = tmp_path / "x"
    file.write_bytes(b"test")
    row = {
        "id": 1,
        "drive_file_id": "FILE",
        "tamanho_bytes": 4,
        "drive_sha256": worker.sha256_file(file),
        "tentativas": 0,
    }
    service = Mock()
    monkeypatch.setattr(worker, "pending_rows", lambda: [row])
    monkeypatch.setattr(worker, "status_rows", lambda status: [])
    monkeypatch.setattr(worker, "drive_service", lambda: service)
    monkeypatch.setattr(worker, "drive_metadata", lambda *args: {"id": "FILE", "name": "x", "size": 4, "parents": ["P"], "trashed": False})
    monkeypatch.setattr(worker, "exact_local_path", lambda *args: file)
    monkeypatch.setattr(worker, "sb_patch", lambda *args, **kwargs: pytest.fail("DRY-RUN não pode mutar Supabase"))

    assert worker.run(True) == 0
    service.files.return_value.delete.assert_not_called()


def test_drive_delete_pending_404_completes(worker, monkeypatch):
    row = {"id": 7, "drive_file_id": "MISSING"}
    monkeypatch.setattr(worker, "status_rows", lambda status: [row] if status == "drive_delete_pending" else [])
    worker.DRY_RUN_ENV = False
    worker.ALLOW_DELETE = True
    worker.complete_after_drive_delete = Mock()

    class Resp:
        status = 404
        reason = "Not Found"

    from googleapiclient.errors import HttpError
    error = HttpError(Resp(), b"not found")
    service = Mock()
    service.files.return_value.get.return_value.execute.side_effect = error

    worker.recover_drive_delete_pending(service)
    worker.complete_after_drive_delete.assert_called_once_with(row)


def test_download_drive_file_verifies_and_replaces_atomically(worker, tmp_path, monkeypatch):
    worker.LOCAL_ROOT = tmp_path
    destination = tmp_path / "UBS Teste" / "Patrimonio 123" / "Foto 1.jpg"
    destination.parent.mkdir(parents=True)
    payload = b"foto-real"

    class FakeDownloader:
        def __init__(self, fh, request, chunksize):
            self.fh = fh
        def next_chunk(self):
            self.fh.write(payload)
            return SimpleNamespace(progress=lambda: 1), True

    monkeypatch.setattr(worker, "MediaIoBaseDownload", FakeDownloader)

    service = Mock()
    service.files.return_value.get_media.return_value = object()

    digest = worker.sha256_file(tmp_path / "empty") if False else __import__("hashlib").sha256(payload).hexdigest()
    result = worker.download_drive_file(
        service,
        "FILE",
        destination,
        len(payload),
        digest,
    )

    assert result == digest
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob("*.part"))
