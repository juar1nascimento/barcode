"""Persistência PostgreSQL do GTI-SESA.

A integração é opcional: sem a Secret [postgresql], o sistema continua
operando com Google Sheets. Quando configurada, o cadastro é gravado no
PostgreSQL e, separadamente, no Google Sheets.
"""

import hashlib
import io
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


def salvar_foto_patrimonio(numero_patrimonio: str, unidade: str, image_file) -> Tuple[bool, str]:
    """Comprime, valida e grava/substitui a foto do patrimônio."""
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado; a foto não pode ser armazenada na tabela."
    try:
        dados, largura, altura, sha256 = preparar_foto_patrimonio(image_file)
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
            cur.execute(
                """INSERT INTO patrimonio_fotos
                     (patrimonio_id, imagem, mime_type, tamanho_bytes, largura, altura, sha256, atualizado_em)
                   VALUES (%s, %s, 'image/jpeg', %s, %s, %s, %s, NOW())
                   ON CONFLICT (patrimonio_id) DO UPDATE SET
                     imagem = EXCLUDED.imagem, mime_type = EXCLUDED.mime_type,
                     tamanho_bytes = EXCLUDED.tamanho_bytes, largura = EXCLUDED.largura,
                     altura = EXCLUDED.altura, sha256 = EXCLUDED.sha256, atualizado_em = NOW()""",
                (patrimonio_id, dados, len(dados), largura, altura, sha256),
            )
        conn.commit()
        return True, f"Foto armazenada no PostgreSQL ({len(dados) // 1024} KiB)."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao armazenar a foto no PostgreSQL: {exc}"
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
        return True, "PostgreSQL não configurado; persistência principal ainda não ativada."

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
