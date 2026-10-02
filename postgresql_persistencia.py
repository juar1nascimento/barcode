"""Persistência PostgreSQL do GTI-SESA.

O PostgreSQL/Supabase é a fonte operacional do inventário.
O Google Sheets permanece fora do fluxo durante a fase atual.
"""

import re
from datetime import datetime
from typing import Optional, Tuple

import streamlit as st
from psycopg import sql

TIPOS_PATRIMONIO = (
    "CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos"
)


def _conexao_configurada() -> bool:
    """Aceita Streamlit Secrets no app e variáveis de ambiente no worker CI."""
    try:
        import os
        sec = st.secrets.get("postgresql")
        if sec and sec.get("url"):
            return True
        if sec:
            obrigatorios = ("host", "dbname", "user", "password")
            if all(sec.get(k) for k in obrigatorios):
                return True
        return bool(os.getenv("DATABASE_URL"))
    except Exception:
        import os
        return bool(os.getenv("DATABASE_URL"))

def persistencia_postgresql_configurada() -> bool:
    """Indica se o PostgreSQL está configurado sem abrir uma conexão."""
    return _conexao_configurada()


def _config() -> dict:
    import os
    sec = st.secrets.get("postgresql") or {}
    return {
        "host": sec.get("host") or os.getenv("PGHOST"),
        "port": int(sec.get("port") or os.getenv("PGPORT") or 5432),
        "dbname": sec.get("dbname") or sec.get("database") or os.getenv("PGDATABASE") or "postgres",
        "user": sec.get("user") or os.getenv("PGUSER"),
        "password": sec.get("password") or os.getenv("PGPASSWORD"),
        "sslmode": sec.get("sslmode") or os.getenv("PGSSLMODE") or "require",
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


def _buscar_patrimonio_por_codigo(cur, codigo: str, for_update: bool = False):
    """Busca por número primeiro e usa código de barras como fallback.

    A ordem preserva o comportamento anterior (número de patrimônio tem
    prioridade quando o mesmo texto puder coincidir com dois registros),
    mas evita OR + ORDER BY CASE e permite que cada igualdade use sua
    restrição/índice dedicado.
    """
    sufixo_lock = sql.SQL(" FOR UPDATE") if for_update else sql.SQL("")
    consulta_numero = sql.SQL(
        """SELECT p.id,p.numero_patrimonio,p.unidade_id,p.setor_id
              FROM patrimonios p
             WHERE p.numero_patrimonio=%s
               AND COALESCE(p.ativo, TRUE)
             LIMIT 1"""
    ) + sufixo_lock

    cur.execute(consulta_numero, (codigo,))
    row = cur.fetchone()
    if row:
        return row

    consulta_barras = sql.SQL(
        """SELECT p.id,p.numero_patrimonio,p.unidade_id,p.setor_id
              FROM patrimonios p
             WHERE p.codigo_barras=%s
               AND COALESCE(p.ativo, TRUE)
             LIMIT 1"""
    ) + sufixo_lock

    cur.execute(consulta_barras, (codigo,))
    return cur.fetchone()


def _usuario_pode_movimentar(tipo: str, usuario: str) -> bool:
    """Autoriza movimentações destrutivas somente para o administrador."""
    tipo = str(tipo or "").strip().upper()
    usuario = str(usuario or "").strip().casefold()
    if tipo not in {"ENTRADA", "SAIDA", "TRANSFERENCIA"}:
        return False
    if tipo == "ENTRADA":
        return True
    try:
        admin_email = str(st.secrets.get("email", {}).get("admin_email", "")).strip().casefold()
    except Exception:
        return False
    return bool(admin_email and usuario and usuario == admin_email)


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

    # Defesa em profundidade: operações que retiram ou transferem patrimônio
    # exigem privilégio administrativo. A entrada permanece disponível ao
    # operador autenticado, pois não remove patrimônio de uma localização.
    if not _usuario_pode_movimentar(tipo, usuario):
        return False, None, "Operação não autorizada: saída e transferência exigem administrador."

    conn = conectar()
    if conn is None:
        return False, None, "Não foi possível conectar ao PostgreSQL."

    try:
        with conn.cursor() as cur:
            row = _buscar_patrimonio_por_codigo(cur, codigo, for_update=True)
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
                                  SET unidade_id=%s,setor_id=%s,ativo=TRUE,atualizado_em=NOW()
                                WHERE id=%s AND COALESCE(ativo,TRUE)""",
                            (destino_u,destino_s,patrimonio_id))
            else:
                # SAÍDA encerra a presença operacional do patrimônio, mas não
                # remove o registro: fotos e histórico permanecem preservados.
                cur.execute("""UPDATE patrimonios
                                  SET ativo=FALSE,atualizado_em=NOW()
                                WHERE id=%s AND COALESCE(ativo,TRUE)""",
                            (patrimonio_id,))
            if cur.rowcount != 1:
                raise RuntimeError("O patrimônio não pôde ser atualizado após registrar a movimentação.")
        conn.commit()
        return True, movimento_id, f"Movimentação {tipo} registrada com sucesso."
    except Exception as exc:
        conn.rollback()
        return False, None, f"Falha ao registrar movimentação: {exc}"
    finally:
        conn.close()

def buscar_patrimonio_detalhado(codigo_patrimonio: str, incluir_inativos: bool = False):
    codigo = str(codigo_patrimonio or "").strip()
    if not codigo:
        return None
    conn = conectar()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            if incluir_inativos:
                cur.execute("""SELECT p.id,p.numero_patrimonio,p.unidade_id,p.setor_id
                                 FROM patrimonios p
                                WHERE (p.numero_patrimonio=%s OR p.codigo_barras=%s)
                                ORDER BY CASE WHEN p.numero_patrimonio=%s THEN 0 ELSE 1 END,p.id
                                LIMIT 1""", (codigo,codigo,codigo))
                base = cur.fetchone()
            else:
                base = _buscar_patrimonio_por_codigo(cur, codigo)
            if not base:
                return None

            patrimonio_id = base[0]
            cur.execute("""SELECT p.id,p.numero_patrimonio,p.codigo_barras,p.tipo,p.fabricante,
                                  p.unidade_id,u.nome,p.setor_id,s.nome,s.numero_consultorio,
                                  s.especialidade,p.data_cadastro,p.atualizado_em
                             FROM patrimonios p JOIN unidades u ON u.id=p.unidade_id
                             JOIN setores s ON s.id=p.setor_id
                            WHERE p.id=%s
                              AND (%s OR COALESCE(p.ativo, TRUE))
                            LIMIT 1""", (patrimonio_id, incluir_inativos))
            r = cur.fetchone()
            if not r:
                return None
            return {"id":r[0],"numero_patrimonio":r[1],"codigo_barras":r[2],"tipo":r[3],
                    "fabricante":r[4],"unidade_id":r[5],"unidade":r[6],"setor_id":r[7],
                    "setor":r[8],"numero_consultorio":r[9],"especialidade":r[10],
                    "data_cadastro":r[11],"atualizado_em":r[12]}
    finally:
        conn.close()

def listar_historico_movimentacoes(codigo_patrimonio: str, limite: int = 100) -> list[dict]:
    patrimonio = buscar_patrimonio_detalhado(codigo_patrimonio, incluir_inativos=True)
    if not patrimonio: return []
    conn = conectar()
    if conn is None: return []
    try:
        limite=max(1,min(int(limite),500))
        with conn.cursor() as cur:
            cur.execute("""SELECT m.id,m.tipo,m.motivo,m.observacao,m.usuario,m.criado_em,
                                  uo.nome,so.nome,so.numero_consultorio,so.especialidade,
                                  ud.nome,sd.nome,sd.numero_consultorio,sd.especialidade
                             FROM movimentacoes_patrimonio m
                             LEFT JOIN unidades uo ON uo.id=m.unidade_origem_id
                             LEFT JOIN setores so ON so.id=m.setor_origem_id
                             LEFT JOIN unidades ud ON ud.id=m.unidade_destino_id
                             LEFT JOIN setores sd ON sd.id=m.setor_destino_id
                            WHERE m.patrimonio_id=%s ORDER BY m.criado_em DESC,m.id DESC LIMIT %s""",
                        (patrimonio["id"],limite))
            return [{"id":r[0],"tipo":r[1],"motivo":r[2],"observacao":r[3],"usuario":r[4],
                     "data":r[5],
                     "origem":({"unidade":r[6],"setor":r[7],"numero_consultorio":r[8],"especialidade":r[9]} if r[6] else None),
                     "destino":({"unidade":r[10],"setor":r[11],"numero_consultorio":r[12],"especialidade":r[13]} if r[10] else None)}
                    for r in cur.fetchall()]
    finally: conn.close()



def _usuario_atual_e_admin() -> bool:
    """Aplica defesa em profundidade para operações destrutivas no backend."""
    try:
        usuario = str(st.session_state.get("usuario_logado", "")).strip().casefold()
        admin = str(st.secrets.get("email", {}).get("admin_email", "")).strip().casefold()
        return bool(usuario and admin and usuario == admin)
    except Exception:
        return False


def excluir_patrimonio_por_numero(numero_patrimonio: str, unidade: str) -> tuple[bool, str]:
    """Desativa logicamente um patrimônio, preservando fotos e histórico."""
    numero = str(numero_patrimonio or "").strip()
    nome_unidade = str(unidade or "").strip()
    if not _usuario_atual_e_admin():
        return False, "Operação não autorizada: somente o administrador pode excluir patrimônios."
    if not numero or not nome_unidade:
        return False, "Patrimônio e unidade são obrigatórios."
    conn = conectar()
    if conn is None:
        return False, "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.patrimonios p
                   SET ativo = FALSE, atualizado_em = NOW()
                  FROM public.unidades u
                 WHERE p.unidade_id = u.id
                   AND p.numero_patrimonio = %s
                   AND u.nome = %s
                   AND COALESCE(p.ativo, TRUE)
                RETURNING p.id
            """, (numero, nome_unidade))
            row = cur.fetchone()
        conn.commit()
        if not row:
            return False, "Patrimônio não encontrado ou já excluído."
        return True, "Patrimônio excluído da tabela ativa; histórico e fotos foram preservados."
    except Exception as exc:
        conn.rollback()
        return False, f"Falha ao excluir patrimônio: {exc}"
    finally:
        conn.close()


def excluir_patrimonios_setor(setor: str, unidade: str) -> tuple[bool, int, str]:
    """Desativa logicamente todos os patrimônios de um setor."""
    nome_setor = str(setor or "").strip()
    nome_unidade = str(unidade or "").strip()
    if not _usuario_atual_e_admin():
        return False, 0, "Operação não autorizada: somente o administrador pode excluir setores."
    if not nome_setor or not nome_unidade:
        return False, 0, "Setor e unidade são obrigatórios."
    conn = conectar()
    if conn is None:
        return False, 0, "Não foi possível conectar ao PostgreSQL."
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.patrimonios p
                   SET ativo = FALSE, atualizado_em = NOW()
                  FROM public.unidades u, public.setores s
                 WHERE p.unidade_id = u.id
                   AND p.setor_id = s.id
                   AND s.unidade_id = u.id
                   AND u.nome = %s
                   AND s.nome = %s
                   AND COALESCE(p.ativo, TRUE)
            """, (nome_unidade, nome_setor))
            quantidade = cur.rowcount
        conn.commit()
        mensagem = ("Setor excluído da tabela ativa; histórico e fotos foram preservados."
                    if quantidade else "Nenhum patrimônio ativo encontrado no setor.")
        return quantidade > 0, quantidade, mensagem
    except Exception as exc:
        conn.rollback()
        return False, 0, f"Falha ao excluir setor: {exc}"
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
    """Grava um patrimônio no PostgreSQL em uma única transação."""
    resultados = salvar_patrimonios_em_lote([{
        "codigo_barras": codigo_barras,
        "tipo": tipo,
        "setor": setor,
        "unidade": unidade,
        "fabricante": fabricante,
        "numero_patrimonio": numero_patrimonio,
    }])
    if not resultados[0]:
        return False, None, resultados[2]
    return True, resultados[1][0], "Patrimônio gravado no PostgreSQL."


def salvar_patrimonios_em_lote(registros) -> Tuple[bool, list[int], str]:
    """Grava todo o lote em uma única transação; falha implica rollback total."""
    itens = list(registros or [])
    if not itens:
        return False, [], "O lote está vazio."
    if len(itens) > 1000:
        return False, [], "O lote excede o limite de 1000 patrimônios por operação."

    preparados = []
    vistos = set()
    for posicao, item in enumerate(itens, start=1):
        item = item or {}
        numero = str(item.get("numero_patrimonio") or item.get("codigo_barras") or "").strip()
        codigo = str(item.get("codigo_barras") or "").strip() or None
        tipo = str(item.get("tipo") or "").strip()
        setor = re.sub(r"\\s+", " ", str(item.get("setor") or "").strip())
        unidade = str(item.get("unidade") or "").strip()
        fabricante = str(item.get("fabricante") or "").strip() or None
        if not numero or not tipo or tipo not in TIPOS_PATRIMONIO or not setor or not unidade:
            return False, [], f"Registro {posicao}: dados insuficientes ou inválidos."
        chave = numero.casefold()
        if chave in vistos:
            return False, [], f"Registro {posicao}: patrimônio `{numero}` duplicado no lote."
        vistos.add(chave)
        preparados.append((numero, codigo, tipo, setor, unidade, fabricante))

    conn = conectar()
    if conn is None:
        return False, [], "Não foi possível conectar ao PostgreSQL."

    ids = []
    try:
        with conn.cursor() as cur:
            for numero, codigo, tipo, setor, unidade, fabricante in preparados:
                unidade_id = garantir_unidade(cur, unidade)
                setor_id = garantir_setor(cur, unidade_id, setor)
                cur.execute(
                    """INSERT INTO public.patrimonios
                         (unidade_id, setor_id, tipo, numero_patrimonio,
                          codigo_barras, fabricante, data_cadastro, atualizado_em)
                       VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())
                       RETURNING id""",
                    (unidade_id, setor_id, tipo, numero, codigo, fabricante),
                )
                ids.append(cur.fetchone()[0])
        conn.commit()
        return True, ids, "Lote gravado integralmente no PostgreSQL."
    except Exception as exc:
        conn.rollback()
        texto = str(exc)
        if "duplicate key" in texto.lower() or "unique" in texto.lower():
            return False, [], f"Lote cancelado: patrimônio duplicado no PostgreSQL ({texto})."
        return False, [], f"Lote cancelado e revertido: {texto}"
    finally:
        conn.close()
