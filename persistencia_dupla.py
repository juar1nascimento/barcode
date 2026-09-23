"""Compatibilidade para a antiga ponte de persistência dupla.

A persistência PostgreSQL + espelho Google Sheets agora é controlada pelo
backend canônico de Tabela_de_dados_Inventario_7_2.registrar_patrimonio().
Este módulo permanece apenas para compatibilidade com o app.py antigo e não
intercepta mais o cadastro, evitando dupla inserção no PostgreSQL.
"""

_ativado = False


def ativar():
    """Mantém compatibilidade sem substituir o fluxo canônico de cadastro."""
    global _ativado
    _ativado = True


def desativar():
    """Desativa a compatibilidade; não há função original a restaurar."""
    global _ativado
    _ativado = False
