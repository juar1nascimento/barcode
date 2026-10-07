"""Worker idempotente para sincronizar patrimônios do PostgreSQL com Google Sheets.

Uso em CI/cron:
  DATABASE_URL=... GOOGLE_SERVICE_ACCOUNT_JSON=... \
  GOOGLE_SPREADSHEET_ID=... python inventario_sheets_outbox_worker.py
"""
from __future__ import annotations

import json
import os
import re
import time

import gspread
import psycopg
from google.oauth2.service_account import Credentials

CANONICAL_REQUIRED = [
    "Setor",
    "Tipo de Patrimônio",
    "Nº de Patrimônio",
    "Fabricante",
    "Data Cadastro",
]
HEADER_ALIASES = {
    "setor": "Setor",
    "tipo de patrimonio": "Tipo de Patrimônio",
    "tipo patrimonio": "Tipo de Patrimônio",
    "n de patrimonio": "Nº de Patrimônio",
    "n patrimonio": "Nº de Patrimônio",
    "numero de patrimonio": "Nº de Patrimônio",
    "numero patrimonio": "Nº de Patrimônio",
    "fabricante": "Fabricante",
    "data cadastro": "Data Cadastro",
    "data de cadastro": "Data Cadastro",
}

def _header_key(value: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _canonical_header_positions(header: list[str]) -> dict[str, int]:
    positions = {}
    for index, value in enumerate(header):
        canonical = HEADER_ALIASES.get(_header_key(value), str(value or "").strip())
        if canonical in CANONICAL_REQUIRED and canonical not in positions:
            positions[canonical] = index
    return positions


def _row_value(row: list[str], index: int) -> str:
    return str(row[index]).strip() if index < len(row) else ""


def sync_one(conn, spreadsheet, patrimonio_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id,p.numero_patrimonio,p.codigo_barras,
                      COALESCE(NULLIF(p.tipo_custom, ''), p.tipo) AS tipo,
                      p.fabricante,p.data_cadastro,u.nome,s.nome
                 FROM public.patrimonios p
                 JOIN public.unidades u ON u.id=p.unidade_id
                 JOIN public.setores s ON s.id=p.setor_id
                WHERE p.id=%s""",
            (patrimonio_id,),
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError(f"Patrimônio {patrimonio_id} não encontrado.")

    _, numero, _codigo, tipo, fabricante, data_cadastro, unidade, setor = row
    aba = spreadsheet.worksheet(normalize_unit(unidade))
    values = aba.get_all_values()

    if not values:
        raise RuntimeError(
            f"Aba {unidade} está vazia: o worker não cria nem reestrutura cabeçalhos."
        )

    header = [str(value or "").strip() for value in values[0]]
    positions = _canonical_header_positions(header)
    missing = [column for column in CANONICAL_REQUIRED if column not in positions]
    if missing:
        raise RuntimeError(
            f"Aba {unidade} não possui o contrato mínimo do inventário: "
            f"{', '.join(missing)}. Nenhuma alteração estrutural foi realizada."
        )

    numero = str(numero or "").strip()
    setor = str(setor or "").strip()
    tipo = str(tipo or "").strip()
    fabricante = str(fabricante or "").strip()
    data_texto = data_cadastro.isoformat(sep=" ") if hasattr(data_cadastro, "isoformat") else str(data_cadastro or "").strip()
    esperado = {
        "Setor": setor,
        "Tipo de Patrimônio": tipo,
        "Nº de Patrimônio": numero,
        "Fabricante": fabricante,
        "Data Cadastro": data_texto,
    }

    numero_col = positions["Nº de Patrimônio"]
    row_number = None
    compact_expected = re.sub(r"\s+", " ", numero).casefold()
    for idx, existing in enumerate(values[1:], start=2):
        current = _row_value(existing, numero_col)
        if re.sub(r"\s+", " ", current).casefold() == compact_expected:
            row_number = idx
            break

    if row_number is None:
        largura = max(len(header), max(positions.values()) + 1)
        nova_linha = [""] * largura
        for column, value in esperado.items():
            nova_linha[positions[column]] = value
        aba.append_rows([nova_linha], value_input_option="RAW")
        row_number = len(aba.get_all_values())
    else:
        for column, value in esperado.items():
            column_number = positions[column] + 1
            aba.update_cell(row_number, column_number, value)

    # Confirma somente as células que o worker escreveu. Colunas como
    # Origem, Status, ID Patrimônio e Fotos permanecem intocadas.
    confirmada = aba.get(
        f"A{row_number}:{col_letter(max(len(header), max(positions.values()) + 1))}{row_number}"
    )
    linha = list(confirmada[0]) if confirmada else []
    for column, value in esperado.items():
        atual = _row_value(linha, positions[column])
        if atual != value:
            raise RuntimeError(
                f"Google Sheets não confirmou {column} do patrimônio {patrimonio_id}: "
                f"esperado={value!r}, recebido={atual!r}"
            )


def main():
    limit = max(1, int(os.getenv("OUTBOX_BATCH_SIZE", "20")))
    max_attempts = max(1, int(os.getenv("OUTBOX_MAX_ATTEMPTS", "8")))
    conn = psycopg.connect(env("DATABASE_URL"))
    try:
        reset_stale(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public.reconcile_patrimonios_sheets_outbox(%s)",
                (limit * 5,),
            )
            reconciled = int(cur.fetchone()[0] or 0)
        conn.commit()

        spreadsheet = open_spreadsheet(sheets_client())
        claimed = claim_batch(conn, limit)

        synced = failed = 0
        for outbox_id, patrimonio_id in claimed:
            started = time.monotonic()
            try:
                sync_one(conn, spreadsheet, int(patrimonio_id))
                mark(conn, int(outbox_id), "synced")
                synced += 1
                print(json.dumps({
                    "event": "patrimonios_sheets_outbox",
                    "outbox_id": int(outbox_id),
                    "patrimonio_id": int(patrimonio_id),
                    "result": "synced",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }, ensure_ascii=False))
            except Exception as exc:
                mark(conn, int(outbox_id), "failed", safe_error(exc), max_attempts)
                failed += 1
                print(json.dumps({
                    "event": "patrimonios_sheets_outbox",
                    "outbox_id": int(outbox_id),
                    "patrimonio_id": int(patrimonio_id),
                    "result": "failed",
                    "error": safe_error(exc),
                }, ensure_ascii=False))

        print(json.dumps({
            "event": "patrimonios_sheets_outbox_batch",
            "reconciled": reconciled,
            "claimed": len(claimed),
            "synced": synced,
            "failed": failed,
            "max_attempts": max_attempts,
        }, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
