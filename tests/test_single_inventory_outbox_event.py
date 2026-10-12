import pytest

from scripts.sync_single_inventory_outbox_event import classificar_falha, validar_modo


def test_single_event_defaults_to_read_only():
    validar_modo(False, False)


def test_write_requires_explicit_confirmation():
    with pytest.raises(ValueError, match="--confirm-write"):
        validar_modo(True, False)


def test_confirmation_without_execute_is_rejected():
    with pytest.raises(ValueError, match="--execute"):
        validar_modo(False, True)


def test_failed_event_becomes_dead_letter_at_attempt_limit():
    assert classificar_falha(4, 5) == "failed"
    assert classificar_falha(5, 5) == "dead_letter"
