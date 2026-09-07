from pathlib import Path

path = Path("sistema_inventario.py")
text = path.read_text(encoding="utf-8")
old = 'st.session_state.setdefault("gerenciador_exclusao_aberto", False)'
new = '''# O gerenciador permanece aberto durante toda a sessão da página.
        # O st.expander não expõe evento de abertura/fechamento; manter o estado
        # verdadeiro evita que qualquer rerun causado por selectbox/botão feche
        # automaticamente o painel durante a operação de exclusão.
        st.session_state.setdefault("gerenciador_exclusao_aberto", True)
        st.session_state["gerenciador_exclusao_aberto"] = True'''
if old not in text:
    raise SystemExit("alvo não encontrado")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("GERENCIADOR_EVOLUIDO_OK_V2")
