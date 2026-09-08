"""Regras centralizadas para listas, normalização e ordenação do inventário."""

from __future__ import annotations

import re
from typing import Iterable, List

TIPOS_PATRIMONIO_OFICIAIS = (
    "CPU",
    "Monitores",
    "Teclado",
    "Mouse",
    "Imprenssoras",
    "Outros Dispositivos",
)

SETORES_OFICIAIS = (
    "Administração",
    "Almoxarifado",
    "Consultório",
    "Consultório 2",
    "Consultório 4 - odontologia",
    "Consultório 5 - Enfermaria",
    "Consultório 6 - Clinico",
    "Consultório 7 - odontologia",
    "Farmácia",
    "Gerência",
    "Odontologia",
    "Outro Setor",
    "Recepção",
    "Sala de Curativo",
    "Sala de Preparo",
    "Sala de Vacina",
    "Sala dos Agentes de Saúde",
    "Triagem",
)

TEXTOS_PROIBIDOS_MENU = frozenset({
    "local / setor", "local/setor", "fabricante monitor",
    "fabricante computador", "fabricante cpu", "fabricante da cpu",
    "fabricante teclado", "fabricante mouse", "fabricante impressora",
    "fabricante nobreak",
})

_NORMALIZACOES_SETOR = {
    "farmacia": "Farmácia",
    "farmácia": "Farmácia",
    "gerencia": "Gerência",
    "gerência": "Gerência",
    "sala de curativo": "Sala de Curativo",
}

_NORMALIZACOES_FABRICANTE = {
    "hp": "HP",
    "dell": "Dell",
    "lenovo": "Lenovo",
}


def _limpar(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "").strip())


def _chave(valor: object) -> str:
    return _limpar(valor).casefold()


def texto_menu_proibido(valor: object) -> bool:
    chave = _chave(valor)
    if chave in TEXTOS_PROIBIDOS_MENU:
        return True
    compacto = re.sub(r"\s*/\s*", "/", chave)
    return compacto in {"local/setor", "fabricante monitor", "fabricante computador"}


def normalizar_setor(valor: object) -> str:
    texto = _limpar(valor)
    return _NORMALIZACOES_SETOR.get(texto.casefold(), texto)


def normalizar_fabricante(valor: object) -> str:
    texto = _limpar(valor)
    return _NORMALIZACOES_FABRICANTE.get(texto.casefold(), texto)


def lista_unica_ordenada(valores: Iterable[object], normalizador=None) -> List[str]:
    resultado = {}
    for bruto in valores:
        valor = normalizador(bruto) if normalizador else _limpar(bruto)
        if not valor or texto_menu_proibido(valor):
            continue
        resultado.setdefault(valor.casefold(), valor)
    return sorted(resultado.values(), key=lambda x: x.casefold())


def setores_menu() -> List[str]:
    return lista_unica_ordenada(SETORES_OFICIAIS, normalizar_setor)


def tipos_patrimonio_menu() -> List[str]:
    return lista_unica_ordenada(TIPOS_PATRIMONIO_OFICIAIS)


def ordenar_inventario(df):
    """Ordena registros sem alterar conteúdo ou remover históricos."""
    if df is None or df.empty:
        return df
    chaves = [c for c in ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"] if c in df.columns]
    if not chaves:
        return df
    trabalho = df.copy()
    for c in chaves:
        trabalho[f"__ord_{c}"] = trabalho[c].fillna("").astype(str).str.strip().str.casefold()
    trabalho = trabalho.sort_values([f"__ord_{c}" for c in chaves], kind="stable")
    return trabalho.drop(columns=[f"__ord_{c}" for c in chaves]).reset_index(drop=True)


def normalizar_dataframe_inventario(df):
    """Normaliza apenas variações textuais conhecidas; não elimina registros."""
    if df is None:
        return df
    resultado = df.copy()
    if "Setor" in resultado.columns:
        resultado["Setor"] = resultado["Setor"].map(normalizar_setor)
    if "Fabricante" in resultado.columns:
        resultado["Fabricante"] = resultado["Fabricante"].map(normalizar_fabricante)
    return resultado
