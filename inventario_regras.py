"""Regras centralizadas para listas e normalização do inventário.

Este módulo é deliberadamente independente da interface Streamlit e do Google
Sheets. Ele prepara a próxima etapa da auditoria sem alterar o comportamento
atual do sistema até que seja integrado aos pontos de entrada.
"""

from __future__ import annotations

import re
from typing import Iterable, List


# Mantemos "Imprenssoras" nesta etapa para não quebrar dados históricos. A
# correção ortográfica para "Impressoras" deve ser feita em uma migração própria.
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
    "Farmácia",
    "Gerência",
    "Odontologia",
    "Outro Setor",
    "Recepção",
    "Sala de Curativo",
    "Sala de Preparo",
    "Sala de Vacina",
)

# Estes textos são cabeçalhos/artefatos de planilhas antigas e nunca devem
# aparecer como opções de menu.
TEXTOS_PROIBIDOS_MENU = frozenset(
    {
        "local / setor",
        "local/setor",
        "fabricante monitor",
        "fabricante computador",
        "fabricante cpu",
        "fabricante da cpu",
        "fabricante teclado",
        "fabricante mouse",
        "fabricante impressora",
        "fabricante nobreak",
    }
)


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
    """Retorna True para cabeçalhos/artefatos que não são opções válidas."""
    chave = _chave(valor)
    if chave in TEXTOS_PROIBIDOS_MENU:
        return True
    # Também bloqueia variações óbvias com espaços extras ao redor da barra.
    compacto = re.sub(r"\s*\/\s*", "/", chave)
    return compacto in {"local/setor", "fabricante monitor", "fabricante computador"}


def normalizar_setor(valor: object) -> str:
    """Padroniza grafia conhecida sem fundir setores distintos."""
    texto = _limpar(valor)
    return _NORMALIZACOES_SETOR.get(texto.casefold(), texto)


def normalizar_fabricante(valor: object) -> str:
    """Padroniza fabricantes conhecidos, preservando novos fabricantes."""
    texto = _limpar(valor)
    return _NORMALIZACOES_FABRICANTE.get(texto.casefold(), texto)


def lista_unica_ordenada(valores: Iterable[object], normalizador=None) -> List[str]:
    """Limpa, remove duplicatas sem diferenciar maiúsculas/minúsculas e ordena."""
    resultado = {}
    for bruto in valores:
        valor = normalizador(bruto) if normalizador else _limpar(bruto)
        if not valor or texto_menu_proibido(valor):
            continue
        resultado.setdefault(valor.casefold(), valor)
    return sorted(resultado.values(), key=lambda x: x.casefold())


def setores_menu() -> List[str]:
    """Lista oficial de setores, deduplicada e em ordem alfabética."""
    return lista_unica_ordenada(SETORES_OFICIAIS, normalizar_setor)


def tipos_patrimonio_menu() -> List[str]:
    """Lista oficial de patrimônios, deduplicada e em ordem alfabética."""
    return lista_unica_ordenada(TIPOS_PATRIMONIO_OFICIAIS)
