"""Consumidor idempotente das filas de sincronização PostgreSQL -> Google Sheets.

O PostgreSQL permanece como fonte operacional. Este módulo somente espelha
eventos confirmados para o Sheets e registra o resultado no outbox.
"""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import quote

import streamlit as st
from psycopg import sql

from postgresql_persistencia import conectar
from supabase_storage import criar_url_assinada_storage
from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    _garantir_cabecalho_moderno,
    _garantir_coluna_patrimonio_texto,
    _normalizar_unidade_aba,
    _obter_aba_gravacao,
    _chave_texto,
    conectar_google_sheets,
)
from google_sheets_schema import auditar_e_padronizar_abas_inventario

MAX_TENTATIVAS = 5
STALE_MINUTES = 15
FOTO_PREFIXO_COLUNA = "Foto "
FOTO_THUMBNAIL_SIZE = 96
FOTO_MAX_COLUNAS = 12


def _public_photo_url(bucket: str, path: str) -> str:
    """Retorna URL temporária de objeto privado para o espelho do Sheets."""
    try:
        return criar_url_assinada_storage(bucket, path, expires_in=31536000)
    except Exception as exc:
        raise RuntimeError("Não foi possível gerar URL temporária da foto.") from exc


def _marcar_evento(conn, tabela: str, event_id: int, *, status: str, erro: str | None = None,
                   sincronizado: bool = False, tentativas: int | None = None) -> None:
    if tabela not in {"patrimonios_sheets_outbox", "patrimonio_fotos_sheets_outbox"}:
        raise ValueError("Tabela de outbox inválida.")
    colunas = [
        "status=%s",
        "processando_em=NULL",
        "ultimo_erro=%s",
        "atualizado_em=now()",
    ]
    params: list[object] = [status, erro[:1000] if erro else None]
    if sincronizado:
        colunas.append("sincronizado_em=now()")
    if tentativas is not None:
        colunas.append("tentativas=%s")
        params.append(tentativas)
    elif status == "failed":
        colunas.append("proxima_tentativa_em=now() + make_interval(secs => LEAST(3600, 30 * (2 ^ GREATEST(0, tentativas))))")
    params.append(event_id)
    with conn.cursor() as cur:
        consulta = sql.SQL("UPDATE public.{tabela} SET {colunas} WHERE id=%s").format(
            tabela=sql.Identifier(tabela),
            colunas=sql.SQL(", ").join(sql.SQL(coluna) for coluna in colunas),
        )
        cur.execute(consulta, params)


def _claim(tabela: str, limit: int) -> list[dict]:
    if tabela not in {"patrimonios_sheets_outbox", "patrimonio_fotos_sheets_outbox"}:
        raise ValueError("Tabela de outbox inválida.")
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            foto_coluna = sql.SQL("o.foto_id") if tabela == "patrimonio_fotos_sheets_outbox" else sql.SQL("NULL::bigint")
            consulta = sql.SQL(
                """
                WITH candidatos AS (
                    SELECT id
                      FROM {tabela}
                     WHERE (
                         status='pending'
                         AND proxima_tentativa_em <= now()
                         AND tentativas < %s
                     ) OR (
                         status='processing'
                         AND processando_em < now() - make_interval(mins => %s)
                     )
                     ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT %s
                )
                UPDATE {tabela} o
                   SET status='processing',
                       processando_em=now(),
                       tentativas=CASE
                           WHEN o.status='processing' THEN o.tentativas
                           ELSE o.tentativas + 1
                       END,
                       atualizado_em=now()
                  FROM candidatos c
                 WHERE o.id=c.id
             RETURNING o.id, o.patrimonio_id, {foto_coluna}, o.tentativas
                """
            ).format(tabela=sql.Identifier(tabela), foto_coluna=foto_coluna)
            cur.execute(
                consulta,
                (MAX_TENTATIVAS, STALE_MINUTES, max(1, min(limit, 100))),
            )
            rows = cur.fetchall()
        conn.commit()
        return [
            {"id": int(r[0]), "patrimonio_id": int(r[1]), "foto_id": int(r[2]) if r[2] is not None else None,
             "tentativas": int(r[3])}
            for r in rows
        ]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _buscar_patrimonio(patrimonio_id: int) -> dict:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id,p.numero_patrimonio,p.codigo_barras,p.tipo,p.fabricante,
                          p.data_cadastro,u.nome,s.nome
                     FROM public.patrimonios p
                     JOIN public.unidades u ON u.id=p.unidade_id
                     LEFT JOIN public.setores s ON s.id=p.setor_id
                    WHERE p.id=%s""",
                (patrimonio_id,),
            )
            r = cur.fetchone()
        if not r:
            raise RuntimeError(f"Patrimônio {patrimonio_id} não encontrado.")
        return {
            "id": int(r[0]), "numero": str(r[1]), "codigo": str(r[2] or ""),
            "tipo": str(r[3]), "fabricante": str(r[4] or ""),
            "data": str(r[5] or ""), "unidade": str(r[6]), "setor": str(r[7] or ""),
        }
    finally:
        conn.close()


def _espelhar_patrimonio(item: dict) -> None:
    patrimonio = _buscar_patrimonio(item["patrimonio_id"])
    planilha = conectar_google_sheets()
    if not planilha:
        raise RuntimeError(st.session_state.get("sheets_sync_ultimo_erro", "Google Sheets indisponível."))

    aba = _obter_aba_gravacao(
        planilha,
        _normalizar_unidade_aba(patrimonio["unidade"]),
        2,
    )
    _garantir_coluna_patrimonio_texto(aba)
    if not _garantir_cabecalho_moderno(aba):
        raise RuntimeError("Cabeçalho da aba não corresponde ao schema canônico do inventário.")

    valores = [
        patrimonio["setor"],
        patrimonio["tipo"],
        patrimonio["numero"],
        patrimonio["fabricante"],
        patrimonio["data"],
        patrimonio["codigo"],
    ]
    atuais = aba.get_all_values()
    for indice, linha in enumerate(atuais[1:], start=2):
        if len(linha) > 2 and _chave_texto(linha[2]) == _chave_texto(patrimonio["numero"]):
            aba.update(values=[valores], range_name=f"A{indice}:{_coluna(len(COLUNAS_INVENTARIO))}{indice}", value_input_option="RAW")
            return

    aba.append_row(valores, value_input_option="RAW", insert_data_option="INSERT_ROWS")


def _buscar_foto(foto_id: int) -> dict:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT f.id,f.patrimonio_id,f.ordem,f.storage_bucket,f.storage_path,
                          p.numero_patrimonio,u.nome,
                          f.drive_file_id,f.drive_file_name,f.drive_folder_id,f.drive_web_url
                     FROM public.patrimonio_fotos f
                     JOIN public.patrimonios p ON p.id=f.patrimonio_id
                     JOIN public.unidades u ON u.id=p.unidade_id
                    WHERE f.id=%s""",
                (foto_id,),
            )
            r = cur.fetchone()
        if not r:
            raise RuntimeError(f"Foto {foto_id} não encontrada.")
        return {
            "id": int(r[0]), "patrimonio_id": int(r[1]), "ordem": int(r[2]),
            "bucket": str(r[3]), "path": str(r[4]), "numero": str(r[5]),
            "unidade": str(r[6]),
            "drive_file_id": str(r[7] or ""),
            "drive_file_name": str(r[8] or ""),
            "drive_folder_id": str(r[9] or ""),
            "drive_web_url": str(r[10] or ""),
        }
    finally:
        conn.close()


def _garantir_colunas_fotos(aba, quantidade: int) -> None:
    headers = [str(v).strip() for v in (aba.row_values(1) or [])]
    alvo = 5 + max(1, min(quantidade, FOTO_MAX_COLUNAS))
    novos = []
    for ordem in range(1, max(1, min(quantidade, FOTO_MAX_COLUNAS)) + 1):
        nome = f"{FOTO_PREFIXO_COLUNA}{ordem:02d}"
        if nome not in headers:
            novos.append(nome)
    if novos:
        inicio = max(6, len(headers) + 1)
        fim = inicio + len(novos) - 1
        aba.update(values=[headers + novos], range_name=f"A1:{_coluna(fim)}1", value_input_option="RAW")


def _coluna(numero: int) -> str:
    resultado = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        resultado = chr(65 + resto) + resultado
    return resultado


def _nome_foto_drive(foto: dict) -> str:
    nome = str(foto.get("drive_file_name") or "").strip()
    return nome or f"{foto['numero']} - Foto {int(foto['ordem']):02d}.jpg"


def _separador_formula_sheets(planilha) -> str:
    """Retorna o separador de argumentos conforme a localidade da planilha."""
    try:
        metadata = planilha.fetch_sheet_metadata()
        locale = str((metadata.get("properties") or {}).get("locale") or "").lower()
        return ";" if locale.startswith(("pt", "es", "de", "fr", "it", "nl")) else ","
    except Exception:
        # A planilha atual é corporativa em português; falhar fechado para o
        # formato compatível com pt-BR evita o erro de análise de fórmula.
        return ";"


def _normalizar_cabecalhos_fotos(aba) -> list[str]:
    """Migra cabeçalhos legados 'Foto 1' para o padrão 'Foto 01' sem duplicar colunas."""
    headers = [str(v).strip() for v in (aba.row_values(1) or [])]
    alterados = False
    for indice, header in enumerate(headers):
        match = re.fullmatch(r"Foto (\\d+)", header, flags=re.IGNORECASE)
        if not match:
            continue
        ordem = int(match.group(1))
        if 1 <= ordem <= FOTO_MAX_COLUNAS:
            novo = f"{FOTO_PREFIXO_COLUNA}{ordem:02d}"
            if novo != header:
                headers[indice] = novo
                alterados = True
    if alterados:
        aba.update(values=[headers], range_name=f"A1:{_coluna(len(headers))}1", value_input_option="RAW")
    return headers


def _espelhar_foto(item: dict) -> None:
    foto = _buscar_foto(item["foto_id"])
    patrimonio = _buscar_patrimonio(foto["patrimonio_id"])
    planilha = conectar_google_sheets()
    if not planilha:
        raise RuntimeError(st.session_state.get("sheets_sync_ultimo_erro", "Google Sheets indisponível."))

    aba = _obter_aba_gravacao(
        planilha,
        _normalizar_unidade_aba(foto["unidade"]),
        2,
    )
    _garantir_coluna_patrimonio_texto(aba)
    if not _garantir_cabecalho_moderno(aba):
        raise RuntimeError("Cabeçalho da aba não corresponde ao schema canônico do inventário.")

    _garantir_colunas_fotos(aba, foto["ordem"])
    headers = _normalizar_cabecalhos_fotos(aba)
    if foto["ordem"] > FOTO_MAX_COLUNAS:
        raise RuntimeError("Limite de fotos por patrimônio excedido para o modelo tabular do Sheets.")
    coluna_nome = f"{FOTO_PREFIXO_COLUNA}{foto['ordem']:02d}"
    coluna = headers.index(coluna_nome) + 1
    if coluna <= 5:
        raise RuntimeError("Coluna de foto inválida.")

    atuais = aba.get_all_values()
    linha_planilha = None
    for indice, linha in enumerate(atuais[1:], start=2):
        if len(linha) > 2 and _chave_texto(linha[2]) == _chave_texto(patrimonio["numero"]):
            linha_planilha = indice
            break

    if linha_planilha is None:
        _espelhar_patrimonio({"patrimonio_id": foto["patrimonio_id"]})
        atuais = aba.get_all_values()
        for indice, linha in enumerate(atuais[1:], start=2):
            if len(linha) > 2 and _chave_texto(linha[2]) == _chave_texto(patrimonio["numero"]):
                linha_planilha = indice
                break

    if linha_planilha is None:
        raise RuntimeError(f"Linha do patrimônio {patrimonio['numero']} não encontrada no Sheets.")

    drive_url = str(foto.get("drive_web_url") or "").strip()
    if not drive_url:
        # Fail-closed: a foto não pode ser marcada como sincronizada no Sheets
        # enquanto o repositório corporativo do Drive não confirmar o arquivo.
        raise RuntimeError("Foto ainda não está disponível no repositório corporativo do Google Drive.")

    nome = _nome_foto_drive(foto).replace(chr(34), chr(34) + chr(34))
    url_planilha = drive_url.replace(chr(34), chr(34) + chr(34))
    separador = _separador_formula_sheets(planilha)
    formula = f'=HYPERLINK("{url_planilha}"{separador}"{nome}")'
    aba.update_cell(linha_planilha, coluna, formula, value_input_option="USER_ENTERED")


def _espelhar_fotos_do_patrimonio(patrimonio_id: int) -> None:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM public.patrimonio_fotos
                   WHERE patrimonio_id=%s ORDER BY ordem, id""",
                (patrimonio_id,),
            )
            fotos = [int(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()

    for foto_id in fotos:
        _espelhar_foto({"foto_id": foto_id, "patrimonio_id": patrimonio_id})


def _processar_evento(tabela: str, item: dict) -> None:
    if tabela == "patrimonios_sheets_outbox":
        _espelhar_patrimonio(item)
    else:
        if item.get("foto_id") is not None:
            _espelhar_foto(item)
        else:
            # Compatibilidade com eventos antigos sem foto_id.
            _espelhar_fotos_do_patrimonio(item["patrimonio_id"])


def processar_fila_google_sheets(limit: int = 25) -> dict:
    """Audita/padroniza a estrutura do Sheets antes de consumir o outbox."""
    planilha_preflight = conectar_google_sheets()
    if not planilha_preflight:
        raise RuntimeError(
            st.session_state.get(
                "sheets_sync_ultimo_erro",
                "Google Sheets indisponível para preflight estrutural.",
            )
        )
    auditoria = auditar_e_padronizar_abas_inventario(planilha_preflight, aplicar=True)

    resultado = {
        "processados": 0,
        "sucesso": 0,
        "falhas": 0,
        "auditoria_estrutura": auditoria,
    }
    for tabela in ("patrimonios_sheets_outbox", "patrimonio_fotos_sheets_outbox"):
        itens = _claim(tabela, limit)
        for item in itens:
            resultado["processados"] += 1
            conn = conectar()
            if conn is None:
                resultado["falhas"] += 1
                continue
            try:
                _processar_evento(tabela, item)
                _marcar_evento(conn, tabela, item["id"], status="synced", sincronizado=True)
                conn.commit()
                resultado["sucesso"] += 1
            except Exception as exc:
                conn.rollback()
                conn = conectar()
                if conn is None:
                    resultado["falhas"] += 1
                    continue
                try:
                    tentativas = item["tentativas"]
                    status = "dead_letter" if tentativas >= MAX_TENTATIVAS else "failed"
                    _marcar_evento(
                        conn, tabela, item["id"], status=status,
                        erro=str(exc), tentativas=tentativas,
                    )
                    conn.commit()
                finally:
                    conn.close()
                resultado["falhas"] += 1
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    return resultado
