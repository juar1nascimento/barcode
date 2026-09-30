"""Painel operacional da sincronização de fotos com Google Sheets."""
from __future__ import annotations

import streamlit as st

from postgresql_persistencia import conectar


def _consultar(sql: str, params=()):
    conn = conectar()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _health():
    rows = _consultar("SELECT * FROM public.patrimonio_fotos_sheets_outbox_health")
    return rows[0] if rows else None


def _reconciliacao(limit: int = 50):
    return _consultar(
        """SELECT patrimonio_id, numero_patrimonio, fotos_postgres,
                  eventos_pendentes, eventos_falhos
             FROM public.patrimonio_fotos_sheets_reconciliation
            WHERE fotos_postgres > 0
              AND eventos_pendentes > 0
            ORDER BY patrimonio_id
            LIMIT %s""",
        (limit,),
    ) or []


def _falhas(limit: int = 20):
    return _consultar(
        """SELECT id, patrimonio_id, foto_id, status, tentativas,
                  proxima_tentativa_em, ultimo_erro, atualizado_em
             FROM public.patrimonio_fotos_sheets_outbox
            WHERE status='failed'
            ORDER BY atualizado_em DESC
            LIMIT %s""",
        (limit,),
    ) or []


def _reprocessar(ids: list[int]) -> int:
    conn = conectar()
    if conn is None:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status='pending',
                          proxima_tentativa_em=now(),
                          processando_em=NULL,
                          ultimo_erro=NULL,
                          atualizado_em=now()
                    WHERE id = ANY(%s)
                      AND status='failed'""",
                (ids,),
            )
            total = cur.rowcount
        conn.commit()
        return total
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def renderizar_painel_integracao():
    st.title("🩺 Saúde da integração de fotografias")
    st.caption(
        "Monitoramento operacional da fila Supabase → Google Sheets. "
        "Nenhuma credencial é exibida nesta tela."
    )

    health = _health()
    if health is None:
        st.error("PostgreSQL indisponível ou view de saúde não configurada.")
        return

    labels = [
        ("Pendentes", health[0]),
        ("Processando", health[1]),
        ("Sincronizados", health[2]),
        ("Falhos", health[3]),
        ("Prontos para retry", health[4]),
    ]
    cols = st.columns(len(labels))
    for col, (label, value) in zip(cols, labels):
        col.metric(label, int(value or 0))

    st.divider()

    ultima = health[6] if len(health) > 6 else None
    erro = health[7] if len(health) > 7 else None
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Última sincronização:**", ultima or "Ainda não registrada")
    with c2:
        st.write("**Último erro:**", erro or "Nenhum erro registrado")

    reconciliacao = _reconciliacao()
    if reconciliacao:
        st.info(f"🔄 {len(reconciliacao)} patrimônio(s) com eventos aguardando processamento.")
        st.dataframe(
            [
                {"Patrimônio": r[0], "Nº": r[1], "Fotos no PostgreSQL": r[2],
                 "Eventos pendentes": r[3], "Eventos falhos": r[4]}
                for r in reconciliacao
            ], use_container_width=True, hide_index=True,
        )

    falhas = _falhas()
    if not falhas:
        st.success("✅ Nenhuma falha pendente na fila.")
    else:
        st.warning(f"⚠️ {len(falhas)} evento(s) aguardando reprocessamento.")
        opcoes = {
            f"Evento {row[0]} · Patrimônio {row[1]} · tentativa {row[4]}": int(row[0])
            for row in falhas
        }
        selecionados = st.multiselect(
            "Eventos para reprocessar",
            list(opcoes.keys()),
        )
        if st.button("♻️ Reprocessar selecionados", type="primary"):
            ids = [opcoes[x] for x in selecionados]
            if not ids:
                st.info("Selecione pelo menos um evento.")
            else:
                total = _reprocessar(ids)
                st.success(f"{total} evento(s) devolvido(s) para a fila.")
                st.rerun()

        st.dataframe(
            [
                {
                    "Evento": row[0],
                    "Patrimônio": row[1],
                    "Foto": row[2],
                    "Tentativas": row[4],
                    "Próxima tentativa": row[5],
                    "Último erro": row[6] or "",
                }
                for row in falhas
            ],
            use_container_width=True,
            hide_index=True,
        )
