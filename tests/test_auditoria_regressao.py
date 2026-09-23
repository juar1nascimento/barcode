import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AuditoriaRegressaoTest(unittest.TestCase):
    def test_todos_os_python_compilam(self):
        arquivos = [p for p in ROOT.rglob("*.py") if ".git" not in p.parts]
        erros = []
        for arquivo in arquivos:
            try:
                ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
            except SyntaxError as exc:
                erros.append(f"{arquivo}: {exc}")
        self.assertEqual(erros, [], "Arquivos com erro de sintaxe: " + " | ".join(erros))

    def test_setores_e_tipos_oficiais_permanecem_fechados(self):
        fonte = (ROOT / "sistema_inventario.py").read_text(encoding="utf-8")
        setores = [
            "Consultório", "Almoxarifado", "Farmacia", "Sala de Preparo",
            "Sala de Vacina", "Sala de curativo", "Gerencia", "Administração",
            "Odontologia", "Recepção", "Outro Setor",
        ]
        tipos = ["CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos"]
        for valor in setores + tipos:
            self.assertIn(f'"{valor}"', fonte)

    def test_consultorio_continua_composto_sem_mudar_schema(self):
        fonte = (ROOT / "consultorio_setor_ui.py").read_text(encoding="utf-8")
        self.assertIn("Consultório {numero_limpo} - {especialidade_limpa}", fonte)
        self.assertNotIn("nova coluna", fonte.lower())

    def test_validacoes_de_entrada_e_saida_existentes(self):
        entrada = (ROOT / "entrada_equipamentos.py").read_text(encoding="utf-8")
        saida = (ROOT / "saida_equipamentos.py").read_text(encoding="utf-8")
        self.assertIn("Selecione uma URS ou UBS válida", entrada)
        self.assertIn("Selecione uma URS ou UBS válida", saida)
        self.assertIn("Informe ou bipe o código", entrada)
        self.assertIn("Informe ou bipe o código", saida)

    def test_persistencia_tem_bloqueio_de_duplicidade(self):
        fonte = (ROOT / "Tabela_de_dados_Inventario_7_2.py").read_text(encoding="utf-8")
        self.assertIn("já está cadastrado nesta unidade", fonte)
        self.assertIn("patrimônio `", fonte)


if __name__ == "__main__":
    unittest.main()
