from pathlib import Path
import ast
import subprocess
import sys

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


def test_persistencia_nao_importa_streamlit():
    imports = _imports(ROOT / "persistencia_inventario.py")
    assert "streamlit" not in imports


def test_importar_persistencia_nao_carrega_streamlit_antecipadamente():
    codigo = "import sys; import persistencia_inventario; assert 'streamlit' not in sys.modules"
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_servico_de_movimentacao_nao_importa_streamlit():
    imports = _imports(ROOT / "servicos" / "movimentacao.py")
    assert "streamlit" not in imports


def test_importar_servico_nao_carrega_streamlit_antecipadamente():
    codigo = "import sys; import servicos.movimentacao; assert 'streamlit' not in sys.modules"
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_servico_de_movimentacao_nao_importa_modulos_funcionais():
    imports = _imports(ROOT / "servicos" / "movimentacao.py")
    proibidos = {
        "modulos.sistema_inventarios",
        "modulos.entrada_equipamentos",
        "modulos.saida_equipamentos",
        "Tabela_de_dados_Inventario_7_2",
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
