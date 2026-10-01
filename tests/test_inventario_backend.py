import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Tabela_de_dados_Inventario_7_2 as backend

TIPOS = backend.TIPOS_PATRIMONIO
COLUNAS = backend.COLUNAS_INVENTARIO

# O restante desta suíte permanece igual; o teste específico abaixo valida
# o patch temporário do selectbox contra hot-reload do Streamlit.


def _estado_vazio():
    return {"df": pd.DataFrame(columns=COLUNAS)}


# ...