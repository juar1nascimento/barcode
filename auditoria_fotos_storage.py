"""Auditoria somente leitura de integridade entre PostgreSQL e Supabase Storage."""

from __future__ import annotations

import requests
import pandas as pd
import streamlit as st

from postgresql_persistencia import conectar
from supabase_storage import BUCKET, _config_supabase, _headers


def _listar_storage_detalhado():
    config = _config_supabase()
    encontrados = []

    def listar_prefixo(prefixo: str):
        offset = 0
        while True:
            response = requests.post(
                f"{config['url']}/storage/v1/object/list/{BUCKET}",
                headers={**_headers(config["key"]), "Content-Type": "application/json"},
                json={
                    "prefix": prefixo,
                    "limit": 1000,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                },
                timeout=30,
            )
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status_code}")

            itens = response.json()
            if not itens:
                break

            for item in itens:
                nome = str(item.get("name") or "").strip()
                if not nome:
                    continue
                caminho = f"{prefixo.rstrip('/')}/{nome}" if prefixo else nome
                if item.get("id") is None:
                    listar_prefixo(caminho)
                    continue

                metadata = item.get("metadata") or {}
                tamanho = metadata.get("size")
                try:
                    tamanho = int(tamanho) if tamanho is not None else None
                except (TypeError, ValueError):
                    tamanho = None

                encontrados.append(
                    {
                        "storage_path": caminho,
                        "tamanho_bytes": tamanho,
                        "mime_type": str(
                            metadata.get("mimetype")
                            or metadata.get("contentType")
                            or ""
                        ).strip(),
                        "updated_at": item.get("updated_at"),
                    }
                )

            if len(itens) < 1000:
                break
            offset += len(itens)

    listar_prefixo("")
    return encontrados


def auditar_fotos_storage():
    """Executa reconciliação somente leitura; nenhuma mutação é realizada."""
    conn = conectar()
    if conn is None:
        return False, {}, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pf.id,
                    pf.patrimonio_id,
                    pf.ordem,
                    pf.storage_bucket,
                    pf.storage_path,
                    pf.arquivo_nome,
                    pf.mime_type,
                    pf.tamanho_bytes,
                    pf.sha256,
                    p.numero_patrimonio
                FROM public.patrimonio_fotos AS pf
                LEFT JOIN public.patrimonios AS p ON p.id = pf.patrimonio_id
                ORDER BY pf.patrimonio_id, pf.ordem, pf.id
                """
            )
            colunas = [item.name for item in cur.description]
            rows = [dict(zip(colunas, row)) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT patrimonio_id, ordem, COUNT(*) AS quantidade
                FROM public.patrimonio_fotos
                GROUP BY patrimonio_id, ordem
                HAVING COUNT(*) > 1
                ORDER BY patrimonio_id, ordem
                """
            )
            ordens_duplicadas = [
                {
                    "patrimonio_id": int(patrimonio_id),
                    "ordem": int(ordem),
                    "quantidade": int(quantidade),
                }
                for patrimonio_id, ordem, quantidade in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT storage_path, COUNT(*) AS quantidade
                FROM public.patrimonio_fotos
                GROUP BY storage_path
                HAVING COUNT(*) > 1
                ORDER BY storage_path
                """
            )
            caminhos_duplicados = [
                {
                    "storage_path": str(path),
                    "quantidade": int(quantidade),
                }
                for path, quantidade in cur.fetchall()
            ]

        storage = _listar_storage_detalhado()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, {}, f"Falha na auditoria de fotos: {exc}"
    finally:
        conn.close()

    db_por_path = {}
    for row in rows:
        path = str(row["storage_path"] or "").strip()
        if path:
            db_por_path.setdefault(path, []).append(row)

    storage_por_path = {}
    for item in storage:
        path = str(item["storage_path"] or "").strip()
        if path:
            storage_por_path.setdefault(path, []).append(item)

    db_sem_storage = []
    storage_sem_db = []
    tamanhos_divergentes = []
    buckets_invalidos = []
    caminhos_invalidos = []
    hashes_invalidos = []

    for row in rows:
        path = str(row["storage_path"] or "").strip()
        bucket = str(row["storage_bucket"] or "").strip()
        if bucket != BUCKET:
            buckets_invalidos.append(
                {
                    "foto_id": row["id"],
                    "patrimonio_id": row["patrimonio_id"],
                    "bucket": bucket,
                    "storage_path": path,
                }
            )
        if path and not path.startswith(f"{int(row['patrimonio_id'])}/"):
            caminhos_invalidos.append(
                {
                    "foto_id": row["id"],
                    "patrimonio_id": row["patrimonio_id"],
                    "storage_path": path,
                }
            )

        sha = str(row["sha256"] or "").strip().lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            hashes_invalidos.append(
                {
                    "foto_id": row["id"],
                    "patrimonio_id": row["patrimonio_id"],
                    "sha256": sha,
                }
            )

        if path not in storage_por_path:
            db_sem_storage.append(
                {
                    "foto_id": row["id"],
                    "patrimonio_id": row["patrimonio_id"],
                    "numero_patrimonio": row["numero_patrimonio"],
                    "storage_path": path,
                }
            )
            continue

        item = storage_por_path[path][0]
        if item["tamanho_bytes"] is not None and int(row["tamanho_bytes"]) != item["tamanho_bytes"]:
            tamanhos_divergentes.append(
                {
                    "foto_id": row["id"],
                    "storage_path": path,
                    "db_tamanho_bytes": row["tamanho_bytes"],
                    "storage_tamanho_bytes": item["tamanho_bytes"],
                }
            )

    for item in storage:
        path = str(item["storage_path"] or "").strip()
        if path not in db_por_path:
            storage_sem_db.append(
                {
                    "storage_path": path,
                    "tamanho_bytes": item["tamanho_bytes"],
                    "mime_type": item["mime_type"],
                }
            )

    resultado = {
        "db_fotos": rows,
        "storage_objetos": storage,
        "db_sem_storage": db_sem_storage,
        "storage_sem_db": storage_sem_db,
        "tamanhos_divergentes": tamanhos_divergentes,
        "buckets_invalidos": buckets_invalidos,
        "caminhos_invalidos": caminhos_invalidos,
        "hashes_invalidos": hashes_invalidos,
        "ordens_duplicadas": ordens_duplicadas,
        "caminhos_duplicados": caminhos_duplicados,
    }
    return True, resultado, "Reconciliação concluída sem alterações."


def renderizar_auditoria_fotos():
    st.title("🔍 Auditoria de fotos — Patrimônio × Storage")
    st.caption(
        "Consulta somente leitura. A auditoria não envia, altera, move ou exclui imagens."
    )

    if st.button("🔄 Executar reconciliação", type="primary", use_container_width=True):
        with st.spinner("Consultando PostgreSQL e Storage..."):
            ok, resultado, mensagem = auditar_fotos_storage()
        if not ok:
            st.error(mensagem)
            return
        st.session_state["ultima_auditoria_fotos"] = resultado
        st.success(mensagem)

    resultado = st.session_state.get("ultima_auditoria_fotos")
    if not resultado:
        st.info("Execute a reconciliação para obter o diagnóstico atual.")
        return

    categorias = [
        ("DB sem Storage", resultado["db_sem_storage"]),
        ("Storage sem DB", resultado["storage_sem_db"]),
        ("Tamanho divergente", resultado["tamanhos_divergentes"]),
        ("Bucket inválido", resultado["buckets_invalidos"]),
        ("Caminho inválido", resultado["caminhos_invalidos"]),
        ("Hash inválido", resultado["hashes_invalidos"]),
        ("Ordem duplicada", resultado["ordens_duplicadas"]),
        ("Caminho duplicado", resultado["caminhos_duplicados"]),
    ]

    cols = st.columns(4)
    for col, (titulo, itens) in zip(cols * 2, categorias):
        col.metric(titulo, len(itens))

    total_divergencias = sum(len(itens) for _, itens in categorias)
    if total_divergencias == 0:
        st.success(
            f"✅ Tudo sincronizado: {len(resultado['db_fotos'])} metadado(s) "
            f"e {len(resultado['storage_objetos'])} objeto(s) conferidos."
        )
    else:
        st.warning(f"⚠️ Foram encontradas {total_divergencias} divergência(s).")

    for titulo, itens in categorias:
        if itens:
            with st.expander(f"{titulo} ({len(itens)})", expanded=True):
                st.dataframe(
                    pd.DataFrame(itens),
                    use_container_width=True,
                    hide_index=True,
                )

    with st.expander("ℹ️ Limite da comparação de hash"):
        st.write(
            "O SHA-256 cadastrado no PostgreSQL é validado quanto ao formato, "
            "mas não é recalculado a partir do objeto remoto nesta etapa. "
            "A API de listagem usada aqui não é tratada como fonte confiável "
            "para checksum físico. Portanto, nenhuma divergência de hash é inventada."
        )
