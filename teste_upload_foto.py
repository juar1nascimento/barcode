"""Tela administrativa para um teste manual e explicitamente habilitado de foto.

Por padrão, a funcionalidade fica bloqueada. Para habilitá-la, configure
GTI_TEST_UPLOAD_ENABLED=true e GTI_TEST_PATRIMONIO_ID com o ID de um registro
de teste cujo numero_patrimonio comece exatamente com GTI-TESTE-.

Este teste valida apenas Storage + metadados no PostgreSQL; não comprova
sincronização com Google Drive, Google Sheets ou espelhamento local.
"""

from __future__ import annotations

import os

import streamlit as st

from postgresql_persistencia import conectar
from supabase_storage import salvar_foto_patrimonio

PREFIXO_PATRIMONIO_TESTE = "GTI-TESTE-"


def _ler_configuracao(nome: str) -> str:
    """Lê configuração de ambiente ou Streamlit Secrets sem exibi-la."""
    valor = os.getenv(nome)
    if valor is not None:
        return str(valor).strip()

    try:
        valor = st.secrets.get(nome, "")
    except Exception:
        # Secrets podem não existir em execução local; nesse caso, falhar fechado.
        valor = ""

    return str(valor).strip() if valor is not None else ""


def _configurar_teste() -> tuple[int | None, str | None]:
    habilitado = _ler_configuracao("GTI_TEST_UPLOAD_ENABLED").lower()
    if habilitado != "true":
        return None, (
            "Teste bloqueado por padrão. Habilite explicitamente "
            "GTI_TEST_UPLOAD_ENABLED=true no ambiente/Secrets somente quando "
            "houver um patrimônio fictício dedicado."
        )

    id_configurado = _ler_configuracao("GTI_TEST_PATRIMONIO_ID")
    try:
        patrimonio_id = int(id_configurado)
    except (TypeError, ValueError):
        return None, (
            "Configuração inválida: GTI_TEST_PATRIMONIO_ID deve conter o ID "
            "numérico de um patrimônio fictício dedicado."
        )

    if patrimonio_id <= 0:
        return None, "Configuração inválida: o ID do patrimônio de teste deve ser positivo."

    return patrimonio_id, None


def _buscar_patrimonio(conn, patrimonio_id: int) -> dict | None:
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
            (patrimonio_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": int(row[0]),
        "numero": str(row[1] or "").strip(),
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
        "Teste administrativo isolado. A câmera do inventário e os workers "
        "de Drive/Sheets/local não são acionados por esta tela."
    )

    patrimonio_id, erro_config = _configurar_teste()
    if erro_config:
        st.warning(erro_config)
        st.info(
            "Nenhuma conexão com o banco foi aberta e nenhum upload foi executado. "
            "Não use um patrimônio real para habilitar este teste."
        )
        return

    if patrimonio_id is None:
        st.error("Configuração do patrimônio de teste inválida. Upload bloqueado.")
        return

    st.warning(
        "Modo de teste habilitado. O upload será recusado se o número do "
        f"patrimônio não começar com {PREFIXO_PATRIMONIO_TESTE}."
    )

    conn = conectar()
    if conn is None:
        st.error(
            "Não foi possível conectar ao PostgreSQL. "
            "Verifique a configuração do ambiente, sem compartilhar credenciais."
        )
        return

    try:
        patrimonio = _buscar_patrimonio(conn, patrimonio_id)
    finally:
        conn.close()

    if patrimonio is None:
        st.error("Patrimônio de teste configurado não encontrado; operação bloqueada.")
        return

    if not patrimonio["numero"].startswith(PREFIXO_PATRIMONIO_TESTE):
        st.error(
            "Operação bloqueada: o registro configurado não é um patrimônio "
            f"fictício com prefixo {PREFIXO_PATRIMONIO_TESTE}. Nenhum upload foi feito."
        )
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("ID do patrimônio de teste", patrimonio["id"])
        st.write(f"**Número fictício:** {patrimonio['numero']}")
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
        "📤 Enviar 1 foto para o patrimônio fictício",
        type="primary",
        disabled=arquivo is None,
    ):
        return

    # Revalida a configuração e o registro imediatamente antes da gravação.
    id_confirmado, erro_config = _configurar_teste()
    if erro_config or id_confirmado != patrimonio_id:
        st.error("Configuração de teste mudou ou deixou de ser válida. Upload bloqueado.")
        return

    imagem = arquivo.getvalue()
    conn = conectar()
    if conn is None:
        st.error("Não foi possível conectar ao PostgreSQL para registrar a foto.")
        return

    foto = None
    try:
        patrimonio_atual = _buscar_patrimonio(conn, patrimonio_id)
        if (
            patrimonio_atual is None
            or not patrimonio_atual["numero"].startswith(PREFIXO_PATRIMONIO_TESTE)
        ):
            st.error(
                "O patrimônio deixou de passar pela validação de segurança. "
                "Nenhum upload foi executado."
            )
            return

        with st.spinner("Processando e enviando a foto..."):
            ok, foto_id, mensagem = salvar_foto_patrimonio(
                conn,
                patrimonio_id,
                imagem,
                arquivo.name,
            )

        if not ok or foto_id is None:
            st.error(mensagem)
            return

        foto = _buscar_foto(conn, foto_id)
    finally:
        conn.close()

    if foto is None or foto["patrimonio_id"] != patrimonio_id:
        st.error(
            "Não foi possível confirmar os metadados da foto no patrimônio de teste. "
            "A sincronização externa não foi validada."
        )
        return

    st.success(mensagem)
    st.write("### Confirmação do registro")
    st.write(f"**ID da foto:** {foto['id']}")
    st.write(f"**Patrimônio fictício:** {foto['patrimonio_id']}")
    st.write(f"**Ordem:** {foto['ordem']}")
    st.write(f"**Bucket:** {foto['bucket']}")
    st.write(f"**Caminho:** {foto['storage_path']}")
    st.write(f"**MIME:** {foto['mime_type']}")
    st.write(f"**Tamanho final:** {foto['tamanho_bytes']:,} bytes")
    st.write(f"**Dimensões:** {foto['largura']} × {foto['altura']}")
    st.write(f"**SHA-256:** {foto['sha256']}")
    st.write(f"**Criado em:** {foto['criado_em']}")

    st.success(
        "Etapa confirmada: Storage + metadados no PostgreSQL para o patrimônio "
        "fictício. Google Drive, Google Sheets e pasta local ainda precisam de "
        "validação independente."
    )
