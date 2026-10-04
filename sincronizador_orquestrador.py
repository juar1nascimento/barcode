"""Orquestrador do tráfego Supabase -> Google Sheets.

O processamento de Google Drive foi retirado deste fluxo legado. O Drive possui
worker dedicado (Edge Function) e não deve ser consumido por este workflow,
evitando dois consumidores concorrentes da mesma outbox.
"""

from __future__ import annotations

from sincronizador_google_sheets import processar_fila_google_sheets


def processar_sincronizacao_incremental(limit: int = 25) -> dict:
    """Processa somente o consumidor legado do Sheets.

    A entrega de fotos ao Google Drive é responsabilidade exclusiva do worker
    dedicado. Isso evita que o CI volte a consumir a outbox do Drive com regras
    de retry/credenciais diferentes das do worker oficial.
    """
    sheets = processar_fila_google_sheets(limit=limit)
    drive = {
        "processados": 0,
        "sucesso": 0,
        "falhas": 0,
        "dead_letter": 0,
        "desabilitado": True,
        "responsavel": "outbox-drive-worker",
    }
    return {
        "drive": drive,
        "sheets": sheets,
        "ok": sheets["falhas"] == 0,
    }
