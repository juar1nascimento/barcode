from sistema_inventario import opcoes_setor, opcoes_tipo_patrimonio
from modulos.sistema_inventarios.sistema import TIPOS_CONSULTORIO, montar_setor_consultorio, normalizar_especialidade_consultorio


def test_menu_setor_usa_apenas_regras_centralizadas():
    setores = opcoes_setor()
    assert setores == sorted(set(setores), key=str.casefold)
    assert "Farmacia" not in setores
    assert "Gerencia" not in setores
    assert "Sala de curativo" not in setores
    assert "Local / Setor" not in setores
    assert "Fabricante Monitor" not in setores
    assert "Farmácia" in setores
    assert "Gerência" in setores
    assert "Sala de Curativo" in setores


def test_menu_patrimonio_usa_apenas_tipos_oficiais():
    tipos = opcoes_tipo_patrimonio()
    assert tipos == sorted(set(tipos), key=str.casefold)
    assert "Fabricante CPU" not in tipos
    assert "Fabricante Computador" not in tipos
    assert "Local/Setor" not in tipos
    assert "Nobreak" not in tipos
    assert tipos == ["CPU", "Imprenssoras", "Monitores", "Mouse", "Outros Dispositivos", "Teclado"]


def test_consultorio_mantem_especialidades_de_referencia():
    assert TIPOS_CONSULTORIO == ["Psicologia", "Psiquiatria"]


def test_especialidade_consultorio_e_digitavel_e_normalizada():
    assert normalizar_especialidade_consultorio("  Psicologia   ") == "Psicologia"
    assert normalizar_especialidade_consultorio("Fonoaudiologia  infantil") == "Fonoaudiologia infantil"
    assert normalizar_especialidade_consultorio("") == ""


def test_montar_setor_consultorio():
    assert montar_setor_consultorio("3", "Psicologia") == "Consultório 3 - Psicologia"
    assert montar_setor_consultorio("7", "Psiquiatria") == "Consultório 7 - Psiquiatria"
    assert montar_setor_consultorio("12", "Fonoaudiologia infantil") == "Consultório 12 - Fonoaudiologia infantil"
    assert montar_setor_consultorio("", "Psicologia") == ""
    assert montar_setor_consultorio("3", "") == ""
