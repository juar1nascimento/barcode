from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    encontrados = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            encontrados.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            encontrados.append(node.module)
    return encontrados


def test_servico_de_movimentacao_nao_importa_streamlit():
    imports = _imports(ROOT / "servicos" / "movimentacao.py")
    assert "streamlit" not in imports


def test_servico_de_movimentacao_nao_importa_modulos_funcionais():
    imports = _imports(ROOT / "servicos" / "movimentacao.py")
    proibidos = {
        "modulos.sistema_inventarios",
        "modulos.entrada_equipamentos",
        "modulos.saida_equipamentos",
    }
    assert proibidos.isdisjoint(imports)


def test_facades_legadas_apenas_delegam_para_modulos():
    esperados = {
        "sistema_inventario.py": "modulos.sistema_inventarios.sistema",
        "entrada_equipamentos.py": "modulos.entrada_equipamentos.entrada",
        "saida_equipamentos.py": "modulos.saida_equipamentos.saida",
    }
    for nome, modulo in esperados.items():
        texto = (ROOT / nome).read_text(encoding="utf-8")
        assert modulo in texto
        assert texto.count("\n") <= 4
