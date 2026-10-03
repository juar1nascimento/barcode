from inventario_sheets_outbox_worker import COLUNAS, migrate_legacy_cpu_sheet


def test_migrate_legacy_cpu_sheet_preserves_values_and_expands_schema():
    values = [
        ["Setor", "CPU Nº de Patrimônio", "Fabricante CPU"],
        ["Sala de Preparo", "5465465", "dell"],
        ["Recepção", "1234567", "HP"],
    ]

    assert migrate_legacy_cpu_sheet(values) == [
        COLUNAS,
        ["Sala de Preparo", "", "5465465", "dell", ""],
        ["Recepção", "", "1234567", "HP", ""],
    ]


def test_migrate_legacy_cpu_sheet_rejects_unknown_structure():
    values = [
        ["Setor", "Nº de Patrimônio", "Fabricante"],
        ["Sala", "1", "Dell"],
    ]

    try:
        migrate_legacy_cpu_sheet(values)
    except ValueError as exc:
        assert "Estrutura legada" in str(exc)
    else:
        raise AssertionError("estrutura não reconhecida foi aceita")
