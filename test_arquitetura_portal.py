from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_tres_modulos_funcionais_estao_separados():
    esperados = [
        ROOT / "modulos" / "sistema_inventarios" / "sistema.py",
        ROOT / "modulos" / "entrada_equipamentos" / "entrada.py",
        ROOT / "modulos" / "saida_equipamentos" / "saida.py",
    ]
    assert all(path.is_file() for path in esperados)


def test_portal_importa_os_tres_modulos_reorganizados():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from modulos.sistema_inventarios import" in app
    assert "from modulos.entrada_equipamentos import" in app
    assert "from modulos.saida_equipamentos import" in app
