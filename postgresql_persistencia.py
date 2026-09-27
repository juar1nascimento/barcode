"""Persistência PostgreSQL do GTI-SESA.

A integração é opcional: sem a Secret [postgresql], o sistema continua
operando com Google Sheets. Quando configurada, o cadastro é gravado no
PostgreSQL e, separadamente, no Google Sheets.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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


def listar_patrimonios(unidade: str = "") -> Tuple[bool, List[Dict[str, Any]], str]:
    """Lê o inventário diretamente do PostgreSQL."""
    if not _conexao_configurada():
        return False, [], "PostgreSQL não configurado."
    unidade = str(unidade or "").strip()
    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT p.id, u.nome AS unidade, s.nome AS setor_nome,
                       s.numero_consultorio, s.especialidade, p.tipo,
                       p.numero_patrimonio, COALESCE(p.codigo_barras, ''),
                       COALESCE(p.fabricante, ''), p.data_cadastro
                  FROM public.patrimonios p
                  JOIN public.unidades u ON u.id = p.unidade_id
                  JOIN public.setores s ON s.id = p.setor_id
            """
            params: List[Any] = []
            if unidade:
                sql += " WHERE u.nome = %s"
                params.append(unidade)
            sql += " ORDER BY p.id"
            cur.execute(sql, params)
            rows = cur.fetchall()
        dados: List[Dict[str, Any]] = []
        for row in rows:
            setor_nome = str(row[2] or "").strip()
            if setor_nome.casefold() == "consultório" and row[3] is not None:
                setor = f"Consultório {row[3]}"
                if row[4]:
                    setor += f" - {str(row[4]).strip()}"
            else:
                setor = setor_nome
            data_cadastro = row[9]
            if hasattr(data_cadastro, "astimezone"):
                try:
                    from zoneinfo import ZoneInfo
                    data_cadastro = data_cadastro.astimezone(
                        ZoneInfo("America/Sao_Paulo")
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    data_cadastro = str(data_cadastro)
            dados.append({
                "Setor": setor,
                "Tipo de Patrimônio": str(row[5] or ""),
                "Nº de Patrimônio": str(row[6] or ""),
                "Fabricante": str(row[8] or ""),
                "Data Cadastro": str(data_cadastro or ""),
                "_postgresql_id": int(row[0]),
            })
        return True, dados, "PostgreSQL"
    except Exception as exc:
        return False, [], f"Falha ao consultar o PostgreSQL: {exc}"
    finally:
        conn.close()


def salvar_patrimonios_em_lote(registros: List[Dict[str, str]]) -> Tuple[bool, List[int], str]:
    """Grava um lote inteiro em uma única transação PostgreSQL."""
    if not _conexao_configurada():
        return False, [], "PostgreSQL não configurado."
    registros = list(registros or [])
    if not registros:
        return False, [], "O lote está vazio."
    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."
    ids: List[int] = []
    try:
        with conn.cursor() as cur:
            for item in registros:
                numero = str(item.get("numero_patrimonio", "") or "").strip()
                codigo = str(item.get("codigo_barras", "") or "").strip() or None
                tipo = str(item.get("tipo_patrimonio", "") or "").strip()
                setor = re.sub(r"\s+", " ", str(item.get("setor", "") or "").strip())
                unidade = str(item.get("unidade", "") or "").strip()
                fabricante = str(item.get("fabricante", "") or "").strip() or None
                if not numero or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
                    raise ValueError(f"Dados inválidos para o patrimônio `{numero}`.")
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
                ids.append(int(cur.fetchone()[0]))
        conn.commit()
        return True, ids, "Lote gravado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, [], "O lote contém patrimônio ou código de barras já existente no PostgreSQL."
        return False, [], f"Falha ao gravar o lote no PostgreSQL: {texto}"
    finally:
        conn.close()


def _alvo_setor_sql(cur, unidade: str, setor: str):
    nome, numero, especialidade = _dividir_setor(setor)
    cur.execute(
        """SELECT s.id
             FROM public.setores s
             JOIN public.unidades u ON u.id = s.unidade_id
            WHERE u.nome = %s
              AND s.nome = %s
              AND s.numero_consultorio IS NOT DISTINCT FROM %s
              AND s.especialidade IS NOT DISTINCT FROM %s
            LIMIT 1""",
        (str(unidade).strip(), nome, numero, especialidade),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def excluir_patrimonio_db(numero_patrimonio: str, unidade: str, setor: str = "") -> Tuple[bool, str]:
    """Exclui um patrimônio e suas fotos do PostgreSQL/Storage."""
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado."
    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."
    try:
        from supabase_storage import remover_fotos_patrimonio
        nome_setor, numero_setor, especialidade = _dividir_setor(setor)
        with conn.cursor() as cur:
            sql = """
                SELECT p.id
                  FROM public.patrimonios p
                  JOIN public.unidades u ON u.id = p.unidade_id
                  JOIN public.setores s ON s.id = p.setor_id
                 WHERE p.numero_patrimonio = %s
                   AND u.nome = %s
            """
            params: List[Any] = [str(numero_patrimonio).strip(), str(unidade).strip()]
            if setor:
                sql += """ AND s.nome = %s
                           AND s.numero_consultorio IS NOT DISTINCT FROM %s
                           AND s.especialidade IS NOT DISTINCT FROM %s"""
                params.extend([nome_setor, numero_setor, especialidade])
            sql += " LIMIT 1"
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return False, "Patrimônio não encontrado no PostgreSQL."
            patrimonio_id = int(row[0])
            remover_fotos_patrimonio(conn, patrimonio_id)
            cur.execute("DELETE FROM public.patrimonios WHERE id = %s", (patrimonio_id,))
        conn.commit()
        return True, "Patrimônio excluído do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir patrimônio no PostgreSQL: {exc}"
    finally:
        conn.close()


def excluir_setor_db(setor: str, unidade: str) -> Tuple[bool, str]:
    """Exclui um setor e seus patrimônios do PostgreSQL/Storage."""
    if not _conexao_configurada():
        return False, "PostgreSQL não configurado."
    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."
    try:
        from supabase_storage import remover_fotos_patrimonio
        with conn.cursor() as cur:
            setor_id = _alvo_setor_sql(cur, unidade, setor)
            if setor_id is None:
                return False, "Setor não encontrado no PostgreSQL."
            cur.execute(
                "SELECT id FROM public.patrimonios WHERE setor_id = %s ORDER BY id",
                (setor_id,),
            )
            ids = [int(row[0]) for row in cur.fetchall()]
            for patrimonio_id in ids:
                remover_fotos_patrimonio(conn, patrimonio_id)
            if ids:
                cur.execute("DELETE FROM public.patrimonios WHERE setor_id = %s", (setor_id,))
            cur.execute("DELETE FROM public.setores WHERE id = %s", (setor_id,))
        conn.commit()
        return True, "Setor e patrimônios associados excluídos do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir setor no PostgreSQL: {exc}"
    finally:
        conn.close()
