from auditoria_analitica_readonly import _ler_sheets, comparar, normalizar_cabecalho


def test_normalizar_cabecalho_aceita_colunas_legadas_de_foto():
    assert normalizar_cabecalho("Foto 1") == "Foto 01"
    assert normalizar_cabecalho("foto 10") == "Foto 10"
    assert normalizar_cabecalho("Nº de Patrimônio") == "Nº de Patrimônio"


def test_comparar_detecta_divergencia_de_campo_por_id_estavel():
    patrimonios = [{
        "id": "7", "numero": "0007", "tipo": "CPU", "unidade": "Unidade A",
        "setor": "TI", "fabricante": "Marca A", "codigo_barras": "0007",
        "data_cadastro": "", "ativo": True,
    }]
    fotos = [{
        "id": "31", "patrimonio_id": "7", "ordem": 1,
        "storage_path_present": True, "storage_bucket": "patrimonio-fotos",
        "drive_url_present": True, "drive_name_present": True,
        "patrimonio_exists": True,
    }]
    sheet_rows = [{
        "id": "7", "numero": "0007", "unidade": "Unidade A",
        "setor": "Administrativo", "tipo": "CPU", "fabricante": "Marca A",
        "codigo_barras": "0007", "data_cadastro": "",
        "photo_cells_filled": 1, "tab": "Unidade A", "row": 2,
    }]
    schema = {"active_status_available": True, "schema_missing": []}
    sheet_report = {"tabs_scanned": 1, "tabs_skipped": [], "tab_issues": []}

    report = comparar(patrimonios, fotos, sheet_rows, schema, sheet_report)

    assert report["counts"]["matched_postgres_ids"] == 1
    assert report["issues"]["field_differences_by_stable_id"] == [{
        "id": "7", "tab": "Unidade A", "row": 2, "field": "setor",
        "sheet_value": "Administrativo", "postgres_value": "TI",
    }]
    assert report["blocking_issue_count"] == 1


def test_comparar_nao_classifica_foto_de_patrimonio_inativo_como_orfa():
    patrimonios = []
    fotos = [{
        "id": "31", "patrimonio_id": "7", "ordem": 1,
        "storage_path_present": True, "storage_bucket": "patrimonio-fotos",
        "drive_url_present": True, "drive_name_present": True,
        "patrimonio_exists": True,
    }]
    schema = {"active_status_available": True, "schema_missing": []}
    sheet_report = {"tabs_scanned": 0, "tabs_skipped": [], "tab_issues": []}

    report = comparar(patrimonios, fotos, [], schema, sheet_report)

    assert report["issues"]["orphan_photo_records"] == []
    assert report["issues"]["photo_records_without_drive_url"] == []


def test_comparar_detecta_divergencias_em_linha_legada_sem_id_estavel():
    patrimonios = [{
        "id": "7", "numero": "0007", "tipo": "CPU", "unidade": "Unidade A",
        "setor": "TI", "fabricante": "Marca A", "codigo_barras": "0007",
        "data_cadastro": "", "ativo": True,
    }]
    fotos = [{
        "id": "31", "patrimonio_id": "7", "ordem": 1,
        "storage_path_present": True, "storage_bucket": "patrimonio-fotos",
        "drive_url_present": True, "drive_name_present": True,
        "patrimonio_exists": True,
    }]
    sheet_rows = [{
        "id": "", "numero": "0007", "unidade": "Unidade A",
        "setor": "Administrativo", "tipo": "CPU", "fabricante": "Marca A",
        "codigo_barras": "0007", "data_cadastro": "",
        "photo_cells_filled": 0, "tab": "Unidade A", "row": 2,
    }]
    schema = {"active_status_available": True, "schema_missing": []}
    sheet_report = {"tabs_scanned": 1, "tabs_skipped": [], "tab_issues": []}

    report = comparar(patrimonios, fotos, sheet_rows, schema, sheet_report)

    assert report["counts"]["matched_postgres_ids"] == 1
    assert report["issues"]["field_differences_by_stable_id"] == [{
        "id": "7", "tab": "Unidade A", "row": 2, "field": "setor",
        "sheet_value": "Administrativo", "postgres_value": "TI",
    }]
    assert report["issues"]["photo_count_differences_by_stable_id"] == [{
        "id": "7", "tab": "Unidade A", "row": 2,
        "sheets_photo_cells": 0, "postgres_photo_records": 1,
    }]
    assert report["blocking_issue_count"] == 2


def test_comparar_nao_parea_por_numero_duplicado():
    patrimonios = [
        {"id": "7", "numero": "0007", "tipo": "CPU", "unidade": "Unidade A",
         "setor": "TI", "fabricante": "", "codigo_barras": "", "data_cadastro": "", "ativo": True},
        {"id": "8", "numero": "0007", "tipo": "Monitor", "unidade": "Unidade A",
         "setor": "TI", "fabricante": "", "codigo_barras": "", "data_cadastro": "", "ativo": True},
    ]
    sheet_rows = [{
        "id": "", "numero": "0007", "unidade": "Unidade A",
        "setor": "TI", "tipo": "CPU", "fabricante": "",
        "codigo_barras": "", "data_cadastro": "", "photo_cells_filled": 0,
        "tab": "Unidade A", "row": 2,
    }]
    schema = {"active_status_available": True, "schema_missing": []}
    sheet_report = {"tabs_scanned": 1, "tabs_skipped": [], "tab_issues": []}

    report = comparar(patrimonios, [], sheet_rows, schema, sheet_report)

    assert report["issues"]["ambiguous_fallback_rows"] == [{
        "tab": "Unidade A", "row": 2, "reason": "missing_id_and_number_not_unique",
    }]
    assert report["counts"]["matched_postgres_ids"] == 0



def test_ler_sheets_classifica_aba_nao_vazia_sem_coluna_de_patrimonio_como_incompleta():
    class Worksheet:
        title = "Resumo auxiliar"

        def get_all_values(self, value_render_option):
            return [["Indicador", "Valor"], ["Total", "42"]]

    class Spreadsheet:
        def worksheets(self):
            return [Worksheet()]

    rows, report = _ler_sheets(Spreadsheet())

    assert rows == []
    assert report["unclassified_nonempty_tabs"] == ["Resumo auxiliar"]
    assert {"tab": "Resumo auxiliar", "issue": "unclassified_nonempty_tab"} in report["tab_issues"]


def test_ler_sheets_nao_classifica_aba_vazia_como_bloqueio_de_cobertura():
    class Worksheet:
        title = "Aba vazia"

        def get_all_values(self, value_render_option):
            return []

    class Spreadsheet:
        def worksheets(self):
            return [Worksheet()]

    rows, report = _ler_sheets(Spreadsheet())

    assert rows == []
    assert report["unclassified_nonempty_tabs"] == []
    assert report["tabs_skipped"] == [{"tab": "Aba vazia", "reason": "empty"}]
