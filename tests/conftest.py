"""Configuração compartilhada da suíte de testes.

Garante que os módulos Python localizados na raiz do repositório sejam
importáveis tanto localmente quanto no GitHub Actions.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)
