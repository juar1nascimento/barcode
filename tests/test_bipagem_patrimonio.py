from Tabela_de_dados_Inventario_7_2 import (
    _garantir_coluna_patrimonio_texto,
    normalizar_codigo_patrimonio,
)


def test_normalizar_codigo_preserva_zeros_e_caracteres():
    assert normalizar_codigo_patrimonio("  00012345\r\n") == "00012345"
    assert normalizar_codigo_patrimonio("ABC-0012\t") == "ABC-0012"
    assert normalizar_codigo_patrimonio("9.0") == "9.0"


def test_coluna_patrimonio_eh_configurada_como_texto():
    class AbaFake:
        def __init__(self):
            self.chamada = None

        def format(self, intervalo, formato):
            self.chamada = (intervalo, formato)

    aba = AbaFake()
    assert _garantir_coluna_patrimonio_texto(aba) is True
    assert aba.chamada == ("C:C", {"numberFormat": {"type": "TEXT"}})
