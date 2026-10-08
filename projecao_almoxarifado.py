"""Controles de projeção do Almoxarifado Central SESA, embutidos no inventário.

A quantidade total é opcional: NULL significa que o patrimônio continua
normalmente no inventário, sem countdown/projeção.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from postgresql_persistencia import conectar


UNIDADE_ALMOX = "Almoxarifado Central SESA"


def _is_admin() -> bool:
    usuario = str(st.session_state.get("usuario_logado", "")).strip().casefold()
    try:
        admin = str(st.secrets.get("email", {}).get("admin_email", "")).strip().casefold()
    except Exception:
        admin = ""
    return bool(usuario and admin and usuario == admin)


def _query(sql: str, params=()) -> list[tuple]:
    conn = conectar()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def _listar_opcoes() -> list[dict[str, Any]]:
    rows = _query(
        """
        SELECT DISTINCT
               p.tipo,
               NULLIF(BTRIM(p.tipo_custom), '') AS tipo_custom,
               NULLIF(BTRIM(p.fabricante), '') AS fabricante
          FROM public.patrimonios p
          JOIN public.unidades u ON u.id = p.unidade_id
         WHERE u.nome = %s
           AND COALESCE(p.ativo, TRUE)
         ORDER BY p.tipo, tipo_custom, fabricante
        """,
        (UNIDADE_ALMOX,),
    )
    return [
        {"tipo": r[0], "tipo_custom": r[1], "fabricante": r[2]}
        for r in rows
    ]


def _meta_atual(tipo: str, tipo_custom: str | None, fabricante: str | None):
    rows = _query(
        """
        SELECT m.id, m.quantidade_total, m.ativo, m.atualizado_em
          FROM public.patrimonio_contagem_metas m
          JOIN public.unidades u ON u.id = m.unidade_id
         WHERE u.nome = %s
           AND m.tipo = %s
           AND m.tipo_custom IS NOT DISTINCT FROM %s
           AND m.fabricante IS NOT DISTINCT FROM %s
         ORDER BY m.id DESC
         LIMIT 1
        """,
        (UNIDADE_ALMOX, tipo, tipo_custom, fabricante),
    )
    return rows[0] if rows else None


def _salvar_meta(tipo: str, tipo_custom: str | None, fabricante: str | None, quantidade: int | None) -> tuple[bool, str]:
    if not _is_admin():
        return False, "Operação não autorizada: somente o administrador pode configurar a projeção."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM public.unidades WHERE nome=%s LIMIT 1",
                (UNIDADE_ALMOX,),
            )
            unidade = cur.fetchone()
            if not unidade:
                conn.rollback()
                return False, "Almoxarifado Central SESA não encontrado."

            cur.execute(
                """
                INSERT INTO public.patrimonio_contagem_metas
                    (unidade_id, tipo, tipo_custom, fabricante, quantidade_total, ativo, atualizado_em)
                VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (
                    unidade_id,
                    tipo,
                    (COALESCE(tipo_custom, '')),
                    (COALESCE(fabricante, ''))
                )
                DO UPDATE SET
                    quantidade_total = EXCLUDED.quantidade_total,
                    ativo = TRUE,
                    atualizado_em = NOW()
                RETURNING id
                """,
                (unidade[0], tipo, tipo_custom, fabricante, quantidade),
            )
            meta_id = cur.fetchone()[0]
        conn.commit()
        if quantidade is None:
            return True, f"Meta {meta_id} mantida sem quantidade total: sem countdown."
        return True, f"Meta {meta_id} atualizada para {quantidade} unidade(s)."
    except Exception:
        conn.rollback()
        return False, "Não foi possível salvar a configuração da projeção."
    finally:
        conn.close()


def _projecao() -> list[dict[str, Any]]:
    rows = _query(
        """
        SELECT meta_id, unidade_id, unidade, tipo, tipo_custom, fabricante,
               quantidade_total, quantidade_conferida, quantidade_restante,
               percentual_concluido, ativo, atualizado_em
          FROM public.v_projecao_almoxarifado_central
         WHERE unidade_id = 2
           AND ativo = TRUE
         ORDER BY tipo, tipo_custom, fabricante
        """
    )
    cols = [
        "meta_id", "unidade_id", "unidade", "tipo", "tipo_custom",
        "fabricante", "quantidade_total", "quantidade_conferida",
        "quantidade_restante", "percentual_concluido", "ativo", "atualizado_em",
    ]
    return [dict(zip(cols, row)) for row in rows]


def renderizar_projecao_almoxarifado() -> None:
    if not _is_admin():
        st.error("Acesso não autorizado.")
        st.session_state.pagina_atual = "portal"
        return

    st.title("📈 Projeção — Almoxarifado Central SESA")
    st.caption(
        "A quantidade total é opcional. Deixe o campo vazio para manter o patrimônio "
        "no inventário sem countdown ou efeito de projeção."
    )

    opcoes = _listar_opcoes()
    if not opcoes:
        st.info("Ainda não existem patrimônios ativos no Almoxarifado Central SESA.")
        return

    labels = []
    mapa = {}
    for item in opcoes:
        nome_tipo = item["tipo_custom"] if item["tipo"] == "Outros Patrimônio" and item["tipo_custom"] else item["tipo"]
        fabricante = item["fabricante"] or "Todos / não informado"
        label = f"{nome_tipo} — {fabricante}"
        labels.append(label)
        mapa[label] = item

    escolhido = st.selectbox(
        "Patrimônio / fabricante",
        labels,
        index=None,
        placeholder="Selecione o patrimônio...",
        key="projecao_almox_item",
    )

    if not escolhido:
        st.divider()
        st.subheader("📊 Projeções configuradas")
        dados = _projecao()
        if dados:
            st.dataframe(
                [
                    {
                        "Patrimônio": (
                            d["tipo_custom"]
                            if d["tipo"] == "Outros Patrimônio" and d["tipo_custom"]
                            else d["tipo"]
                        ),
                        "Fabricante": d["fabricante"] or "Todos / não informado",
                        "Total": d["quantidade_total"] if d["quantidade_total"] is not None else "—",
                        "Conferidos": d["quantidade_conferida"],
                        "Restantes": d["quantidade_restante"] if d["quantidade_total"] is not None else "—",
                        "Progresso": (
                            f'{float(d["percentual_concluido"]):.2f}%'
                            if d["percentual_concluido"] is not None else "—"
                        ),
                    }
                    for d in dados
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma projeção configurada ainda.")
        return

    item = mapa[escolhido]
    tipo = item["tipo"]
    tipo_custom = item["tipo_custom"]
    fabricante = item["fabricante"]

    atual = _meta_atual(tipo, tipo_custom, fabricante)
    valor_atual = atual[1] if atual else None

    st.divider()
    st.markdown(f"**Patrimônio:** {escolhido}")
    st.caption(
        "Informe a quantidade total somente quando existir uma meta de conferência. "
        "Apagar o valor remove o countdown, sem apagar o patrimônio."
    )

    with st.form("form_meta_projecao_almox", clear_on_submit=False):
        quantidade_texto = st.text_input(
            "Quantidade total (opcional)",
            value="" if valor_atual is None else str(valor_atual),
            placeholder="Deixe vazio para não usar projeção",
            key="projecao_quantidade_total",
        )
        salvar = st.form_submit_button(
            "💾 Salvar quantidade total",
            type="primary",
            use_container_width=True,
        )

    if salvar:
        texto = quantidade_texto.strip()
        quantidade = None
        if texto:
            try:
                quantidade = int(texto)
                if quantidade < 0:
                    raise ValueError
            except ValueError:
                st.error("Informe um número inteiro maior ou igual a zero, ou deixe vazio.")
                return

        ok, msg = _salvar_meta(tipo, tipo_custom, fabricante, quantidade)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
            return

    dados = [
        d for d in _projecao()
        if d["tipo"] == tipo
        and d["tipo_custom"] == tipo_custom
        and d["fabricante"] == fabricante
    ]

    if not dados:
        st.info("Nenhuma meta configurada para este patrimônio. O inventário segue normalmente.")
        return

    d = dados[0]
    total = d["quantidade_total"]
    conferidos = int(d["quantidade_conferida"] or 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TOTAL DEFINIDO", total if total is not None else "—")
    c2.metric("CONFERIDOS", conferidos)
    c3.metric(
        "RESTANTES",
        int(d["quantidade_restante"]) if d["quantidade_restante"] is not None else "—",
    )
    c4.metric(
        "PROGRESSO",
        f'{float(d["percentual_concluido"]):.2f}%'
        if d["percentual_concluido"] is not None else "—",
    )

    if total is None:
        st.info(
            "Quantidade total não definida. Os patrimônios continuam sendo armazenados "
            "normalmente, mas esta seleção não participa do countdown."
        )
    else:
        restante = max(int(total) - conferidos, 0)
        if restante == 0:
            st.success("✅ Meta de conferência atingida.")
        else:
            st.info(f"⏳ Faltam {restante} patrimônio(s) distintos para atingir a meta.")

    st.caption("A contagem considera patrimônios distintos; repetir a leitura do mesmo patrimônio não reduz o restante novamente.")
