from auditoria_analitica_readonly import comparar, normalizar_cabecalho


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
