"""Integração da leitura de patrimônio com o motor de contagem do Almoxarifado.

A contagem é complementar ao cadastro: falha no motor de contagem não desfaz
um patrimônio já gravado no inventário.
"""

from __future__ import annotations

from typing import Any

from postgresql_persistencia import conectar


UNIDADE_ALMOX = "Almoxarifado Central SESA"


def registrar_contagem_se_almoxarifado(
    codigo: str,
    unidade: str,
    usuario: str | None = None,
) -> dict[str, Any] | None:
    if str(unidade or "").strip().casefold() != UNIDADE_ALMOX.casefold():
        return None

    conn = conectar()
    if conn is None:
        return {"ok": False, "erro": "PostgreSQL indisponível para a contagem."}

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT public.registrar_contagem_patrimonio(
                    %s, %s, %s, %s
                )
                """,
                (
                    str(codigo or "").strip(),
                    "barcode",
                    2,
                    str(usuario or "").strip() or None,
                ),
            )
            row = cur.fetchone()
        conn.commit()

        resultado = row[0] if row else None
        if isinstance(resultado, dict):
            return resultado
        return {"ok": True, "resultado": resultado}
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "erro": "Falha ao registrar o evento de contagem."}
    finally:
        conn.close()
