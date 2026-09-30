"""Worker idempotente para sincronizar fotos do Supabase com Google Sheets.

Uso em CI/cron:
  DATABASE_URL=... GOOGLE_SERVICE_ACCOUNT_JSON=... \
  GOOGLE_SPREADSHEET_ID=... SUPABASE_URL=... \
  python sheets_outbox_worker.py
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

import gspread
import psycopg
from google.oauth2.service_account import Credentials


PHOTO_COLUMNS = [f"Foto {i}" for i in range(1, 11)]
ID_COLUMN = "ID Patrimônio"
BUCKET = "patrimonio-fotos"


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def col_letter(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def sheet_url(storage_path: str) -> str:
    base = env("SUPABASE_URL").rstrip("/")
    from urllib.parse import quote
    path = quote(str(storage_path).lstrip("/"), safe="/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


def normalize_unit(value: str) -> str:
    aliases = {"URS Jacara_pe": "URS Jacaraípe", "UBS Bairro de F_tima": "UBS Bairro de Fátima"}
    return aliases.get(str(value or "").strip(), str(value or "").strip())


def sheets_client():
    raw = env("GOOGLE_SERVICE_ACCOUNT_JSON")
    data = json.loads(raw)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    return gspread.authorize(Credentials.from_service_account_info(data, scopes=scopes))


def open_spreadsheet(client):
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    spreadsheet_url = os.getenv("GOOGLE_SPREADSHEET_URL", "").strip()
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    if spreadsheet_url:
        return client.open_by_url(spreadsheet_url)
    raise RuntimeError("Defina GOOGLE_SPREADSHEET_ID ou GOOGLE_SPREADSHEET_URL.")


def claim_batch(conn, limit: int):
    with conn.cursor() as cur:
        cur.execute(
            """WITH candidatos AS (
                 SELECT id
                   FROM public.patrimonio_fotos_sheets_outbox
                  WHERE status IN ('pending','failed')
                    AND proxima_tentativa_em <= now()
                  ORDER BY id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
               )
               UPDATE public.patrimonio_fotos_sheets_outbox o
                  SET status = 'processing',
                      processando_em = now(),
                      tentativas = tentativas + 1,
                      atualizado_em = now()
                 FROM candidatos c
                WHERE o.id = c.id
               RETURNING o.id, o.patrimonio_id, o.foto_id""",
            (limit,),
        )
        rows = cur.fetchall()
    conn.commit()
    return rows


def mark(conn, outbox_id: int, status: str, error: str | None = None):
    with conn.cursor() as cur:
        if status == "synced":
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status='synced', sincronizado_em=now(),
                          processando_em=NULL, ultimo_erro=NULL,
                          atualizado_em=now()
                    WHERE id=%s""",
                (outbox_id,),
            )
        else:
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status='failed',
                          processando_em=NULL,
                          proxima_tentativa_em=now() +
                            LEAST(interval '1 hour',
                                  interval '5 minutes' * power(2, tentativas - 1)),
                          ultimo_erro=%s,
                          atualizado_em=now()
                    WHERE id=%s""",
                (str(error or "erro")[:2000], outbox_id),
            )
    conn.commit()


def reset_stale(conn):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.patrimonio_fotos_sheets_outbox
                  SET status='failed', processando_em=NULL,
                      proxima_tentativa_em=now(),
                      ultimo_erro='job recuperado após expiração do lock',
                      atualizado_em=now()
                WHERE status='processing'
                  AND processando_em < now() - interval '15 minutes'"""
        )
    conn.commit()


def sync_one(conn, sheets, outbox_id: int, patrimonio_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id, p.numero_patrimonio, u.nome
                 FROM public.patrimonios p
                 JOIN public.unidades u ON u.id=p.unidade_id
                WHERE p.id=%s""",
            (patrimonio_id,),
        )
        patrimonio = cur.fetchone()
        cur.execute(
            """SELECT ordem, storage_path
                 FROM public.patrimonio_fotos
                WHERE patrimonio_id=%s
                ORDER BY ordem, id""",
            (patrimonio_id,),
        )
        fotos = cur.fetchall()

    if not patrimonio:
        raise RuntimeError(f"Patrimônio {patrimonio_id} não encontrado.")

    _, numero, unidade = patrimonio
    aba = sheets.worksheet(normalize_unit(unidade))
    values = aba.get_all_values()
    if not values:
        raise RuntimeError(f"Aba {unidade} sem cabeçalho.")

    header = list(values[0])
    while header and header[-1] == "":
        header.pop()

    changed = False
    if ID_COLUMN not in header:
        header.append(ID_COLUMN)
        changed = True
    for col in PHOTO_COLUMNS:
        if col not in header:
            header.append(col)
            changed = True

    if changed:
        aba.update(
            values=[header],
            range_name=f"A1:{col_letter(len(header))}1",
        )
        values = aba.get_all_values()

    id_idx = header.index(ID_COLUMN)
    number_idx = header.index("Nº de Patrimônio") if "Nº de Patrimônio" in header else 2
    row_number = None
    for row_idx, row in enumerate(values[1:], start=2):
        stable_id = row[id_idx].strip() if len(row) > id_idx else ""
        number = row[number_idx].strip() if len(row) > number_idx else ""
        if stable_id == str(patrimonio_id) or (
            not stable_id and re.sub(r"\s+", " ", number).casefold()
            == re.sub(r"\s+", " ", str(numero)).casefold()
        ):
            row_number = row_idx
            break

    if row_number is None:
        raise RuntimeError(f"Patrimônio {numero} não encontrado na aba {unidade}.")

    aba.update(
        values=[[str(patrimonio_id)]],
        range_name=f"{col_letter(id_idx + 1)}{row_number}",
    )

    formulas = [
        f'=IMAGE("{sheet_url(path).replace(chr(34), chr(34) * 2)}")'
        for _, path in fotos[:10]
    ]
    formulas += [""] * (10 - len(formulas))
    first = header.index(PHOTO_COLUMNS[0]) + 1
    last = first + 9
    aba.update(
        values=[formulas],
        range_name=f"{col_letter(first)}{row_number}:{col_letter(last)}{row_number}",
        value_input_option="USER_ENTERED",
    )


def main():
    limit = int(os.getenv("OUTBOX_BATCH_SIZE", "20"))
    conn = psycopg.connect(env("DATABASE_URL"))
    try:
        reset_stale(conn)
        sheets = sheets_client()
        spreadsheet = open_spreadsheet(sheets)
        claimed = claim_batch(conn, limit)
        for outbox_id, patrimonio_id, _foto_id in claimed:
            try:
                sync_one(conn, spreadsheet, outbox_id, int(patrimonio_id))
                mark(conn, int(outbox_id), "synced")
            except Exception as exc:
                mark(conn, int(outbox_id), "failed", str(exc))
        print(f"outbox processada: {len(claimed)} evento(s)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
