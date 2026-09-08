from sistema_inventario import opcoes_setor, opcoes_tipo_patrimonio


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
