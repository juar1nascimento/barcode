# Correcao final: nao alterar chaves de widgets depois de instanciadas
from pathlib import Path

path = Path('sistema_inventario.py')
text = path.read_text(encoding='utf-8')

text = text.replace(
    '        st.session_state.setdefault("del_coluna_patrimonio", None)\n\n        with st.expander(',
    '        st.session_state.setdefault("del_coluna_patrimonio", None)\n        if st.session_state.pop("reset_del_setor", False):\n            st.session_state.del_setor = None\n        if st.session_state.pop("reset_del_coluna_patrimonio", False):\n            st.session_state.del_coluna_patrimonio = None\n\n        with st.expander(',
    1,
)

text = text.replace(
    '                        st.session_state.del_setor = None\n                        st.session_state.del_setor_patrimonio = None\n                        st.session_state.del_coluna_patrimonio = None\n',
    '                        st.session_state.reset_del_setor = True\n                        st.session_state.del_setor_patrimonio = None\n                        st.session_state.reset_del_coluna_patrimonio = True\n',
    1,
)

text = text.replace(
    '                        st.session_state.del_coluna_patrimonio = None\n                        st.session_state.del_setor_patrimonio = setor_patrimonio_del\n',
    '                        st.session_state.reset_del_coluna_patrimonio = True\n                        st.session_state.del_setor_patrimonio = setor_patrimonio_del\n',
    1,
)

path.write_text(text, encoding='utf-8')
print('WIDGET_STATE_FIX_OK')
