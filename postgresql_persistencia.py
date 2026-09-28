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


def salvar_patrimonios_em_lote(registros) -> Tuple[bool, list, str]:
    """Grava um lote de patrimônios em uma única transação PostgreSQL."""
    registros = list(registros or [])
    if not registros:
        return False, [], "O lote está vazio."
    if not _conexao_configurada():
        return True, [None] * len(registros), "PostgreSQL não configurado."

    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."

    ids = []
    try:
        with conn.cursor() as cur:
            for item in registros:
                codigo = str(item.get("codigo_barras") or "").strip() or None
                tipo = str(item.get("tipo") or "").strip()
                setor = re.sub(r"\s+", " ", str(item.get("setor") or "").strip())
                unidade = str(item.get("unidade") or "").strip()
                fabricante = str(item.get("fabricante") or "").strip() or None
                numero = str(item.get("numero_patrimonio") or "").strip() or str(item.get("codigo_barras") or "").strip()

                if not numero or not tipo or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
                    raise ValueError("Dados insuficientes ou inválidos para o PostgreSQL.")

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
                ids.append(cur.fetchone()[0])
        conn.commit()
        return True, ids, "Lote gravado no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, [], f"Falha ao gravar o lote no PostgreSQL: {exc}"
    finally:
        conn.close()

def obter_dados_exclusao_patrimonio(numero_patrimonio: str, unidade: str) -> Tuple[bool, Optional[int], list, str]:
    """Localiza um patrimônio e seus objetos de foto sem alterar dados."""
    if not _conexao_configurada():
        return True, None, [], "PostgreSQL não configurado."

    numero = str(numero_patrimonio or "").strip()
    unidade = str(unidade or "").strip()
    if not numero or not unidade:
        return False, None, [], "Número de patrimônio e unidade são obrigatórios."

    conn = conectar()
    if conn is None:
        return False, None, [], "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id
                     FROM public.patrimonios AS p
                     JOIN public.unidades AS u ON u.id = p.unidade_id
                    WHERE p.numero_patrimonio = %s
                      AND u.nome = %s
                    LIMIT 1""",
                (numero, unidade),
            )
            row = cur.fetchone()
            if not row:
                return False, None, [], "Patrimônio não encontrado no PostgreSQL."

            patrimonio_id = int(row[0])
            cur.execute(
                """SELECT storage_bucket, storage_path
                     FROM public.patrimonio_fotos
                    WHERE patrimonio_id = %s
                    ORDER BY ordem, id""",
                (patrimonio_id,),
            )
            fotos = [(str(bucket), str(path)) for bucket, path in cur.fetchall()]
        return True, patrimonio_id, fotos, "Patrimônio localizado."
    except Exception as exc:
        return False, None, [], f"Falha ao consultar o patrimônio para exclusão: {exc}"
    finally:
        conn.close()


def excluir_patrimonio_postgresql(patrimonio_id: int) -> Tuple[bool, str]:
    """Exclui um patrimônio; as fotos em public.patrimonio_fotos sofrem CASCADE."""
    if not _conexao_configurada():
        return True, "PostgreSQL não configurado."

    try:
        patrimonio_id = int(patrimonio_id)
    except (TypeError, ValueError):
        return False, "ID de patrimônio inválido."

    if patrimonio_id <= 0:
        return False, "ID de patrimônio inválido."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.patrimonios WHERE id = %s RETURNING id",
                (patrimonio_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False, "Patrimônio não encontrado no PostgreSQL."
        conn.commit()
        return True, "Patrimônio excluído do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir o patrimônio no PostgreSQL: {exc}"
    finally:
        conn.close()


def obter_dados_exclusao_setor(setor: str, unidade: str) -> Tuple[bool, Optional[int], list, str]:
    """Localiza um setor e todos os patrimônios/fotos dependentes sem alterar dados."""
    if not _conexao_configurada():
        return True, None, [], "PostgreSQL não configurado."

    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    unidade = str(unidade or "").strip()
    if not setor or not unidade:
        return False, None, [], "Setor e unidade são obrigatórios."

    conn = conectar()
    if conn is None:
        return False, None, [], "Não foi possível conectar ao PostgreSQL."

    try:
        nome, numero, especialidade = _dividir_setor(setor)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.id
                     FROM public.setores AS s
                     JOIN public.unidades AS u ON u.id = s.unidade_id
                    WHERE u.nome = %s
                      AND s.nome = %s
                      AND s.numero_consultorio IS NOT DISTINCT FROM %s
                      AND s.especialidade IS NOT DISTINCT FROM %s
                    LIMIT 1""",
                (unidade, nome, numero, especialidade),
            )
            row = cur.fetchone()
            if not row:
                return False, None, [], "Setor não encontrado no PostgreSQL."

            setor_id = int(row[0])
            cur.execute(
                """SELECT p.id, p.numero_patrimonio, f.storage_bucket, f.storage_path
                     FROM public.patrimonios AS p
                     LEFT JOIN public.patrimonio_fotos AS f
                       ON f.patrimonio_id = p.id
                    WHERE p.setor_id = %s
                    ORDER BY p.id, f.ordem, f.id""",
                (setor_id,),
            )
            dependentes = [
                {
                    "patrimonio_id": int(pid),
                    "numero_patrimonio": str(numero_patrimonio),
                    "storage_bucket": str(bucket) if bucket is not None else None,
                    "storage_path": str(path) if path is not None else None,
                }
                for pid, numero_patrimonio, bucket, path in cur.fetchall()
            ]
        return True, setor_id, dependentes, "Setor localizado."
    except Exception as exc:
        return False, None, [], f"Falha ao consultar o setor para exclusão: {exc}"
    finally:
        conn.close()


def excluir_setor_postgresql(setor_id: int) -> Tuple[bool, str]:
    """Exclui um setor e seus patrimônios em uma única transação PostgreSQL."""
    if not _conexao_configurada():
        return True, "PostgreSQL não configurado."

    try:
        setor_id = int(setor_id)
    except (TypeError, ValueError):
        return False, "ID de setor inválido."

    if setor_id <= 0:
        return False, "ID de setor inválido."

    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM public.setores
                   WHERE id = %s
                   RETURNING id""",
                (setor_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False, "Setor não encontrado no PostgreSQL."
        conn.commit()
        return True, "Setor e patrimônios dependentes excluídos do PostgreSQL."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir o setor no PostgreSQL: {exc}"
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
