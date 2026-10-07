"""Schema e saneamento controlado das abas do inventário no Google Sheets.

A planilha é um espelho operacional: PostgreSQL continua sendo a fonte de verdade.
Este módulo só normaliza a estrutura das abas de unidades já existentes e aplica
as mesmas opções fechadas usadas pelos menus do site.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    LISTA_ALMOXARIFADO_PADRAO,
    LISTA_UBS_PADRAO,
    LISTA_URS_PADRAO,
    SETORES_PADRAO,
    TIPOS_PATRIMONIO,
)

ID_COLUMN = "ID Patrimônio"
PHOTO_COLUMNS = [f"Foto {i:02d}" for i in range(1, 11)]
CANONICAL_COLUMNS = [*COLUNAS_INVENTARIO, ID_COLUMN, *PHOTO_COLUMNS]

UNIDADES_INVENTARIO = tuple(
    dict.fromkeys(
        [
            *LISTA_URS_PADRAO,
            *LISTA_UBS_PADRAO,
            *LISTA_ALMOXARIFADO_PADRAO,
        ]
    )
)

# Compatibilidade somente de cabeçalho. Valores de dados não são inventados.
HEADER_ALIASES = {
    "setor": "Setor",
    "tipo de patrimonio": "Tipo de Patrimônio",
    "tipo patrimonio": "Tipo de Patrimônio",
    "n de patrimonio": "Nº de Patrimônio",
    "n patrimonio": "Nº de Patrimônio",
    "numero de patrimonio": "Nº de Patrimônio",
    "numero patrimonio": "Nº de Patrimônio",
    "fabricante": "Fabricante",
    "data cadastro": "Data Cadastro",
    "data de cadastro": "Data Cadastro",
    "codigo de barras": "Código de Barras",
    "codigo barras": "Código de Barras",
    "id patrimonio": ID_COLUMN,
    "id de patrimonio": ID_COLUMN,
}

for _n in range(1, 13):
    HEADER_ALIASES[f"foto {_n}"] = f"Foto {_n:02d}"
    HEADER_ALIASES[f"foto {_n:02d}"] = f"Foto {_n:02d}"


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def canonical_header(value: Any) -> str:
    raw = str(value or "").strip()
    return HEADER_ALIASES.get(_key(raw), raw)


def _pad(row: list[Any], size: int) -> list[str]:
    values = ["" if value is None else str(value) for value in row]
    return (values + [""] * size)[:size]


def _canonicalize_values(values: list[list[Any]]) -> tuple[list[list[str]], dict]:
    if not values:
        return [CANONICAL_COLUMNS.copy()], {"changed": True, "reason": "aba_vazia", "conflicts": []}

    raw_header = [str(v or "").strip() for v in values[0]]
    mapped = [canonical_header(v) for v in raw_header]

    # Colunas desconhecidas são preservadas ao final. Nunca descartamos dados
    # automaticamente.
    unknown = []
    for name in mapped:
        if name and name not in CANONICAL_COLUMNS and name not in unknown:
            unknown.append(name)

    positions: dict[str, list[int]] = {}
    for idx, name in enumerate(mapped):
        if name in CANONICAL_COLUMNS:
            positions.setdefault(name, []).append(idx)

    conflicts = [name for name, idxs in positions.items() if len(idxs) > 1]

    target_columns = [*CANONICAL_COLUMNS, *unknown]
    rows_out = [target_columns]

    for source_row in values[1:]:
        source = _pad(source_row, len(mapped))
        target = []
        for name in CANONICAL_COLUMNS:
            idxs = positions.get(name, [])
            if not idxs:
                target.append("")
                continue
            # Quando houver duplicidade, preserva o primeiro valor e não
            # escolhe silenciosamente entre dois valores conflitantes.
            chosen = source[idxs[0]]
            if len(idxs) > 1:
                nonempty = [source[i] for i in idxs if source[i].strip()]
                if len(set(nonempty)) > 1:
                    chosen = ""
            target.append(chosen)
        for name in unknown:
            idx = mapped.index(name)
            target.append(source[idx] if idx < len(source) else "")
        rows_out.append(target)

    changed = mapped != target_columns
    return rows_out, {
        "changed": changed,
        "reason": "cabecalho_normalizado" if changed else "ok",
        "conflicts": conflicts,
        "original_header": raw_header,
        "canonical_header": target_columns,
    }


def _validation_rule(values: list[str], *, strict: bool, message: str) -> dict:
    return {
        "condition": {
            "type": "ONE_OF_LIST",
            "values": [{"userEnteredValue": value} for value in values],
        },
        "strict": strict,
        "showCustomUi": True,
        "inputMessage": message,
    }


def _structure_requests(worksheet, column_count: int) -> list[dict]:
    sheet_id = int(worksheet.id)
    end_col = max(column_count, len(CANONICAL_COLUMNS))
    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment)",
            }
        },

    ]
    return requests


def auditar_e_padronizar_abas_inventario(spreadsheet, *, aplicar: bool = True) -> dict:
    """Audita todas as abas de unidades conhecidas e, se solicitado, corrige-as.

    Abas não reconhecidas são apenas reportadas. Duplicidades de cabeçalho que
    poderiam causar perda ambígua de dados bloqueiam a correção daquela aba.
    """
    relatorio = {
        "abas_verificadas": 0,
        "abas_corrigidas": 0,
        "abas_ok": 0,
        "abas_bloqueadas": 0,
        "abas_nao_reconhecidas": [],
        "erros": [],
        "detalhes": [],
    }

    conhecidos = set(UNIDADES_INVENTARIO)
    structure_requests: list[dict] = []

    for worksheet in spreadsheet.worksheets():
        nome = str(worksheet.title).strip()
        if nome not in conhecidos:
            relatorio["abas_nao_reconhecidas"].append(nome)
            continue

        relatorio["abas_verificadas"] += 1
        try:
            values = worksheet.get_all_values(value_render_option="FORMULA")
            normalized, info = _canonicalize_values(values)
            detalhe = {
                "aba": nome,
                "linhas": max(0, len(normalized) - 1),
                "alteracao_necessaria": bool(info["changed"]),
                "conflitos": info["conflicts"],
            }

            if info["conflicts"]:
                relatorio["abas_bloqueadas"] += 1
                detalhe["status"] = "bloqueada_por_cabecalho_duplicado"
                relatorio["detalhes"].append(detalhe)
                continue

            if aplicar and info["changed"]:
                width = len(normalized[0])
                end = _column_letter(width)
                worksheet.update(
                    values=normalized,
                    range_name=f"A1:{end}{len(normalized)}",
                    value_input_option="USER_ENTERED",
                )
                relatorio["abas_corrigidas"] += 1
            elif not info["changed"]:
                relatorio["abas_ok"] += 1

            structure_requests.extend(_structure_requests(worksheet, len(normalized[0])))
            detalhe["status"] = "corrigida" if info["changed"] and aplicar else "ok"
            relatorio["detalhes"].append(detalhe)
        except Exception as exc:
            relatorio["erros"].append(f"{nome}: {str(exc)[:500]}")
            relatorio["abas_bloqueadas"] += 1

    if not relatorio["erros"] and structure_requests:
        # Uma única batch_update reduz drasticamente a quantidade de escritas,
        # mas o Google Sheets pode devolver 429 quando a janela de quota ainda
        # está saturada por execuções anteriores. Nesse caso, aguarda-se uma
        # janela crescente antes de falhar o gate; não há repetição de escrita
        # concorrente nem alteração dos dados durante o backoff.
        for tentativa, espera in enumerate((0, 20, 40, 60), start=1):
            if espera:
                time.sleep(espera)
            try:
                spreadsheet.batch_update({"requests": structure_requests})
                break
            except Exception as exc:
                erro = str(exc)
                eh_rate_limit = "429" in erro or "RATE_LIMIT_EXCEEDED" in erro or "RESOURCE_EXHAUSTED" in erro
                if eh_rate_limit and tentativa < 4:
                    continue
                relatorio["erros"].append(f"estrutura das abas: {erro[:500]}")
                relatorio["abas_bloqueadas"] += 1
                break

    if relatorio["erros"]:
        raise RuntimeError(
            "Auditoria/padronização do Google Sheets encontrou falhas: "
            + " | ".join(relatorio["erros"][:5])
        )
    return relatorio


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result
