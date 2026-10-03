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

COLUNAS = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro"]


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def safe_error(error: Exception | str) -> str:
    """Remove credenciais e detalhes potencialmente sensíveis dos registros operacionais."""
    value = str(error or "")
    value = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token=)[^&\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[REDACTED PEM]", value, flags=re.DOTALL)
    return value[:500]


def normalize_unit(value: str) -> str:
    aliases = {
        "URS Jacara_pe": "URS Jacaraípe",
        "UBS Bairro de F_tima": "UBS Bairro de Fátima",
    }
    return aliases.get(str(value or "").strip(), str(value or "").strip())


def sheets_client():
    data = json.loads(env("GOOGLE_SERVICE_ACCOUNT_JSON"))
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


def col_letter(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def claim_batch(conn, limit: int):
    with conn.cursor() as cur:
        cur.execute(
            """WITH candidatos AS (
                 SELECT id
                   FROM public.patrimonios_sheets_outbox
                  WHERE status IN ('pending','failed')
                    AND proxima_tentativa_em <= now()
                  ORDER BY id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
               )
               UPDATE public.patrimonios_sheets_outbox o
                  SET status='processing',
                      processando_em=now(),
                      tentativas=tentativas+1,
                      atualizado_em=now()
                 FROM candidatos c
                WHERE o.id=c.id
               RETURNING o.id,o.patrimonio_id""",
            (limit,),
        )
        rows = cur.fetchall()
    conn.commit()
    return rows


def mark(conn, outbox_id: int, status: str, error: str | None = None, max_attempts: int = 8):
    with conn.cursor() as cur:
        if status == "synced":
            cur.execute(
                """UPDATE public.patrimonios_sheets_outbox
                      SET status='synced', sincronizado_em=now(),
                          processando_em=NULL, ultimo_erro=NULL, atualizado_em=now()
                    WHERE id=%s""",
                (outbox_id,),
            )
        else:
            cur.execute(
                """UPDATE public.patrimonios_sheets_outbox
                      SET status=CASE WHEN tentativas >= %s THEN 'dead_letter' ELSE 'failed' END,
                          processando_em=NULL,
                          proxima_tentativa_em=CASE
                            WHEN tentativas >= %s THEN now()
                            ELSE now() + LEAST(interval '1 hour',
                                 interval '5 minutes' * power(2, tentativas - 1))
                          END,
                          ultimo_erro=%s, atualizado_em=now()
                    WHERE id=%s""",
                (max_attempts, max_attempts, safe_error(error or "erro"), outbox_id),
            )
    conn.commit()


def reset_stale(conn):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.patrimonios_sheets_outbox
                  SET status='failed', processando_em=NULL,
                      proxima_tentativa_em=now(),
                      ultimo_erro='job recuperado após expiração do lock',
                      atualizado_em=now()
                WHERE status='processing'
                  AND processando_em < now() - interval '15 minutes'"""
        )
    conn.commit()


def sync_one(conn, spreadsheet, patrimonio_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id,p.numero_patrimonio,p.codigo_barras,p.tipo,p.fabricante,
                      p.data_cadastro,u.nome,s.nome
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
        aba.update(values=[COLUNAS], range_name="A1:E1")
        values = [COLUNAS]

    header = list(values[0])

    def _header_key(value: str) -> str:
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

    aliases = {
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
    normalized_header = [aliases.get(_header_key(item), str(item or "").strip()) for item in header]
    required_keys = [_header_key(item) for item in COLUNAS]
    actual_keys = [_header_key(item) for item in normalized_header]
    if actual_keys[:len(COLUNAS)] != required_keys:
        missing = [COLUNAS[i] for i, key in enumerate(required_keys) if i >= len(actual_keys) or actual_keys[i] != key]
        observed = actual_keys[:len(COLUNAS)]
        raise RuntimeError(
            f"Aba {unidade} possui cabeçalho incompatível com o inventário. "
            f"Coluna divergente: {missing[0] if missing else 'desconhecida'}. "
            f"Chaves observadas: {observed!r}."
        )

    numero = str(numero or "").strip()
    setor = str(setor or "").strip()
    tipo = str(tipo or "").strip()
    fabricante = str(fabricante or "").strip()
    data_texto = data_cadastro.isoformat(sep=" ") if hasattr(data_cadastro, "isoformat") else str(data_cadastro or "").strip()
    esperado = [setor, tipo, numero, fabricante, data_texto]

    row_number = None
    compact_expected = re.sub(r"\s+", " ", numero).casefold()
    for idx, existing in enumerate(values[1:], start=2):
        current = existing[2].strip() if len(existing) > 2 else ""
        if re.sub(r"\s+", " ", current).casefold() == compact_expected:
            row_number = idx
            break

    if row_number is None:
        aba.append_rows([esperado], value_input_option="RAW")
        row_number = len(aba.get_all_values())
    else:
        aba.update(
            values=[esperado],
            range_name=f"A{row_number}:E{row_number}",
            value_input_option="RAW",
        )

    confirmed = aba.get(f"A{row_number}:E{row_number}")
    actual = list(confirmed[0]) if confirmed else []
    actual = (actual + [""] * 5)[:5]
    if actual != esperado:
        raise RuntimeError(
            f"Google Sheets não confirmou o patrimônio {patrimonio_id}: "
            f"esperado={esperado!r}, recebido={actual!r}"
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
