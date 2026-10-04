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

    # Se a infraestrutura do Drive não passou no preflight, não consuma
    # tentativas do Sheets de fotos: o pré-requisito corporativo ainda não
    # está disponível para completar o fluxo foto -> Drive -> Sheets.
    if drive.get("erro_preflight"):
        sheets = {
            "processados": 0,
            "sucesso": 0,
            "falhas": 0,
            "bloqueado_por": "drive_preflight",
        }
    else:
        sheets = processar_fila_google_sheets(limit=limit)
    return {
        "drive": drive,
        "sheets": sheets,
        # O workflow só pode ficar verde quando não houve falha transitória
        # nem dead-letter no Drive e nenhuma falha no Sheets.
        "ok": (
            drive["falhas"] == 0
            and drive["dead_letter"] == 0
            and sheets["falhas"] == 0
        ),
    }
