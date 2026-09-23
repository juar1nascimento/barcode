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



def salvar_patrimonios_em_lote(registros, unidade: str) -> Tuple[bool, str]:
    """Grava um lote inteiro em uma única transação PostgreSQL.

    Todas as linhas são validadas e inseridas antes do commit. Qualquer
    duplicidade ou erro faz rollback do lote inteiro, evitando gravação parcial.
    """
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado."

    itens = list(registros or [])
    if not itens:
        return False, "O lote está vazio."
    if len(itens) > 1000:
        return False, "O lote excede o limite de 1000 patrimônios por operação."

    nome_unidade = str(unidade or "").strip()
    if not nome_unidade:
        return False, "Unidade obrigatória."

    vistos = set()
    for posicao, item in enumerate(itens, start=1):
        item = item or {}
        numero = str(item.get("numero_patrimonio") or item.get("codigo_barras") or "").strip()
        tipo = str(item.get("tipo") or item.get("tipo_patrimonio") or "").strip()
        setor = re.sub(r"\s+", " ", str(item.get("setor") or "").strip())
        if not numero or tipo not in TIPOS_PATRIMONIO or not setor:
            return False, f"Registro {posicao}: dados insuficientes ou tipo inválido."
        chave = numero.casefold()
        if chave in vistos:
            return False, f"Registro {posicao}: o patrimônio {numero} está duplicado no próprio lote."
        vistos.add(chave)

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, nome_unidade)

            for item in itens:
                numero = str(item.get("numero_patrimonio") or item.get("codigo_barras") or "").strip()
                codigo = str(item.get("codigo_barras") or "").strip() or None
                tipo = str(item.get("tipo") or item.get("tipo_patrimonio") or "").strip()
                setor = re.sub(r"\s+", " ", str(item.get("setor") or "").strip())
                fabricante = str(item.get("fabricante") or "").strip() or None
                foto_bytes = item.get("foto_bytes")

                setor_id = garantir_setor(cur, unidade_id, setor)
                cur.execute(
                    """INSERT INTO patrimonios
                       (unidade_id, setor_id, tipo, numero_patrimonio,
                        codigo_barras, fabricante, data_cadastro, atualizado_em, foto)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)""",
                    (
                        unidade_id,
                        setor_id,
                        tipo,
                        numero,
                        codigo,
                        fabricante,
                        datetime.now(),
                        foto_bytes,
                    ),
                )

        conn.commit()
        return True, f"{len(itens)} patrimônio(s) gravado(s) no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, "O lote foi cancelado: um ou mais patrimônios já existem no PostgreSQL."
        return False, f"Lote cancelado e revertido: {texto}"
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


def obter_foto_patrimonio(unidade: str, setor: str, numero_patrimonio: str) -> Optional[bytes]:
    """Recupera somente a foto de um patrimônio identificado pela UI.

    A consulta é sob demanda para não carregar todas as imagens BYTEA da unidade
    junto com a tabela principal.
    """
    conn = conectar()
    if conn is None:
        return None

    try:
        nome_unidade = str(unidade or "").strip()
        numero = str(numero_patrimonio or "").strip()
        if not nome_unidade or not numero:
            return None

        nome_setor, numero_consultorio, especialidade = _dividir_setor(setor)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.foto
                   FROM patrimonios p
                   JOIN unidades u ON u.id = p.unidade_id
                   JOIN setores s ON s.id = p.setor_id
                   WHERE u.nome=%s
                     AND s.nome=%s
                     AND s.numero_consultorio IS NOT DISTINCT FROM %s
                     AND s.especialidade IS NOT DISTINCT FROM %s
                     AND p.numero_patrimonio=%s
                   LIMIT 1""",
                (nome_unidade, nome_setor, numero_consultorio, especialidade, numero),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return None
            return bytes(row[0])
    except Exception as exc:
        st.warning(f"Não foi possível recuperar a foto do patrimônio: {exc}")
        return None
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



def atualizar_patrimonio_por_identificacao(
    unidade: str,
    setor_atual: str,
    numero_atual: str,
    tipo: str,
    novo_setor: str,
    novo_numero: str,
    fabricante: str = "",
) -> Tuple[bool, str]:
    """Atualiza um patrimônio usando a identificação estável exibida pela UI."""
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."

    try:
        nome_unidade = str(unidade or "").strip()
        numero_origem = str(numero_atual or "").strip()
        numero_destino = str(novo_numero or "").strip()
        tipo_limpo = str(tipo or "").strip()

        if not nome_unidade or not numero_origem or not numero_destino:
            return False, "Unidade e números de patrimônio são obrigatórios."
        if tipo_limpo not in TIPOS_PATRIMONIO:
            return False, "Tipo de patrimônio inválido."

        nome_setor_atual, num_cons_atual, esp_atual = _dividir_setor(setor_atual)

        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id
                   FROM patrimonios p
                   JOIN unidades u ON u.id=p.unidade_id
                   JOIN setores s ON s.id=p.setor_id
                   WHERE u.nome=%s AND s.nome=%s
                     AND s.numero_consultorio IS NOT DISTINCT FROM %s
                     AND s.especialidade IS NOT DISTINCT FROM %s
                     AND p.numero_patrimonio=%s
                   FOR UPDATE""",
                (nome_unidade, nome_setor_atual, num_cons_atual, esp_atual, numero_origem),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "Patrimônio original não encontrado no PostgreSQL."

            unidade_id = garantir_unidade(cur, nome_unidade)
            setor_id = garantir_setor(cur, unidade_id, novo_setor)

            cur.execute(
                """UPDATE patrimonios
                   SET unidade_id=%s, setor_id=%s, tipo=%s, numero_patrimonio=%s,
                       fabricante=%s, atualizado_em=NOW()
                   WHERE id=%s""",
                (
                    unidade_id,
                    setor_id,
                    tipo_limpo,
                    numero_destino,
                    str(fabricante or "").strip() or None,
                    row[0],
                ),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Patrimônio não pôde ser atualizado."

        conn.commit()
        return True, "Patrimônio atualizado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
            return False, "O novo número de patrimônio já está em uso."
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


def excluir_patrimonio_por_identificacao(unidade: str, setor: str, numero_patrimonio: str) -> Tuple[bool, str]:
    """Exclui exatamente um patrimônio usando os identificadores estáveis da UI."""
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."
    try:
        nome_unidade = str(unidade or "").strip()
        numero = str(numero_patrimonio or "").strip()
        if not nome_unidade or not numero:
            return False, "Unidade e número de patrimônio são obrigatórios."

        nome_setor, numero_consultorio, especialidade = _dividir_setor(setor)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id
                   FROM patrimonios p
                   JOIN unidades u ON u.id = p.unidade_id
                   JOIN setores s ON s.id = p.setor_id
                   WHERE u.nome=%s
                     AND s.nome=%s
                     AND s.numero_consultorio IS NOT DISTINCT FROM %s
                     AND s.especialidade IS NOT DISTINCT FROM %s
                     AND p.numero_patrimonio=%s
                   FOR UPDATE""",
                (nome_unidade, nome_setor, numero_consultorio, especialidade, numero),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "Patrimônio não encontrado no PostgreSQL."

            cur.execute("DELETE FROM patrimonios WHERE id=%s", (row[0],))
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Patrimônio não pôde ser excluído do PostgreSQL."

        conn.commit()
        return True, "Patrimônio excluído do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir patrimônio: {exc}"
    finally:
        conn.close()


def excluir_setor_postgresql(unidade: str, setor: str) -> Tuple[bool, str]:
    """Exclui setor e seus patrimônios em uma única transação."""
    conn = conectar()
    if conn is None:
        return False, "PostgreSQL não disponível."
    try:
        nome_unidade = str(unidade or "").strip()
        nome_setor, numero_consultorio, especialidade = _dividir_setor(setor)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE nome=%s", (nome_unidade,))
            row = cur.fetchone()
            if not row:
                return False, "Unidade não encontrada."

            unidade_id = row[0]
            cur.execute(
                """SELECT id
                   FROM setores
                   WHERE unidade_id=%s AND nome=%s
                     AND numero_consultorio IS NOT DISTINCT FROM %s
                     AND especialidade IS NOT DISTINCT FROM %s
                   FOR UPDATE""",
                (unidade_id, nome_setor, numero_consultorio, especialidade),
            )
            setor_row = cur.fetchone()
            if not setor_row:
                conn.rollback()
                return False, "Setor não encontrado."

            setor_id = setor_row[0]
            cur.execute("DELETE FROM patrimonios WHERE setor_id=%s", (setor_id,))
            patrim_consumidos = cur.rowcount

            cur.execute("DELETE FROM setores WHERE id=%s", (setor_id,))
            if cur.rowcount != 1:
                conn.rollback()
                return False, "Setor não pôde ser excluído do PostgreSQL."

        conn.commit()
        return True, f"Setor excluído do PostgreSQL; {patrim_consumidos} patrimônio(s) removido(s)."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir setor: {exc}"
    finally:
        conn.close()
