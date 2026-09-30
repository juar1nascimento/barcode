from __future__ import annotations

from typing import Any

import streamlit as st

from postgresql_persistencia import conectar
from supabase_storage import salvar_foto_patrimonio


EXTENSOES_IMAGEM = ["jpg", "jpeg", "png", "webp"]
MAX_UPLOAD_MB = 20


GOOGLE_FOTO_COLUNAS = [f"Foto {indice}" for indice in range(1, 11)]


def _coluna_letra(numero: int) -> str:
    letra = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letra = chr(65 + resto) + letra
    return letra


def _url_publica_foto(storage_path: str) -> str:
    sec = st.secrets.get("supabase") or {}
    base_url = str(sec.get("url") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("Secret [supabase].url não configurada.")
    from urllib.parse import quote
    caminho = quote(str(storage_path or "").lstrip("/"), safe="/")
    return f"{base_url}/storage/v1/object/public/patrimonio-fotos/{caminho}"


def _sincronizar_fotos_google(patrimonio_id: int) -> tuple[bool, str]:
    """Coloca as fotografias também dentro da linha do patrimônio no Sheets.

    As células Foto 1..Foto 10 usam IMAGE(URL), mantendo a imagem visível na
    própria tabela. O arquivo físico continua no Storage; a planilha recebe
    a referência visual, não um binário/base64.
    """
    try:
        patrimonio = buscar_patrimonio_por_id(patrimonio_id)
        if not patrimonio:
            return False, "Patrimônio não encontrado para sincronização no Sheets."
        from Tabela_de_dados_Inventario_7_2 import conectar_google_sheets, _nome_aba, _normalizar_unidade_aba
        planilha = conectar_google_sheets()
        if planilha is None:
            return False, "Google Sheets indisponível para sincronizar as fotos."
        aba = planilha.worksheet(_nome_aba(_normalizar_unidade_aba(patrimonio["unidade"])))
        valores = aba.get_all_values()
        if not valores:
            return False, "A aba do patrimônio está sem cabeçalho."
        cabecalho = list(valores[0])
        while len(cabecalho) < 5:
            cabecalho.append("")
        for nome in GOOGLE_FOTO_COLUNAS:
            if nome not in cabecalho:
                cabecalho.append(nome)
        ultima_coluna = _coluna_letra(len(cabecalho))
        if cabecalho != list(valores[0]):
            aba.update(values=[cabecalho], range_name=f"A1:{ultima_coluna}1")
        indice_numero = 2
        linha_planilha = None
        chave = str(patrimonio["numero"]).strip().casefold()
        for indice, linha in enumerate(valores[1:], start=2):
            if len(linha) > indice_numero and str(linha[indice_numero]).strip().casefold() == chave:
                linha_planilha = indice
                break
        if linha_planilha is None:
            return False, f"Patrimônio {patrimonio['numero']} não encontrado na aba do Sheets."
        fotos = buscar_fotos_patrimonio(patrimonio_id)
        formulas = []
        for foto in fotos[: len(GOOGLE_FOTO_COLUNAS)]:
            url = _url_publica_foto(foto["storage_path"]).replace('"', '""')
            formulas.append(f'=IMAGE("{url}")')
        formulas.extend([""] * (len(GOOGLE_FOTO_COLUNAS) - len(formulas)))
        primeira_coluna = _coluna_letra(6)
        ultima_coluna = _coluna_letra(5 + len(GOOGLE_FOTO_COLUNAS))
        aba.update(values=[formulas], range_name=f"{primeira_coluna}{linha_planilha}:{ultima_coluna}{linha_planilha}", value_input_option="USER_ENTERED")
        return True, f"{len(fotos)} foto(s) sincronizada(s) no Google Sheets."
    except Exception as exc:
        return False, f"Falha ao sincronizar fotos no Google Sheets: {exc}"


def _fechar_conexao(conn: Any) -> None:
    """Fecha uma conexão PostgreSQL sem mascarar o erro original."""
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def buscar_patrimonio_por_id(patrimonio_id: int) -> dict[str, Any] | None:
    """Localiza patrimônio pelo ID PostgreSQL para sincronização da foto."""
    try:
        patrimonio_id = int(patrimonio_id)
    except (TypeError, ValueError):
        return None
    if patrimonio_id <= 0:
        return None
    conn = conectar()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.numero_patrimonio, p.tipo, p.fabricante,
                       u.nome AS unidade, COALESCE(s.nome, '') AS setor
                FROM public.patrimonios p
                JOIN public.unidades u ON u.id = p.unidade_id
                LEFT JOIN public.setores s ON s.id = p.setor_id
                WHERE p.id = %s
                LIMIT 1
                """,
                (patrimonio_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]), "numero": row[1], "tipo": row[2],
                "fabricante": row[3] or "", "unidade": row[4], "setor": row[5] or "",
            }
    except Exception:
        return None
    finally:
        _fechar_conexao(conn)


def buscar_patrimonio_por_numero(
    numero_patrimonio: str,
    unidade: str,
) -> dict[str, Any] | None:
    """Localiza um patrimônio pelo número e pela unidade."""
    numero = str(numero_patrimonio or "").strip()
    nome_unidade = str(unidade or "").strip()

    if not numero or not nome_unidade:
        return None

    conn = conectar()

    if conn is None:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    p.id,
                    p.numero_patrimonio,
                    p.tipo,
                    p.fabricante,
                    u.nome AS unidade,
                    s.nome AS setor
                FROM public.patrimonios AS p
                JOIN public.unidades AS u
                    ON u.id = p.unidade_id
                LEFT JOIN public.setores AS s
                    ON s.id = p.setor_id
                WHERE p.numero_patrimonio = %s
                  AND u.nome = %s
                LIMIT 1
                """,
                (numero, nome_unidade),
            )

            row = cur.fetchone()

            if not row:
                return None

            return {
                "id": int(row[0]),
                "numero": row[1],
                "tipo": row[2],
                "fabricante": row[3] or "",
                "unidade": row[4],
                "setor": row[5] or "",
            }

    except Exception:
        return None

    finally:
        _fechar_conexao(conn)


def buscar_fotos_patrimonio(patrimonio_id: int) -> list[dict[str, Any]]:
    """Retorna os metadados das fotografias vinculadas ao patrimônio."""
    try:
        patrimonio_id = int(patrimonio_id)
    except (TypeError, ValueError):
        return []

    if patrimonio_id <= 0:
        return []

    conn = conectar()

    if conn is None:
        return []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    ordem,
                    storage_bucket,
                    storage_path,
                    arquivo_nome,
                    mime_type,
                    tamanho_bytes,
                    largura,
                    altura,
                    sha256,
                    criado_em
                FROM public.patrimonio_fotos
                WHERE patrimonio_id = %s
                ORDER BY ordem ASC, id ASC
                """,
                (patrimonio_id,),
            )

            registros = cur.fetchall()

            return [
                {
                    "id": int(row[0]),
                    "ordem": int(row[1]),
                    "bucket": row[2],
                    "storage_path": row[3],
                    "arquivo_nome": row[4],
                    "mime_type": row[5],
                    "tamanho_bytes": int(row[6]),
                    "largura": row[7],
                    "altura": row[8],
                    "sha256": row[9],
                    "criado_em": row[10],
                }
                for row in registros
            ]

    except Exception:
        return []

    finally:
        _fechar_conexao(conn)


def _formatar_tamanho(tamanho_bytes: int) -> str:
    """Formata bytes para leitura humana."""
    tamanho = float(max(0, tamanho_bytes))

    for unidade in ("B", "KB", "MB", "GB"):
        if tamanho < 1024 or unidade == "GB":
            return f"{tamanho:.1f} {unidade}"
        tamanho /= 1024

    return f"{tamanho_bytes} B"


def _salvar_fotografia(
    patrimonio_id: int,
    arquivo: Any,
) -> tuple[bool, int | None, str]:
    """Processa e grava uma fotografia usando a rotina central do Storage."""
    dados = arquivo.getvalue()

    if not dados:
        return False, None, "O arquivo selecionado está vazio."

    limite = MAX_UPLOAD_MB * 1024 * 1024

    if len(dados) > limite:
        return (
            False,
            None,
            f"A fotografia excede o limite de {MAX_UPLOAD_MB} MB.",
        )

    conn = conectar()

    if conn is None:
        return (
            False,
            None,
            "Não foi possível conectar ao PostgreSQL.",
        )

    try:
        return salvar_foto_patrimonio(
            conn,
            patrimonio_id,
            dados,
            arquivo.name,
        )
    except Exception as exc:
        return (
            False,
            None,
            f"Erro ao salvar a fotografia: {exc}",
        )
    finally:
        _fechar_conexao(conn)


def renderizar_fotos_patrimonio(patrimonio_id: int) -> None:
    """Renderiza upload e histórico de fotografias de um patrimônio."""
    try:
        patrimonio_id = int(patrimonio_id)
    except (TypeError, ValueError):
        st.error("ID de patrimônio inválido.")
        return

    if patrimonio_id <= 0:
        st.error("ID de patrimônio inválido.")
        return

    st.markdown("### 📷 Fotografias do patrimônio")

    fotos = buscar_fotos_patrimonio(patrimonio_id)

    if fotos:
        st.caption(
            f"{len(fotos)} fotografia(s) cadastrada(s). "
            "As imagens permanecem vinculadas a este patrimônio."
        )
    else:
        st.info(
            "Nenhuma fotografia cadastrada para este patrimônio."
        )

    origem = st.radio(
        "Origem da fotografia",
        ["📷 Tirar foto", "📁 Selecionar arquivo"],
        horizontal=True,
        key=f"origem_foto_patrimonio_{patrimonio_id}",
    )

    if origem == "📷 Tirar foto":
        arquivo = st.camera_input(
            "Capture a fotografia do patrimônio",
            key=f"camera_patrimonio_{patrimonio_id}",
        )
    else:
        arquivo = st.file_uploader(
            "Adicionar fotografia do equipamento",
            type=EXTENSOES_IMAGEM,
            accept_multiple_files=False,
            key=f"foto_patrimonio_{patrimonio_id}",
            help=(
                f"Formatos aceitos: JPG, JPEG, PNG e WEBP. "
                f"Limite de entrada: {MAX_UPLOAD_MB} MB. "
                "A rotina do Storage realiza o tratamento final da imagem."
            ),
        )

    if arquivo is not None:
        st.image(
            arquivo,
            caption=arquivo.name,
            use_container_width=True,
        )

        st.caption(
            f"Arquivo selecionado: {arquivo.name} — "
            f"{_formatar_tamanho(arquivo.size)} antes do tratamento."
        )

        if st.button(
            "📤 Salvar fotografia",
            type="primary",
            use_container_width=True,
            key=f"salvar_foto_{patrimonio_id}",
        ):
            with st.spinner(
                "Processando e armazenando fotografia..."
            ):
                ok, foto_id, mensagem = _salvar_fotografia(
                    patrimonio_id,
                    arquivo,
                )

            if ok:
                sincronizada, mensagem_sheets = _sincronizar_fotos_google(patrimonio_id)
                st.success(
                    f"✅ {mensagem} "
                    f"Foto ID: {foto_id}."
                )
                if sincronizada:
                    st.success(f"📊 {mensagem_sheets}")
                else:
                    st.warning(
                        "⚠️ A foto foi salva no Supabase/PostgreSQL, mas não foi "
                        f"refletida na tabela do Google Sheets: {mensagem_sheets}"
                    )
                st.rerun()
            else:
                st.error(mensagem)

    fotos = buscar_fotos_patrimonio(patrimonio_id)

    if not fotos:
        return

    st.markdown("#### Histórico de fotografias")

    colunas = st.columns(min(len(fotos), 3))

    for indice, foto in enumerate(fotos):
        with colunas[indice % len(colunas)]:
            st.markdown(f"**📷 Foto {foto['ordem']}**")
            st.caption(foto["arquivo_nome"])

            dimensoes = ""
            if foto["largura"] and foto["altura"]:
                dimensoes = (
                    f"{foto['largura']} × {foto['altura']}"
                )

            detalhes = [
                item
                for item in (
                    dimensoes,
                    _formatar_tamanho(foto["tamanho_bytes"]),
                    foto["mime_type"],
                )
                if item
            ]

            if detalhes:
                st.caption(" • ".join(detalhes))

            st.caption(
                f"Storage: {foto['bucket']}/{foto['storage_path']}"
            )

            if foto["sha256"]:
                with st.expander("Integridade / SHA-256"):
                    st.code(foto["sha256"])
