"""Tela administrativa para o primeiro teste controlado de upload de foto.

Este módulo não integra a câmera do inventário. Ele permite somente um
upload manual por vez para o patrimônio de teste previamente validado.
"""

from __future__ import annotations

import streamlit as st

from postgresql_persistencia import conectar
from supabase_storage import salvar_foto_patrimonio

PATRIMONIO_TESTE_ID = 2


def _buscar_patrimonio(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                   p.id,
                   p.numero_patrimonio,
                   u.nome AS unidade,
                   s.nome AS setor,
                   COUNT(f.id)::int AS fotos,
                   COALESCE(MAX(f.ordem), 0)::int AS ultima_ordem
                 FROM public.patrimonios p
                 LEFT JOIN public.unidades u ON u.id = p.unidade_id
                 LEFT JOIN public.setores s ON s.id = p.setor_id
                 LEFT JOIN public.patrimonio_fotos f
                   ON f.patrimonio_id = p.id
                WHERE p.id = %s
                GROUP BY p.id, p.numero_patrimonio, u.nome, s.nome""",
            (PATRIMONIO_TESTE_ID,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": int(row[0]),
        "numero": row[1],
        "unidade": row[2],
        "setor": row[3],
        "fotos": int(row[4]),
        "ultima_ordem": int(row[5]),
    }


def _buscar_foto(conn, foto_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                   id, patrimonio_id, ordem, storage_bucket, storage_path,
                   arquivo_nome, mime_type, tamanho_bytes, largura, altura,
                   sha256, criado_em
                 FROM public.patrimonio_fotos
                WHERE id = %s""",
            (foto_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": int(row[0]),
        "patrimonio_id": int(row[1]),
        "ordem": int(row[2]),
        "bucket": row[3],
        "storage_path": row[4],
        "arquivo_nome": row[5],
        "mime_type": row[6],
        "tamanho_bytes": int(row[7]),
        "largura": int(row[8]) if row[8] is not None else None,
        "altura": int(row[9]) if row[9] is not None else None,
        "sha256": row[10],
        "criado_em": row[11],
    }


def renderizar_teste_upload_foto() -> None:
    st.title("🧪 Teste controlado de upload de foto")
    st.caption(
        "Teste administrativo isolado. A câmera do inventário ainda não foi alterada."
    )

    st.warning(
        "Este teste aceita somente 1 imagem por execução e grava no patrimônio "
        f"de teste ID {PATRIMONIO_TESTE_ID}."
    )

    conn = conectar()
    if conn is None:
        st.error(
            "Não foi possível conectar ao PostgreSQL. "
            "Verifique a configuração [postgresql] nas Secrets."
        )
        return

    try:
        patrimonio = _buscar_patrimonio(conn)
    finally:
        conn.close()

    if patrimonio is None:
        st.error(f"Patrimônio de teste ID {PATRIMONIO_TESTE_ID} não encontrado.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("ID do patrimônio", patrimonio["id"])
        st.write(f"**Número:** {patrimonio['numero']}")
        st.write(f"**Unidade:** {patrimonio['unidade']}")
    with col2:
        st.metric("Fotos existentes", patrimonio["fotos"])
        st.write(f"**Setor:** {patrimonio['setor']}")
        st.write(f"**Próxima ordem:** {patrimonio['ultima_ordem'] + 1}")

    st.divider()

    arquivo = st.file_uploader(
        "Selecione uma única foto para o teste",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="teste_upload_foto",
    )

    if arquivo is not None:
        st.info(
            f"Arquivo selecionado: {arquivo.name} — "
            f"{arquivo.size:,} bytes antes do tratamento."
        )

    if not st.button(
        "📤 Enviar 1 foto para o patrimônio de teste",
        type="primary",
        disabled=arquivo is None,
    ):
        return

    imagem = arquivo.getvalue()

    conn = conectar()
    if conn is None:
        st.error("Não foi possível conectar ao PostgreSQL para registrar a foto.")
        return

    try:
        with st.spinner("Processando e enviando a foto..."):
            ok, foto_id, mensagem = salvar_foto_patrimonio(
                conn,
                PATRIMONIO_TESTE_ID,
                imagem,
                arquivo.name,
            )

        if not ok or foto_id is None:
            st.error(mensagem)
            return

        foto = _buscar_foto(conn, foto_id)
    finally:
        conn.close()

    if foto is None:
        st.error(
            "O upload retornou sucesso, mas os metadados não foram encontrados "
            "na consulta de confirmação."
        )
        return

    st.success(mensagem)
    st.write("### Confirmação do registro")
    st.write(f"**ID da foto:** {foto['id']}")
    st.write(f"**Patrimônio:** {foto['patrimonio_id']}")
    st.write(f"**Ordem:** {foto['ordem']}")
    st.write(f"**Bucket:** {foto['bucket']}")
    st.write(f"**Caminho:** {foto['storage_path']}")
    st.write(f"**MIME:** {foto['mime_type']}")
    st.write(f"**Tamanho final:** {foto['tamanho_bytes']:,} bytes")
    st.write(f"**Dimensões:** {foto['largura']} × {foto['altura']}")
    st.write(f"**SHA-256:** {foto['sha256']}")
    st.write(f"**Criado em:** {foto['criado_em']}")

    st.success(
        "Teste ponta a ponta confirmado: imagem tratada → Storage → "
        "patrimonio_fotos."
    )
