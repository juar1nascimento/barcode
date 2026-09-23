import sistema_inventario as si


def test_selecao_de_unidade_por_categoria_e_exclusiva():
    urs = ["URS Serra Sede", "URS Serra Dourada"]
    ubs = ["UBS André Carloni", "UBS Feu Rosa"]
    almox = ["Almoxarifado Central SESA"]

    assert si._opcoes_unidade_por_categoria("URS", urs, ubs, almox) == urs
    assert si._opcoes_unidade_por_categoria("UBS", urs, ubs, almox) == ubs
    assert si._opcoes_unidade_por_categoria("Almoxarifado", urs, ubs, almox) == almox


def test_selecao_de_unidade_nao_mistura_categorias():
    urs = ["URS Serra Sede"]
    ubs = ["UBS André Carloni"]
    almox = ["Almoxarifado Central SESA"]

    for categoria, esperadas in (
        ("URS", urs),
        ("UBS", ubs),
        ("Almoxarifado", almox),
    ):
        opcoes = si._opcoes_unidade_por_categoria(categoria, urs, ubs, almox)
        assert not (set(opcoes) & (set(urs + ubs + almox) - set(esperadas)))
