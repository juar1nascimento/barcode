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


@st.cache_resource(show_spinner=False)
def _pool():
    """Cria um pool global para as conexões PostgreSQL."""
    from psycopg_pool import ConnectionPool

    sec = st.secrets["postgresql"]
    url = str(sec.get("url") or "").strip()
    if url:
        return ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=5,
            open=True,
            name="gti-sesa-postgresql",
        )

    cfg = _config()
    obrigatorios = ("host", "dbname", "user", "password")
    if any(not cfg.get(k) for k in obrigatorios):
        raise ValueError("Secret [postgresql] incompleta.")

    return ConnectionPool(
        kwargs=cfg,
        min_size=1,
        max_size=5,
        open=True,
        name="gti-sesa-postgresql",
    )


class _PoolConnection:
    """Compatibilidade: close() devolve a conexão ao pool."""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._released = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._released:
            self._released = True
            try:
                self._conn.rollback()
            finally:
                self._pool.putconn(self._conn)


def conectar() -> Optional[object]:
    """Obtém uma conexão do pool sem expor o pool ao restante da aplicação."""
    if not _conexao_configurada():
        return None
    try:
        pool = _pool()
        return _PoolConnection(pool, pool.getconn())
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
        return False, [], "PostgreSQL não configurado; o cadastro não pode ser considerado persistido na tabela principal."

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


def listar_patrimonios_unidade(unidade: str) -> Tuple[bool, list, str]:
    """Lista o estado PostgreSQL de uma unidade sem alterar dados."""
    unidade = str(unidade or "").strip()
    if not unidade:
        return False, [], "Unidade é obrigatória."
    if not _conexao_configurada():
        return True, [], "PostgreSQL não configurado."

    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT
                       s.nome,
                       s.numero_consultorio,
                       s.especialidade,
                       p.tipo,
                       p.numero_patrimonio,
                       COALESCE(p.fabricante, ''),
                       p.data_cadastro
                     FROM public.patrimonios AS p
                     JOIN public.unidades AS u ON u.id = p.unidade_id
                     JOIN public.setores AS s ON s.id = p.setor_id
                    WHERE u.nome = %s
                    ORDER BY s.id, p.id""",
                (unidade,),
            )
            registros = [
                {
                    "Setor": (
                        f"Consultório {numero} - {especialidade}"
                        if numero is not None and especialidade
                        else str(setor)
                    ),
                    "Tipo de Patrimônio": str(tipo),
                    "Nº de Patrimônio": str(numero_patrimonio),
                    "Fabricante": str(fabricante or ""),
                    "Data Cadastro": data_cadastro.isoformat() if data_cadastro else "",
                }
                for setor, numero, especialidade, tipo, numero_patrimonio, fabricante, data_cadastro
                in cur.fetchall()
            ]
        return True, registros, "PostgreSQL consultado."
    except Exception as exc:
        return False, [], f"Falha ao consultar o inventário PostgreSQL: {exc}"
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
    """Exclui patrimônios dependentes e o setor em uma única transação PostgreSQL.

    A FK patrimonios.setor_id usa ON DELETE RESTRICT, então os patrimônios
    precisam ser removidos explicitamente antes do setor. As fotos são
    removidas do banco por CASCADE a partir dos patrimônios.
    """
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
                "SELECT id FROM public.setores WHERE id = %s FOR UPDATE",
                (setor_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False, "Setor não encontrado no PostgreSQL."

            cur.execute(
                "DELETE FROM public.patrimonios "
                "WHERE setor_id = %s "
                "RETURNING id",
                (setor_id,),
            )
            patrimonios_excluidos = cur.fetchall()

            cur.execute(
                "DELETE FROM public.setores "
                "WHERE id = %s "
                "RETURNING id",
                (setor_id,),
            )
            if cur.fetchone() is None:
                raise RuntimeError("Setor não foi excluído após remover os patrimônios dependentes.")

        conn.commit()
        return True, (
            f"Setor excluído do PostgreSQL com {len(patrimonios_excluidos)} "
            "patrimônio(s) dependente(s)."
        )
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
        return False, None, "PostgreSQL não configurado; o cadastro não pode ser considerado persistido na tabela principal."

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



def registrar_entrada_patrimonio(
    numero_patrimonio: str, codigo_barras: str, tipo: str,
    unidade: str, setor: str, fabricante: str = "",
    observacao: str = "", usuario: str = "",
) -> Tuple[bool, Optional[int], str]:
    """Cadastra o patrimônio e registra a entrada na mesma transação."""
    numero = str(numero_patrimonio or "").strip() or str(codigo_barras or "").strip()
    codigo = str(codigo_barras or "").strip() or None
    tipo = str(tipo or "").strip()
    unidade = str(unidade or "").strip()
    setor = re.sub(r"\s+", " ", str(setor or "").strip())
    usuario = str(usuario or "").strip()
    fabricante = str(fabricante or "").strip() or None
    if not all((numero, tipo, unidade, setor, usuario)):
        return False, None, "Número, tipo, unidade, setor e usuário são obrigatórios."
    if tipo not in TIPOS_PATRIMONIO:
        return False, None, "Tipo de patrimônio inválido."
    conn = conectar()
    if conn is None:
        return False, None, "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            setor_id = garantir_setor(cur, unidade_id, setor)
            cur.execute(
                """INSERT INTO public.patrimonios
                   (unidade_id, setor_id, tipo, numero_patrimonio,
                    codigo_barras, fabricante, data_cadastro, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                   RETURNING id""",
                (unidade_id, setor_id, tipo, numero, codigo, fabricante),
            )
            patrimonio_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO public.movimentacoes_patrimonio
                   (patrimonio_id, tipo, unidade_destino_id, setor_destino_id,
                    motivo, observacao, usuario)
                   VALUES (%s, 'ENTRADA', %s, %s, %s, %s, %s)
                   RETURNING id""",
                (patrimonio_id, unidade_id, setor_id,
                 "Recebimento de equipamento",
                 str(observacao or "").strip() or None, usuario),
            )
            cur.fetchone()
            conn.commit()
        return True, patrimonio_id, "Entrada e patrimônio gravados no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, None, "O patrimônio " + numero + " já existe no PostgreSQL."
        return False, None, "Falha ao registrar entrada: " + texto
    finally:
        conn.close()

def listar_setores_unidade(unidade_nome: str) -> Tuple[bool, list, str]:
    """Lista setores ativos de uma unidade sem alterar dados."""
    unidade = str(unidade_nome or "").strip()
    if not unidade:
        return False, [], "Unidade não informada."
    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.nome
                   FROM public.setores AS s
                   JOIN public.unidades AS u ON u.id = s.unidade_id
                   WHERE u.nome = %s AND s.ativo = TRUE
                   ORDER BY s.nome""",
                (unidade,),
            )
            return True, [str(row[0]) for row in cur.fetchall()], "Setores consultados."
    except Exception as exc:
        return False, [], f"Falha ao consultar setores: {exc}"
    finally:
        conn.close()


def transferir_patrimonio(
    identificador: str,
    unidade_origem: str,
    unidade_destino: str,
    setor_destino: str,
    motivo: str = "Transferência para outra Unidade",
    observacao: str = "",
    usuario: str = "",
) -> Tuple[bool, Optional[int], str]:
    """Atualiza a localização e grava o histórico na mesma transação."""
    identificador = str(identificador or "").strip()
    origem = str(unidade_origem or "").strip()
    destino = str(unidade_destino or "").strip()
    setor = str(setor_destino or "").strip()
    usuario = str(usuario or "").strip()
    if not all((identificador, origem, destino, setor, usuario)):
        return False, None, "Patrimônio, origem, destino, setor de destino e usuário são obrigatórios."
    if origem == destino:
        return False, None, "A unidade de destino deve ser diferente da unidade de origem."

    conn = conectar()
    if conn is None:
        return False, None, "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id, p.unidade_id, p.setor_id, u.nome, s.nome
                   FROM public.patrimonios p
                   JOIN public.unidades u ON u.id = p.unidade_id
                   JOIN public.setores s ON s.id = p.setor_id
                   WHERE (p.numero_patrimonio = %s OR p.codigo_barras = %s)
                     AND u.nome = %s
                   FOR UPDATE""",
                (identificador, identificador, origem),
            )
            patrimonio = cur.fetchone()
            if not patrimonio:
                conn.rollback()
                return False, None, "Patrimônio não encontrado na unidade de origem."
            patrimonio_id, unidade_origem_id, setor_origem_id, _, setor_origem_nome = patrimonio

            cur.execute(
                """SELECT u.id, s.id
                   FROM public.unidades u
                   JOIN public.setores s ON s.unidade_id = u.id
                   WHERE u.nome = %s AND s.nome = %s AND s.ativo = TRUE
                   FOR SHARE""",
                (destino, setor),
            )
            destino_row = cur.fetchone()
            if not destino_row:
                conn.rollback()
                return False, None, "Setor de destino não encontrado na unidade informada."
            unidade_destino_id, setor_destino_id = destino_row

            cur.execute(
                """UPDATE public.patrimonios
                   SET unidade_id = %s, setor_id = %s, atualizado_em = NOW()
                   WHERE id = %s
                   RETURNING id""",
                (unidade_destino_id, setor_destino_id, patrimonio_id),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False, None, "Não foi possível atualizar a localização do patrimônio."

            cur.execute(
                """INSERT INTO public.movimentacoes_patrimonio
                   (patrimonio_id, tipo, unidade_origem_id, setor_origem_id,
                    unidade_destino_id, setor_destino_id, motivo, observacao, usuario)
                   VALUES (%s, 'TRANSFERENCIA', %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    int(patrimonio_id), int(unidade_origem_id), int(setor_origem_id),
                    int(unidade_destino_id), int(setor_destino_id),
                    str(motivo or "").strip() or None,
                    str(observacao or "").strip() or None,
                    usuario,
                ),
            )
            movimento_id = int(cur.fetchone()[0])
            conn.commit()
        return True, movimento_id, f"Patrimônio transferido de {origem} / {setor_origem_nome} para {destino} / {setor}."
    except Exception as exc:
        conn.rollback()
        return False, None, f"Falha na transferência do patrimônio: {exc}"
    finally:
        conn.close()



def registrar_movimentacao_patrimonio(
    identificador: str,
    tipo_movimentacao: str,
    unidade_nome: str,
    motivo: str = "",
    observacao: str = "",
    usuario: str = "",
) -> Tuple[bool, Optional[int], str]:
    """Registra um evento de movimentação sem alterar ainda a localização atual.

    A localização efetiva do patrimônio permanece em public.patrimonios até que
    o fluxo de transferência/baixa seja implementado com suas validações próprias.
    """
    tipos = {"ENTRADA", "SAIDA", "TRANSFERENCIA"}
    tipo = str(tipo_movimentacao or "").strip().upper()
    identificador = str(identificador or "").strip()
    unidade_nome = str(unidade_nome or "").strip()
    usuario = str(usuario or "").strip()
    if tipo not in tipos:
        return False, None, "Tipo de movimentação inválido."
    if not identificador or not unidade_nome or not usuario:
        return False, None, "Identificador, unidade e usuário são obrigatórios."

    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.id, p.setor_id
                       FROM public.patrimonios AS p
                       JOIN public.unidades AS u ON u.id = p.unidade_id
                       WHERE (p.numero_patrimonio = %s OR p.codigo_barras = %s)
                         AND u.nome = %s
                       LIMIT 1""",
                    (identificador, identificador, unidade_nome),
                )
                row = cur.fetchone()
                if not row:
                    return False, None, "Patrimônio não encontrado na unidade informada."

                patrimonio_id = int(row[0])
                setor_origem_id = int(row[1])
                unidade_origem_id = None
                unidade_destino_id = None
                if tipo in ("SAIDA", "TRANSFERENCIA"):
                    cur.execute(
                        "SELECT id FROM public.unidades WHERE nome = %s LIMIT 1",
                        (unidade_nome,),
                    )
                    unidade_origem_id = int(cur.fetchone()[0])
                else:
                    cur.execute(
                        "SELECT id FROM public.unidades WHERE nome = %s LIMIT 1",
                        (unidade_nome,),
                    )
                    unidade_destino_id = int(cur.fetchone()[0])

                cur.execute(
                    """INSERT INTO public.movimentacoes_patrimonio
                       (patrimonio_id, tipo, unidade_origem_id, setor_origem_id,
                        unidade_destino_id, motivo, observacao, usuario)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        patrimonio_id,
                        tipo,
                        unidade_origem_id,
                        setor_origem_id,
                        unidade_destino_id,
                        str(motivo or "").strip() or None,
                        str(observacao or "").strip() or None,
                        usuario,
                    ),
                )
                movimento_id = int(cur.fetchone()[0])
            conn.commit()
        return True, movimento_id, "Movimentação registrada no PostgreSQL."
    except Exception as exc:
        return False, None, f"Falha ao registrar movimentação: {exc}"
