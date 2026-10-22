"""Auditoria analítica somente leitura: PostgreSQL/Supabase ↔ Google Sheets.

Este utilitário não executa INSERT/UPDATE/DELETE, não altera abas e não imprime
URLs de fotos nem credenciais. Use uma credencial PostgreSQL com permissão SELECT
e uma conta Google com acesso somente leitura à planilha.

Variáveis:
  DATABASE_URL
  GOOGLE_SERVICE_ACCOUNT_JSON
  GOOGLE_SPREADSHEET_ID (preferencial) ou GOOGLE_SPREADSHEET_URL

Execução:
  python auditoria_analitica_readonly.py > auditoria_analitica.json

Código de saída:
  0 = auditoria executada sem divergências bloqueantes
  1 = divergências de dados encontradas
  2 = auditoria incompleta / pré-requisitos ausentes
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter
from typing import Any

import gspread
import psycopg
from google.oauth2.service_account import Credentials


SHEET_ID_HEADER = "ID Patrimônio"
SHEET_NUMBER_HEADER = "Nº de Patrimônio"
SHEET_PHOTO_HEADERS = {f"Foto {n:02d}" for n in range(1, 11)}
SHEET_NUMBER_ALIASES = {"nº de patrimônio", "n° de patrimônio", "numero de patrimonio", "n de patrimonio"}


def normalizar_texto(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def normalizar_cabecalho(valor: Any) -> str:
    chave = normalizar_texto(valor)
    if chave in SHEET_NUMBER_ALIASES:
        return SHEET_NUMBER_HEADER
    return str(valor or "").strip()


def _obter_colunas(conn, tabela: str) -> set[str]:
    rows = conn.execute(
        """SELECT column_name
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s""",
        (tabela,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _tabela_existe(conn, tabela: str) -> bool:
    row = conn.execute(
        """SELECT EXISTS (
             SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = %s
           )""",
        (tabela,),
    ).fetchone()
    return bool(row and row[0])


def _conectar_postgres():
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn or dsn.upper() == "URL":
        raise RuntimeError("DATABASE_URL ausente ou contém placeholder.")
    conn = psycopg.connect(dsn, connect_timeout=10)
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET statement_timeout = '30s'")
    return conn


def _conectar_sheets():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON ausente.")
    data = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly",
              "https://www.googleapis.com/auth/drive.readonly"]
    client = gspread.authorize(Credentials.from_service_account_info(data, scopes=scopes))
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    spreadsheet_url = os.getenv("GOOGLE_SPREADSHEET_URL", "").strip()
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    if spreadsheet_url:
        return client.open_by_url(spreadsheet_url)
    raise RuntimeError("Defina GOOGLE_SPREADSHEET_ID ou GOOGLE_SPREADSHEET_URL.")


def _ler_postgres(conn) -> tuple[list[dict], list[dict], dict]:
    report = {"schema_missing": [], "active_status_available": False}
    required = {"patrimonios": {"id", "unidade_id", "setor_id", "tipo", "numero_patrimonio"},
                "unidades": {"id", "nome"},
                "setores": {"id", "nome", "unidade_id"},
                "patrimonio_fotos": {"id", "patrimonio_id", "ordem", "storage_path"}}
    cols = {}
    for table, needed in required.items():
        if not _tabela_existe(conn, table):
            report["schema_missing"].append(f"public.{table}")
            continue
        cols[table] = _obter_colunas(conn, table)
        missing = sorted(needed - cols[table])
        report["schema_missing"].extend(f"public.{table}.{name}" for name in missing)
    if report["schema_missing"]:
        return [], [], report

    pcols = cols["patrimonios"]
    report["active_status_available"] = "ativo" in pcols
    select_fields = [
        "p.id", "p.numero_patrimonio", "p.tipo", "u.nome AS unidade",
        "s.nome AS setor",
        "COALESCE(p.fabricante, '') AS fabricante" if "fabricante" in pcols else "'' AS fabricante",
        "COALESCE(p.codigo_barras, '') AS codigo_barras" if "codigo_barras" in pcols else "'' AS codigo_barras",
        "p.data_cadastro" if "data_cadastro" in pcols else "NULL AS data_cadastro",
        "p.ativo" if "ativo" in pcols else "TRUE AS ativo",
    ]
    active_filter = "WHERE p.ativo IS TRUE" if "ativo" in pcols else ""
    rows = conn.execute(
        f"""SELECT {', '.join(select_fields)}
              FROM public.patrimonios p
              JOIN public.unidades u ON u.id = p.unidade_id
              LEFT JOIN public.setores s ON s.id = p.setor_id
              {active_filter}
             ORDER BY p.id"""
    ).fetchall()
    patrimonios = [{
        "id": str(row[0]), "numero": str(row[1] or "").strip(),
        "tipo": str(row[2] or "").strip(), "unidade": str(row[3] or "").strip(),
        "setor": str(row[4] or "").strip(), "fabricante": str(row[5] or "").strip(),
        "codigo_barras": str(row[6] or "").strip(),
        "data_cadastro": row[7].isoformat() if row[7] is not None else "",
        "ativo": bool(row[8]),
    } for row in rows]

    fcols = cols["patrimonio_fotos"]
    photo_select = ["id", "patrimonio_id", "ordem", "storage_path"]
    photo_select += ["storage_bucket"] if "storage_bucket" in fcols else ["'patrimonio-fotos' AS storage_bucket"]
    photo_select += ["drive_web_url"] if "drive_web_url" in fcols else ["NULL AS drive_web_url"]
    photo_select += ["drive_file_name"] if "drive_file_name" in fcols else ["NULL AS drive_file_name"]
    photo_rows = conn.execute(
        f"SELECT {', '.join(photo_select)} FROM public.patrimonio_fotos ORDER BY patrimonio_id, ordem, id"
    ).fetchall()
    fotos = [{
        "id": str(row[0]), "patrimonio_id": str(row[1]), "ordem": int(row[2]),
        "storage_path_present": bool(str(row[3] or "").strip()),
        "storage_bucket": str(row[4] or ""),
        "drive_url_present": bool(str(row[5] or "").strip()),
        "drive_name_present": bool(str(row[6] or "").strip()),
    } for row in photo_rows]
    return patrimonios, fotos, report


def _ler_sheets(spreadsheet) -> tuple[list[dict], dict]:
    rows = []
    report = {"tabs_scanned": 0, "tabs_skipped": [], "tab_issues": []}
    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values()
        if not values:
            report["tabs_skipped"].append({"tab": worksheet.title, "reason": "empty"})
            continue
        header = [normalizar_cabecalho(v) for v in values[0]]
        if SHEET_NUMBER_HEADER not in header:
            report["tabs_skipped"].append({"tab": worksheet.title, "reason": "no inventory number column"})
            continue
        report["tabs_scanned"] += 1
        if len(header) != len(set(header)):
            report["tab_issues"].append({"tab": worksheet.title, "issue": "duplicate_headers"})
        if header.count(SHEET_NUMBER_HEADER) != 1:
            report["tab_issues"].append({"tab": worksheet.title, "issue": "ambiguous_number_header"})
            continue
        idx = {name: i for i, name in enumerate(header) if name}
        for sheet_row_number, values_row in enumerate(values[1:], start=2):
            def cell(name: str) -> str:
                i = idx.get(name)
                return str(values_row[i] if i is not None and i < len(values_row) else "").strip()
            number = cell(SHEET_NUMBER_HEADER)
            if not number:
                if any(str(v).strip() for v in values_row):
                    report["tab_issues"].append({"tab": worksheet.title, "row": sheet_row_number, "issue": "missing_asset_number"})
                continue
            photo_cells = [cell(name) for name in header if name in SHEET_PHOTO_HEADERS]
            rows.append({
                "id": cell(SHEET_ID_HEADER), "numero": number,
                "unidade": worksheet.title, "setor": cell("Setor"),
                "tipo": cell("Tipo de Patrimônio"), "fabricante": cell("Fabricante"),
                "codigo_barras": cell("Código de Barras"),
                "data_cadastro": cell("Data Cadastro"),
                "photo_cells_filled": sum(bool(x) for x in photo_cells),
                "tab": worksheet.title, "row": sheet_row_number,
            })
    return rows, report


def _duplicados(valores: list[str]) -> list[str]:
    contagem = Counter(v for v in valores if v)
    return sorted(k for k, n in contagem.items() if n > 1)


def comparar(patrimonios: list[dict], fotos: list[dict], sheet_rows: list[dict], schema: dict, sheet_report: dict) -> dict:
    pg_by_id = {p["id"]: p for p in patrimonios}
    pg_ids = [p["id"] for p in patrimonios]
    sheet_ids = [r["id"] for r in sheet_rows if r["id"]]
    sheet_numbers = [normalizar_texto(r["numero"]) for r in sheet_rows]
    pg_numbers = [normalizar_texto(p["numero"]) for p in patrimonios]
    pg_number_counts = Counter(x for x in pg_numbers if x)
    sheet_number_counts = Counter(x for x in sheet_numbers if x)
    duplicate_sheet_ids = _duplicados(sheet_ids)
    duplicate_sheet_numbers = sorted(k for k, n in sheet_number_counts.items() if k and n > 1)
    duplicate_pg_numbers = sorted(k for k, n in pg_number_counts.items() if k and n > 1)

    matched_pg_ids = set()
    unmatched_sheet_rows = []
    ambiguous_number_matches = []
    for row in sheet_rows:
        stable_id = row["id"]
        if stable_id:
            if stable_id in pg_by_id:
                matched_pg_ids.add(stable_id)
            else:
                unmatched_sheet_rows.append({"tab": row["tab"], "row": row["row"], "reason": "unknown_or_inactive_id"})
            continue
        number_key = normalizar_texto(row["numero"])
        if number_key and pg_number_counts[number_key] == 1 and sheet_number_counts[number_key] == 1:
            match = next(p for p in patrimonios if normalizar_texto(p["numero"]) == number_key)
            matched_pg_ids.add(match["id"])
        else:
            ambiguous_number_matches.append({"tab": row["tab"], "row": row["row"], "reason": "missing_id_and_number_not_unique"})

    photos_orphaned = [f["id"] for f in fotos if f["patrimonio_id"] not in pg_by_id]
    photo_counts = Counter(f["patrimonio_id"] for f in fotos)
    sheet_counts_by_id = Counter(r["id"] for r in sheet_rows if r["id"])
    sheet_photo_cells = sum(r["photo_cells_filled"] for r in sheet_rows)

    issues = {
        "duplicate_sheet_ids": duplicate_sheet_ids,
        "duplicate_sheet_numbers_normalized": duplicate_sheet_numbers,
        "duplicate_postgres_numbers_normalized": duplicate_pg_numbers,
        "postgres_patrimonios_missing_from_sheets": sorted(set(pg_ids) - matched_pg_ids),
        "sheet_rows_not_matched_to_postgres": unmatched_sheet_rows,
        "ambiguous_fallback_rows": ambiguous_number_matches,
        "photo_records_without_storage_path": [f["id"] for f in fotos if not f["storage_path_present"]],
        "photo_records_without_drive_url": [f["id"] for f in fotos if not f["drive_url_present"]],
        "orphan_photo_records": photos_orphaned,
        "patrimonios_without_photo": sorted(p["id"] for p in patrimonios if photo_counts[p["id"]] == 0),
    }
    blockers = sum(len(v) for v in issues.values())
    return {
        "audit_mode": "read_only",
        "postgres_active_filter_available": schema["active_status_available"],
        "postgres_schema_missing": schema["schema_missing"],
        "sheets": sheet_report,
        "counts": {
            "postgres_patrimonios": len(patrimonios),
            "sheets_inventory_rows": len(sheet_rows),
            "matched_postgres_ids": len(matched_pg_ids),
            "postgres_photos": len(fotos),
            "sheets_nonempty_photo_cells": sheet_photo_cells,
        },
        "issues": issues,
        "blocking_issue_count": blockers + len(schema["schema_missing"]) + len(sheet_report["tab_issues"]),
        "notes": [
            "A auditoria não escreve em PostgreSQL, Google Sheets ou Storage.",
            "URLs e credenciais não são incluídas no relatório.",
            "Células de foto no Sheets podem conter fórmulas IMAGE/HYPERLINK e não são prova independente do acesso ao arquivo.",
            "Ausência de coluna ativo no schema significa que não foi possível restringir a comparação aos registros ativos.",
        ],
    }


def main() -> int:
    try:
        spreadsheet = _conectar_sheets()
        with _conectar_postgres() as conn:
            patrimonios, fotos, schema = _ler_postgres(conn)
        sheet_rows, sheet_report = _ler_sheets(spreadsheet)
        report = comparar(patrimonios, fotos, sheet_rows, schema, sheet_report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["postgres_schema_missing"]:
            return 2
        if report["blocking_issue_count"]:
            return 1
        return 0
    except Exception as exc:
        # Mensagem de erro controlada; não imprimir DSN, token ou URL da foto.
        print(json.dumps({
            "audit_mode": "read_only",
            "complete": False,
            "error_type": type(exc).__name__,
            "error": "Auditoria incompleta; verifique credenciais de leitura, conectividade e permissões.",
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
