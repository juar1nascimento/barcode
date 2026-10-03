"""Orquestrador do tráfego Supabase -> Google Drive -> Google Sheets.

A ordem é deliberada: fotos são entregues primeiro ao repositório corporativo
do Drive; somente depois o Sheets recebe o nome/link da foto. Patrimônio sem
foto segue seu fluxo normalmente.
"""

from __future__ import annotations

from sincronizador_google_drive import processar_fila_google_drive
from sincronizador_google_sheets import processar_fila_google_sheets


def processar_sincronizacao_incremental(limit: int = 25) -> dict:
    drive = processar_fila_google_drive(limit=limit)
    sheets = processar_fila_google_sheets(limit=limit)
    return {
        "drive": drive,
        "sheets": sheets,
        "ok": drive["dead_letter"] == 0 and sheets["falhas"] == 0,
    }
