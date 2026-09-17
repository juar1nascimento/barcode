"""Migração controlada do Google Sheets para PostgreSQL.

A rotina suporta simulação (dry-run) e migração efetiva.
- Não apaga nem modifica o Google Sheets.
- Registros já existentes no PostgreSQL não são duplicados.
- Se o mesmo número de patrimônio já existir com dados diferentes, o caso é
  reportado como conflito e NÃO é sobrescrito automaticamente.
"""

from datetime import datetime
from typing import Iterable

from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    LISTA_UBS_PADRAO,
    LISTA_URS_PADRAO,
)
from google_sheets_lote import carregar_dados_excel_lote
from postgresql_persistencia import conectar, garantir_unidade, garantir_setor


def _converter_data(valor: str):
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _normalizar_texto(valor) -> str:
    return " ".join(str(valor or "").strip().split())


def migrar_unidade(unidade: str, dry_run: bool = False, dados_lote=None) -> dict:
    """Audita/simula ou migra uma unidade sem sobrescrever conflitos."""
    if dados_lote is None:
        dados_lote = carregar_dados_excel_lote([unidade])
    df, origem = dados_lote.get(unidade, (None, f"Google Sheets ({unidade})"))
    resultado = {
        "unidade": unidade,
        "origem": origem,
        "lidos": 0,
        "candidatos": 0,
        "inseridos": 0,
        "ja_existentes": 0,
        "conflitos": [],
        "erros": [],
        "simulacao": dry_run,
    }

    if df is None or df.empty:
        return resultado

    resultado["lidos"] = len(df)
    conn = conectar()
    if conn is None:
        resultado["erros"].append(f"{unidade}: PostgreSQL indisponível.")
        return resultado

    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            for _, row in df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").iterrows():
                numero = _normalizar_texto(row.get("Nº de Patrimônio", ""))
                tipo = _normalizar_texto(row.get("Tipo de Patrimônio", ""))
                setor = _normalizar_texto(row.get("Setor", ""))
                fabricante = _normalizar_texto(row.get("Fabricante", "")) or None
                data_cadastro = _converter_data(row.get("Data Cadastro", ""))

                if not numero or not tipo or not setor:
                    resultado["erros"].append(
                        f"{unidade}: linha ignorada por dados obrigatórios ausentes."
                    )
                    continue

                resultado["candidatos"] += 1
                setor_id = garantir_setor(cur, unidade_id, setor)
                cur.execute(
                    """SELECT p.id, p.unidade_id, p.setor_id, p.tipo,
                              p.numero_patrimonio, p.fabricante
                         FROM patrimonios p
                        WHERE p.numero_patrimonio = %s""",
                    (numero,),
                )
                existente = cur.fetchone()
                if existente:
                    _, unidade_existente, setor_existente, tipo_existente, numero_existente, fabricante_existente = existente
                    mesmo = (
                        unidade_existente == unidade_id
                        and setor_existente == setor_id
                        and tipo_existente == tipo
                        and _normalizar_texto(numero_existente) == numero
                        and _normalizar_texto(fabricante_existente) == _normalizar_texto(fabricante)
                    )
                    if mesmo:
                        resultado["ja_existentes"] += 1
                    else:
                        resultado["conflitos"].append({
                            "unidade": unidade,
                            "numero": numero,
                            "motivo": "Número já existe no PostgreSQL com dados diferentes.",
                        })
                    continue

                if dry_run:
                    resultado["inseridos"] += 1
                    continue

                cur.execute(
                    """INSERT INTO patrimonios
                         (unidade_id, setor_id, tipo, numero_patrimonio, fabricante,
                          data_cadastro, atualizado_em)
                       VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()), NOW())""",
                    (unidade_id, setor_id, tipo, numero, fabricante, data_cadastro),
                )
                resultado["inseridos"] += 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception as exc:
        conn.rollback()
        resultado["erros"].append(f"{unidade}: falha na transação: {exc}")
    finally:
        conn.close()

    return resultado


def migrar_todas_as_unidades(
    unidades: Iterable[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Executa a simulação ou migração controlada para as unidades informadas."""
    unidades = list(unidades or (LISTA_URS_PADRAO + LISTA_UBS_PADRAO))
    dados_lote = carregar_dados_excel_lote(unidades)
    resultados = [
        migrar_unidade(u, dry_run=dry_run, dados_lote=dados_lote)
        for u in unidades
    ]
    return {
        "simulacao": dry_run,
        "unidades": len(resultados),
        "linhas_lidas": sum(r["lidos"] for r in resultados),
        "candidatos": sum(r["candidatos"] for r in resultados),
        "linhas_inseridas": sum(r["inseridos"] for r in resultados),
        "ja_existentes": sum(r["ja_existentes"] for r in resultados),
        "conflitos": sum(len(r["conflitos"]) for r in resultados),
        "erros": sum(len(r["erros"]) for r in resultados),
        "detalhes": resultados,
    }


if __name__ == "__main__":
    print("Use migrar_todas_as_unidades(dry_run=True) para simulação controlada.")
    print("A migração efetiva só deve ocorrer após a auditoria pré-migração.")
