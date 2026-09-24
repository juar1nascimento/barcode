"""Persistência PostgreSQL do GTI-SESA.

O PostgreSQL é a persistência principal do inventário. O Google Sheets pode
ser usado separadamente como espelho operacional.
"""

import base64
import hashlib
import io
import json
import re
from datetime import datetime
from typing import Optional, Tuple

import streamlit as st

TIPOS_PATRIMONIO = (
    "CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos"
)


def _conexao_configurada() -> bool:
    try:
        sec = st.secrets.get("postgresql")
        if not sec:
            return False
        if sec.get("url"):
            return True
        obrigatorios = ("host", "dbname", "user", "password")
        return all(sec.get(k) for k in obrigatorios)
    except Exception:
        return False


def _config() -> dict:
    sec = st.secrets["postgresql"]
    return {
        "host": sec.get("host"),
        "port": int(sec.get("port", 5432)),
        "dbname": sec.get("dbname") or sec.get("database"),
        "user": sec.get("user"),
        "password": sec.get("password"),
        "sslmode": sec.get("sslmode", "require"),
    }


def conectar() -> Optional[object]:
    if not _conexao_configurada():
        return None
    try:
        import psycopg
        sec = st.secrets["postgresql"]
        url = str(sec.get("url") or "").strip()
        if url:
            return psycopg.connect(url)

        cfg = _config()
        obrigatorios = ("host", "dbname", "user", "password")
        if any(not cfg.get(k) for k in obrigatorios):
            return None
        return psycopg.connect(**cfg)
    except Exception:
        st.warning("PostgreSQL indisponível. Verifique a Secret [postgresql].")
        return None


def _dividir_setor(setor: str) -> Tuple[str, Optional[int], Optional[str]]:
    texto = re.sub(r"\s+", " ", str(setor or "").strip())
    m = re.fullmatch(r"Consultório\s+(\d+)\s*-\s*(.+)", texto, flags=re.I)
    if m:
        numero = int(m.group(1))
        especialidade = m.group(2).strip()
        return "Consultório", numero, especialidade or None
    return texto, None, None


def _tipo_unidade(unidade: str) -> str:
    texto = str(unidade or "").strip()
    if texto.casefold() == "almoxarifado central sesa".casefold():
        return "ALMOX"
    return "URS" if texto.upper().startswith("URS ") else "UBS"


def garantir_unidade(cur, unidade: str) -> int:
    tipo = _tipo_unidade(unidade)
    cur.execute(
        """INSERT INTO unidades (nome, tipo) VALUES (%s, %s)
           ON CONFLICT (nome) DO UPDATE SET tipo = EXCLUDED.tipo
           RETURNING id""",
        (str(unidade).strip(), tipo),
    )
    return cur.fetchone()[0]


def garantir_setor(cur, unidade_id: int, setor: str) -> int:
    """Obtém/cria o setor respeitando as regras do schema definitivo.

    A busca usa IS NOT DISTINCT FROM para comparar corretamente os campos
    opcionais dos setores normais. A inserção usa ON CONFLICT DO NOTHING,
    seguida de nova busca, permitindo que a restrição única do banco seja a
    autoridade final em caso de concorrência.
    """
    nome, numero, especialidade = _dividir_setor(setor)

    cur.execute(
        """SELECT id
             FROM setores
            WHERE unidade_id = %s
              AND nome = %s
              AND numero_consultorio IS NOT DISTINCT FROM %s
              AND especialidade IS NOT DISTINCT FROM %s
            LIMIT 1""",
        (unidade_id, nome, numero, especialidade),
    )
    existente = cur.fetchone()
    if existente:
        cur.execute("UPDATE setores SET ativo = TRUE WHERE id = %s", (existente[0],))
        return existente[0]

    cur.execute(
        """INSERT INTO setores
             (unidade_id, nome, numero_consultorio, especialidade)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        (unidade_id, nome, numero, especialidade),
    )
    criado = cur.fetchone()
    if criado:
        return criado[0]

    # Outra transação pode ter criado o mesmo setor entre a busca e o INSERT.
    cur.execute(
        """SELECT id
             FROM setores
            WHERE unidade_id = %s
              AND nome = %s
              AND numero_consultorio IS NOT DISTINCT FROM %s
              AND especialidade IS NOT DISTINCT FROM %s
            LIMIT 1""",
        (unidade_id, nome, numero, especialidade),
    )
    existente = cur.fetchone()
    if not existente:
        raise RuntimeError("Não foi possível obter o setor após a inserção.")
    cur.execute("UPDATE setores SET ativo = TRUE WHERE id = %s", (existente[0],))
    return existente[0]


MAX_FOTO_DIMENSAO = 1600
MAX_FOTO_BYTES = 1024 * 1024
FOTO_QUALIDADE_JPEG = 78


def preparar_foto_patrimonio(image_file) -> Tuple[bytes, int, int, str]:
    """Reduz e comprime a foto antes do envio ao PostgreSQL."""
    from PIL import Image, ImageOps
    if hasattr(image_file, "getvalue"):
        bruto = image_file.getvalue()
    elif isinstance(image_file, (bytes, bytearray, memoryview)):
        bruto = bytes(image_file)
    else:
        bruto = image_file.read()
    if not bruto:
        raise ValueError("A foto está vazia.")
    with Image.open(io.BytesIO(bruto)) as original:
        imagem = ImageOps.exif_transpose(original)
        imagem.thumbnail((MAX_FOTO_DIMENSAO, MAX_FOTO_DIMENSAO), Image.Resampling.LANCZOS)
        if imagem.mode not in ("RGB", "L"):
            imagem = imagem.convert("RGB")
        qualidade = FOTO_QUALIDADE_JPEG
        while True:
            buffer = io.BytesIO()
            imagem.save(buffer, format="JPEG", quality=qualidade, optimize=True)
            dados = buffer.getvalue()
            if len(dados) <= MAX_FOTO_BYTES or qualidade <= 55:
                break
            qualidade -= 8
        largura, altura = imagem.size
    if len(dados) > MAX_FOTO_BYTES:
        raise ValueError("A foto continua maior que 1 MiB após a compressão.")
    return dados, largura, altura, hashlib.sha256(dados).hexdigest()


def _obter_patrimonio_id(cur, numero_patrimonio: str, unidade: str):
    cur.execute(
        """SELECT p.id FROM patrimonios p JOIN unidades u ON u.id = p.unidade_id
             WHERE p.numero_patrimonio = %s AND u.nome = %s LIMIT 1""",
        (str(numero_patrimonio or "").strip(), str(unidade or "").strip()),
    )
    row = cur.fetchone()
    return row[0] if row else None


def montar_registro_foto(serial: str, dados: bytes, largura: int, altura: int, sha256: str) -> dict:
    """Monta o item sequencial armazenado na coluna fotos."""
    serial_original = str(serial or "").strip()
    if not serial_original:
        raise ValueError("O número serial da etiqueta é obrigatório.")
    nome_arquivo = re.sub(r"[^A-Za-z0-9._-]+", "_", serial_original) + ".jpg"
    return {
        "nome": serial_original,
        "arquivo_nome": nome_arquivo,
        "mime_type": "image/jpeg",
        "tamanho_bytes": len(dados),
        "largura": largura,
        "altura": altura,
        "sha256": sha256,
        "imagem_base64": base64.b64encode(dados).decode("ascii"),
    }


def salvar_foto_patrimonio(numero_patrimonio: str, unidade: str, image_file, serial: str = "") -> Tuple[bool, str]:
    """Acrescenta uma foto à coluna fotos do próprio patrimônio."""
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado; a foto não pode ser armazenada na tabela de patrimônios."
    try:
        dados, largura, altura, sha256 = preparar_foto_patrimonio(image_file)
        registro = montar_registro_foto(serial or numero_patrimonio, dados, largura, altura, sha256)
    except Exception as exc:
        return False, f"Não foi possível preparar a foto: {exc}"
    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL para armazenar a foto."
    try:
        with conn.cursor() as cur:
            patrimonio_id = _obter_patrimonio_id(cur, numero_patrimonio, unidade)
            if patrimonio_id is None:
                return False, f"Patrimônio `{numero_patrimonio}` não encontrado na unidade `{unidade}`."
            cur.execute("SELECT COALESCE(fotos, '[]'::jsonb) FROM patrimonios WHERE id = %s FOR UPDATE", (patrimonio_id,))
            row = cur.fetchone()
            fotos = row[0] if row and row[0] else []
            if not isinstance(fotos, list):
                fotos = []
            fotos.append(registro)
            cur.execute("UPDATE patrimonios SET fotos = %s::jsonb, atualizado_em = NOW() WHERE id = %s", (json.dumps(fotos, ensure_ascii=False), patrimonio_id))
        conn.commit()
        return True, f"Foto `{registro['nome']}` armazenada na ficha do patrimônio como foto {len(fotos)} ({len(dados) // 1024} KiB)."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao armazenar a foto no PostgreSQL: {exc}"
    finally:
        conn.close()



def salvar_patrimonios_em_lote(registros, unidade: str) -> Tuple[bool, str]:
    """Grava todo o lote em uma única transação PostgreSQL."""
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado. Cadastro em lote bloqueado."

    unidade = str(unidade or "").strip()
    registros = list(registros or [])
    if not unidade or not registros:
        return False, "Lote ou unidade inválidos."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            for item in registros:
                numero = str(item.get("numero_patrimonio", "") or item.get("codigo_barras", "")).strip()
                codigo = str(item.get("codigo_barras", "")).strip() or None
                tipo = str(item.get("tipo_patrimonio", "")).strip()
                setor = re.sub(r"\s+", " ", str(item.get("setor", "")).strip())
                fabricante = str(item.get("fabricante", "")).strip() or None
                if not numero or tipo not in TIPOS_PATRIMONIO or not setor:
                    raise ValueError(f"Dados inválidos para o patrimônio '{numero}'.")
                setor_id = garantir_setor(cur, unidade_id, setor)
                cur.execute(
                    """INSERT INTO patrimonios
                         (unidade_id, setor_id, tipo, numero_patrimonio,
                          codigo_barras, fabricante, data_cadastro, atualizado_em)
                       VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())""",
                    (unidade_id, setor_id, tipo, numero, codigo, fabricante),
                )
        conn.commit()
        return True, str(len(registros)) + " patrimônio(s) gravado(s) no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, "O lote foi cancelado integralmente porque existe número ou código de patrimônio duplicado no PostgreSQL."
        return False, f"Lote cancelado integralmente no PostgreSQL: {texto}"
    finally:
        conn.close()



def atualizar_patrimonio(
    numero_patrimonio_original: str,
    codigo_barras: str,
    tipo: str,
    setor: str,
    unidade: str,
    fabricante: str = "",
    numero_patrimonio: str = "",
    unidade_original: str = "",
) -> Tuple[bool, str]:
    """Atualiza um patrimônio existente sem recriar a linha.

    A atualização preserva o mesmo patrimonio_id e eventual foto vinculada.
    """
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado. Edição bloqueada para evitar divergência."

    numero_original = str(numero_patrimonio_original or "").strip()
    numero_novo = str(numero_patrimonio or "").strip() or numero_original
    codigo = str(codigo_barras or "").strip() or None
    tipo = str(tipo or "").strip()
    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    unidade = str(unidade or "").strip()
    unidade_original = str(unidade_original or "").strip()
    fabricante = str(fabricante or "").strip() or None

    if not numero_original or not numero_novo or not tipo or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
        return False, "Dados insuficientes ou inválidos para atualizar o patrimônio."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            if unidade_original:
                cur.execute(
                    """SELECT p.id
                         FROM patrimonios p
                         JOIN unidades u ON u.id = p.unidade_id
                        WHERE p.numero_patrimonio = %s
                          AND u.nome = %s
                        LIMIT 1""",
                    (numero_original, unidade_original),
                )
            else:
                cur.execute(
                    """SELECT id FROM patrimonios
                        WHERE numero_patrimonio = %s
                        LIMIT 1""",
                    (numero_original,),
                )
            row = cur.fetchone()
            if not row:
                return False, f"O patrimônio original `{numero_original}` não foi encontrado no PostgreSQL."

            patrimonio_id = row[0]
            unidade_id = garantir_unidade(cur, unidade)
            setor_id = garantir_setor(cur, unidade_id, setor)

            cur.execute(
                """UPDATE patrimonios
                      SET unidade_id = %s,
                          setor_id = %s,
                          tipo = %s,
                          numero_patrimonio = %s,
                          codigo_barras = %s,
                          fabricante = %s,
                          atualizado_em = NOW()
                    WHERE id = %s""",
                (unidade_id, setor_id, tipo, numero_novo, codigo, fabricante, patrimonio_id),
            )
        conn.commit()
        return True, "Patrimônio atualizado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, f"O número/código do patrimônio `{numero_novo}` já está em uso no PostgreSQL."
        return False, f"Falha ao atualizar o patrimônio no PostgreSQL: {texto}"
    finally:
        conn.close()



def listar_patrimonios(unidade: str):
    """Retorna os patrimônios da unidade diretamente do PostgreSQL."""
    if not _conexao_configurada():
        return None, "PostgreSQL não configurado."
    conn = conectar()
    if conn is None:
        return None, "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.numero_patrimonio, p.tipo, p.fabricante,
                          s.nome, s.numero_consultorio, s.especialidade
                     FROM patrimonios p
                     JOIN unidades u ON u.id = p.unidade_id
                     JOIN setores s ON s.id = p.setor_id
                    WHERE u.nome = %s
                    ORDER BY p.numero_patrimonio""",
                (str(unidade).strip(),),
            )
            linhas = cur.fetchall()
        return linhas, ""
    except Exception as exc:
        conn.rollback()
        return None, f"Erro ao consultar PostgreSQL: {exc}"
    finally:
        conn.close()



def salvar_patrimonio(
    codigo_barras: str,
    tipo: str,
    setor: str,
    unidade: str,
    fabricante: str = "",
    numero_patrimonio: str = "",
) -> Tuple[bool, str]:
    """Grava um patrimônio no PostgreSQL e retorna (sucesso, mensagem).

    A transação é atômica. Duplicidades são tratadas pelo banco e não geram
    segunda linha. Esta função não grava no Google Sheets; o chamador faz o
    espelhamento separadamente para manter as duas persistências independentes.
    """
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado. Cadastros foram bloqueados para evitar gravação somente no Google Sheets."

    numero = str(numero_patrimonio or "").strip() or str(codigo_barras or "").strip()
    codigo = str(codigo_barras or "").strip() or None
    tipo = str(tipo or "").strip()
    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    unidade = str(unidade or "").strip()
    fabricante = str(fabricante or "").strip() or None

    if not numero or not tipo or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
        return False, "Dados insuficientes ou inválidos para o PostgreSQL."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            setor_id = garantir_setor(cur, unidade_id, setor)
            cur.execute(
                """INSERT INTO patrimonios
                     (unidade_id, setor_id, tipo, numero_patrimonio,
                      codigo_barras, fabricante, data_cadastro, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""",
                (unidade_id, setor_id, tipo, numero, codigo, fabricante, datetime.now()),
            )
        conn.commit()
        return True, "Patrimônio gravado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, f"O patrimônio `{numero}` já existe no PostgreSQL."
        return False, f"Falha ao gravar no PostgreSQL: {texto}"
    finally:
        conn.close()
