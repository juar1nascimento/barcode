"""Persistência PostgreSQL do GTI-SESA.

A integração é opcional: sem a Secret [postgresql], o sistema continua
operando com Google Sheets. Quando configurada, o cadastro é gravado no
PostgreSQL e, separadamente, no Google Sheets.
"""

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



def listar_unidades_setores() -> list[dict]:
    conn = conectar()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT u.id,u.nome,s.id,s.nome,s.numero_consultorio,s.especialidade
                             FROM unidades u JOIN setores s ON s.unidade_id=u.id
                            WHERE COALESCE(s.ativo,TRUE)
                            ORDER BY u.nome,s.nome,s.numero_consultorio,s.especialidade""")
            return [{"unidade_id":r[0],"unidade":r[1],"setor_id":r[2],
                     "setor":r[3],"numero_consultorio":r[4],"especialidade":r[5]}
                    for r in cur.fetchall()]
    finally:
        conn.close()


def formatar_localizacao(local: dict) -> str:
    setor = local["setor"]
    if local.get("numero_consultorio") is not None:
        setor += f" {local['numero_consultorio']}"
    if local.get("especialidade"):
        setor += f" - {local['especialidade']}"
    return f"{local['unidade']} — {setor}"


def registrar_movimentacao(codigo_patrimonio: str, tipo: str, usuario: str,
                           unidade_destino_id=None, setor_destino_id=None,
                           motivo: str = "", observacao: str = ""):
    tipo = str(tipo or "").strip().upper()
    codigo = str(codigo_patrimonio or "").strip()
    usuario = str(usuario or "").strip()
    if tipo not in {"ENTRADA", "SAIDA", "TRANSFERENCIA"}:
        return False, None, "Tipo de movimentação inválido."
    if not codigo or not usuario:
        return False, None, "Patrimônio e usuário são obrigatórios."

    conn = conectar()
    if conn is None:
        return False, None, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT p.id,p.numero_patrimonio,p.unidade_id,p.setor_id
                             FROM patrimonios p
                            WHERE p.numero_patrimonio=%s OR p.codigo_barras=%s
                            ORDER BY CASE WHEN p.numero_patrimonio=%s THEN 0 ELSE 1 END
                            LIMIT 1 FOR UPDATE""", (codigo,codigo,codigo))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, None, "Patrimônio não encontrado."

            patrimonio_id, numero, origem_u, origem_s = row
            destino_u = destino_s = None

            if tipo != "SAIDA":
                if not unidade_destino_id or not setor_destino_id:
                    conn.rollback()
                    return False, None, "Unidade e setor de destino são obrigatórios."
                cur.execute("""SELECT 1 FROM setores WHERE id=%s AND unidade_id=%s
                                 AND COALESCE(ativo,TRUE)""",
                            (setor_destino_id,unidade_destino_id))
                if not cur.fetchone():
                    conn.rollback()
                    return False, None, "Setor de destino não pertence à unidade."
                destino_u, destino_s = unidade_destino_id, setor_destino_id

            if tipo == "TRANSFERENCIA" and origem_u == destino_u and origem_s == destino_s:
                conn.rollback()
                return False, None, "O patrimônio já está na localização de destino."

            cur.execute("""INSERT INTO movimentacoes_patrimonio
                           (patrimonio_id,tipo,unidade_origem_id,setor_origem_id,
                            unidade_destino_id,setor_destino_id,motivo,observacao,usuario)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (patrimonio_id,tipo,origem_u,origem_s,destino_u,destino_s,
                         str(motivo or "").strip() or None,
                         str(observacao or "").strip() or None,usuario))
            movimento_id = cur.fetchone()[0]

            if tipo != "SAIDA":
                cur.execute("""UPDATE patrimonios
                                  SET unidade_id=%s,setor_id=%s,atualizado_em=NOW()
                                WHERE id=%s""", (destino_u,destino_s,patrimonio_id))
            else:
                cur.execute("UPDATE patrimonios SET atualizado_em=NOW() WHERE id=%s",
                            (patrimonio_id,))
        conn.commit()
        return True, movimento_id, f"Movimentação {tipo} registrada com sucesso."
    except Exception as exc:
        conn.rollback()
        return False, None, f"Falha ao registrar movimentação: {exc}"
    finally:
        conn.close()

def salvar_patrimonio(
    codigo_barras: str,
    tipo: str,
    setor: str,
    unidade: str,
    fabricante: str = "",
    numero_patrimonio: str = "",
) -> Tuple[bool, Optional[int], str]:
    """Grava um patrimônio no PostgreSQL e retorna (sucesso, id, mensagem).

    A transação é atômica. Duplicidades são tratadas pelo banco e não geram
    segunda linha. Esta função não grava no Google Sheets; o chamador faz o
    espelhamento separadamente para manter as duas persistências independentes.
    """
    if not _conexao_configurada():
        return True, None, "PostgreSQL não configurado; persistência principal ainda não ativada."

    numero = str(numero_patrimonio or "").strip() or str(codigo_barras or "").strip()
    codigo = str(codigo_barras or "").strip() or None
    tipo = str(tipo or "").strip()
    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    unidade = str(unidade or "").strip()
    fabricante = str(fabricante or "").strip() or None

    if not numero or not tipo or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
        return False, None, "Dados insuficientes ou inválidos para o PostgreSQL."

    conn = conectar()
    if conn is None:
        return False, None, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            setor_id = garantir_setor(cur, unidade_id, setor)
            cur.execute(
                """INSERT INTO patrimonios
                     (unidade_id, setor_id, tipo, numero_patrimonio,
                      codigo_barras, fabricante, data_cadastro, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                   RETURNING id""",
                (unidade_id, setor_id, tipo, numero, codigo, fabricante, datetime.now()),
            )
            patrimonio_id = cur.fetchone()[0]
        conn.commit()
        return True, patrimonio_id, "Patrimônio gravado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, None, f"O patrimônio `{numero}` já existe no PostgreSQL."
        return False, None, f"Falha ao gravar no PostgreSQL: {texto}"
    finally:
        conn.close()
