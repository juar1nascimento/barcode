"""Camada de persistência PostgreSQL do GTI-SESA.

Esta camada concentra operações de unidade, setor e patrimônio.
Durante a transição, o Google Sheets continua podendo atuar como espelho,
mas não deve ser usado para decidir a existência de um patrimônio quando
PostgreSQL estiver configurado.
"""

import re
from datetime import datetime
from typing import Optional, Tuple

import streamlit as st

TIPOS_PATRIMONIO = ("CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos")
TIPOS_UNIDADE = ("UBS", "URS", "ALMOXARIFADO")


def _conexao_configurada() -> bool:
    try:
        sec = st.secrets.get("postgresql")
        if not sec:
            return False
        if sec.get("url"):
            return True
        return all(sec.get(k) for k in ("host", "dbname", "user", "password"))
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
        return psycopg.connect(url) if url else psycopg.connect(**_config())
    except Exception as exc:
        st.warning(f"PostgreSQL indisponível. Verifique a Secret [postgresql]: {exc}")
        return None


def _dividir_setor(setor: str) -> Tuple[str, Optional[int], Optional[str]]:
    texto = re.sub(r"\s+", " ", str(setor or "").strip())
    m = re.fullmatch(r"Consultório\s+(\d+)\s*-\s*(.+)", texto, flags=re.I)
    if m:
        return "Consultório", int(m.group(1)), m.group(2).strip() or None
    return texto, None, None


def _tipo_unidade(unidade: str) -> str:
    nome = str(unidade or "").strip()
    if nome.casefold() == "almoxarifado central sesa":
        return "ALMOXARIFADO"
    if nome.upper().startswith("URS "):
        return "URS"
    return "UBS"


def garantir_unidade(cur, unidade: str) -> int:
    nome = str(unidade).strip()
    tipo = _tipo_unidade(nome)
    cur.execute(
        """INSERT INTO unidades (nome, tipo) VALUES (%s, %s)
           ON CONFLICT (nome) DO UPDATE SET tipo = EXCLUDED.tipo, ativo = TRUE
           RETURNING id""",
        (nome, tipo),
    )
    return cur.fetchone()[0]


def garantir_setor(cur, unidade_id: int, setor: str) -> int:
    nome, numero, especialidade = _dividir_setor(setor)
    cur.execute(
        """SELECT id FROM setores
           WHERE unidade_id = %s AND nome = %s
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
           ON CONFLICT DO NOTHING RETURNING id""",
        (unidade_id, nome, numero, especialidade),
    )
    criado = cur.fetchone()
    if criado:
        return criado[0]

    cur.execute(
        """SELECT id FROM setores
           WHERE unidade_id = %s AND nome = %s
             AND numero_consultorio IS NOT DISTINCT FROM %s
             AND especialidade IS NOT DISTINCT FROM %s
           LIMIT 1""",
        (unidade_id, nome, numero, especialidade),
    )
    existente = cur.fetchone()
    if not existente:
        raise RuntimeError("Não foi possível obter o setor após a inserção.")
    return existente[0]


def salvar_patrimonio(codigo_barras: str, tipo: str, setor: str, unidade: str,
                      fabricante: str = "", numero_patrimonio: str = "",
                      foto_bytes: Optional[bytes] = None) -> Tuple[bool, str]:
    if not _conexao_configurada():
        return True, "PostgreSQL não configurado; persistência ainda não ativada."

    numero = str(numero_patrimonio or "").strip() or str(codigo_barras or "").strip()
    codigo = str(codigo_barras or "").strip() or None
    tipo = str(tipo or "").strip()
    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    unidade = str(unidade or "").strip()
    fabricante = str(fabricante or "").strip() or None

    if not numero or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
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
                    codigo_barras, fabricante, data_cadastro, atualizado_em, foto)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)""",
                (unidade_id, setor_id, tipo, numero, codigo, fabricante, datetime.now(), foto_bytes),
            )
        conn.commit()
        return True, "Patrimônio gravado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, f"O patrimônio {numero} já existe no PostgreSQL."
        return False, f"Falha ao gravar no PostgreSQL: {texto}"
    finally:
        conn.close()


def listar_unidades(apenas_ativas: bool = True):
    conn = conectar()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, tipo FROM unidades WHERE (%s = FALSE OR ativo = TRUE) ORDER BY tipo, nome",
                (apenas_ativas,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def listar_setores(unidade: str, apenas_ativos: bool = True):
    conn = conectar()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.nome, s.numero_consultorio, s.especialidade
                   FROM setores s JOIN unidades u ON u.id = s.unidade_id
                   WHERE u.nome = %s AND (%s = FALSE OR s.ativo = TRUE)
                   ORDER BY s.nome, s.numero_consultorio, s.especialidade""",
                (str(unidade).strip(), apenas_ativos),
            )
            return cur.fetchall()
    finally:
        conn.close()


def listar_patrimonios(unidade: Optional[str] = None, setor: Optional[str] = None):
    conn = conectar()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id, u.nome, s.nome, s.numero_consultorio, s.especialidade,
                          p.tipo, p.numero_patrimonio, p.codigo_barras, p.fabricante,
                          p.data_cadastro, p.atualizado_em,
                          (p.foto IS NOT NULL) AS possui_foto
                   FROM patrimonios p
                   JOIN unidades u ON u.id = p.unidade_id
                   JOIN setores s ON s.id = p.setor_id
                   WHERE (%s IS NULL OR u.nome = %s)
                     AND (%s IS NULL OR s.nome = %s)
                   ORDER BY p.numero_patrimonio""",
                (unidade, unidade, setor, setor),
            )
            return cur.fetchall()
    finally:
        conn.close()


def atualizar_patrimonio(patrimonio_id: int, tipo: str, setor: str, unidade: str,
                         fabricante: str = "", numero_patrimonio: str = "",
                         codigo_barras: str = "", foto_bytes: Optional[bytes] = None) -> Tuple[bool, str]:
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."

    try:
        numero = str(numero_patrimonio or "").strip()
        if not numero or tipo not in TIPOS_PATRIMONIO:
            return False, "Número de patrimônio e tipo são obrigatórios."
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            setor_id = garantir_setor(cur, unidade_id, setor)
            if foto_bytes is None:
                cur.execute(
                    """UPDATE patrimonios
                       SET unidade_id=%s, setor_id=%s, tipo=%s, numero_patrimonio=%s,
                           codigo_barras=%s, fabricante=%s, atualizado_em=NOW()
                       WHERE id=%s""",
                    (unidade_id, setor_id, tipo, numero, str(codigo_barras).strip() or None,
                     str(fabricante).strip() or None, patrimonio_id),
                )
            else:
                cur.execute(
                    """UPDATE patrimonios
                       SET unidade_id=%s, setor_id=%s, tipo=%s, numero_patrimonio=%s,
                           codigo_barras=%s, fabricante=%s, foto=%s, atualizado_em=NOW()
                       WHERE id=%s""",
                    (unidade_id, setor_id, tipo, numero, str(codigo_barras).strip() or None,
                     str(fabricante).strip() or None, foto_bytes, patrimonio_id),
                )
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Patrimônio não encontrado."
        conn.commit()
        return True, "Patrimônio atualizado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
            return False, "Número patrimonial ou código de barras já utilizado."
        return False, f"Falha ao atualizar patrimônio: {exc}"
    finally:
        conn.close()


def excluir_patrimonio_postgresql(patrimonio_id: int) -> Tuple[bool, str]:
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM patrimonios WHERE id = %s", (patrimonio_id,))
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Patrimônio não encontrado."
        conn.commit()
        return True, "Patrimônio excluído do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir patrimônio: {exc}"
    finally:
        conn.close()


def excluir_setor_postgresql(unidade: str, setor: str) -> Tuple[bool, str]:
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE nome=%s", (str(unidade).strip(),))
            row = cur.fetchone()
            if not row:
                return False, "Unidade não encontrada."
            nome, numero, especialidade = _dividir_setor(setor)
            cur.execute(
                """UPDATE setores SET ativo=FALSE
                   WHERE unidade_id=%s AND nome=%s
                     AND numero_consultorio IS NOT DISTINCT FROM %s
                     AND especialidade IS NOT DISTINCT FROM %s""",
                (row[0], nome, numero, especialidade),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Setor não encontrado."
        conn.commit()
        return True, "Setor desativado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao desativar setor: {exc}"
    finally:
        conn.close()
