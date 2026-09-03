import base64
import streamlit as st

# Logo da Prefeitura da Serra em SVG Nativo
LOGO_SERRA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180" width="280" height="97"><g><path d="M 15,15 L 145,15 C 145,105 130,150 80,170 C 30,150 15,105 15,15 Z" fill="#1b8e42" stroke="#146830" stroke-width="2"/><path d="M 27,27 L 133,27 C 133,98 120,138 80,155 C 40,138 27,98 27,27 Z" fill="#ffffff"/><path d="M 27,27 L 133,27 L 133,48 L 27,48 Z" fill="#1b8e42"/><text x="80" y="42" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="15" fill="#ffffff" text-anchor="middle">SERRA</text><text x="44" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1535</text><text x="116" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1822</text><text x="33" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><text x="127" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><circle cx="80" cy="72" r="16" fill="none" stroke="#000000" stroke-width="4" stroke-dasharray="6,4"/><circle cx="80" cy="72" r="11" fill="#fbd100" stroke="#000000" stroke-width="1.5"/><path d="M 74,78 L 74,68 L 82,68 L 80,64 L 86,64 L 84,68 L 86,78 Z" fill="#000000"/><rect x="42" y="93" width="76" height="10" fill="#000000"/><rect x="46" y="89" width="8" height="4" fill="#000000"/><rect x="58" y="89" width="8" height="4" fill="#000000"/><rect x="70" y="89" width="8" height="4" fill="#000000"/><rect x="82" y="89" width="8" height="4" fill="#000000"/><rect x="94" y="89" width="8" height="4" fill="#000000"/><rect x="106" y="89" width="8" height="4" fill="#000000"/><path d="M 40,135 L 120,135 C 120,120 40,120 40,135 Z" fill="#fbd100"/><line x1="80" y1="105" x2="80" y2="120" stroke="#fbd100" stroke-width="2"/><line x1="65" y1="108" x2="72" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="95" y1="108" x2="88" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="53" y1="115" x2="65" y2="124" stroke="#fbd100" stroke-width="2"/><line x1="107" y1="115" x2="95" y2="124" stroke="#fbd100" stroke-width="2"/><path d="M 33,138 Q 50,122 65,135 Q 80,118 95,138 Q 110,125 127,138 L 127,143 C 115,152 45,152 33,143 Z" fill="#2d8647" stroke="#1e5c30" stroke-width="1"/><path d="M 36,143 Q 80,158 124,143 C 110,157 50,157 36,143 Z" fill="#1b4d89"/><text x="35" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="125" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="80" y="152" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text></g><text x="195" y="62" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="normal" fill="#000000" letter-spacing="1">PREFEITURA MUNICIPAL DA</text><text x="193" y="135" font-family="Arial Black, Gadget, sans-serif" font-size="76" font-weight="900" fill="#000000" letter-spacing="-1">SERRA</text></svg>"""[cite: 16]

def renderizar_login() -> bool:
    """
    Renderiza a interface de autenticação baseada no GLPI.
    Retorna True se o usuário estiver autenticado e False caso contrário.
    """
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False[cite: 16]

    if st.session_state.autenticado:
        return True[cite: 16]

    # Codificação segura em Base64 do SVG
    b64_logo = base64.b64encode(LOGO_SERRA_SVG.encode("utf-8")).decode("utf-8")[cite: 16]
    logo_html = f'<div style="text-align: center; margin-bottom: 25px;"><img src="data:image/svg+xml;base64,{b64_logo}" width="280" /></div>'[cite: 16]

    # Estilização CSS personalizada
    st.markdown("""
        <style>
            /* Fundo global cinza claro */
            .stApp {
                background-color: #f2f4f7 !important;
            }
            
            /* Oculta topo e rodapé nativos */
            header, footer, #MainMenu {
                visibility: hidden;
            }

            /* Container do Formulário formatado como Card GLPI */
            div[data-testid="stForm"] {
                background-color: #ffffff !important;
                border: 1px solid #e1e4e8 !important;
                border-radius: 4px !important;
                padding: 35px 40px !important;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            }

            .login-title {
                text-align: center;
                font-size: 20px;
                font-weight: 600;
                color: #24292e;
                margin-bottom: 25px;
            }

            .forgot-link {
                float: right;
                font-size: 12px;
                color: #333333;
                text-decoration: none;
                margin-top: -26px;
            }

            /* Inputs e Selects */
            div[data-baseweb="input"] {
                background-color: #f4f6f8 !important;
                border: 1px solid #d1d5da !important;
                border-radius: 4px !important;
            }
            
            div[data-baseweb="select"] > div {
                background-color: #ffffff !important;
                border: 1px solid #d1d5da !important;
                border-radius: 4px !important;
            }

            /* Reduz a seta do menu suspenso de Origem do Login */
            div[data-baseweb="select"] svg {
                transform: scale(0.7) !important;
            }

            /* Reduz o ícone de olho do campo de Senha */
            div[data-baseweb="input"] button svg {
                transform: scale(0.7) !important;
            }

            /* Botão 'Entrar' */
            div[data-testid="stForm"] button {
                background-color: #555555 !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 4px !important;
                height: 42px !important;
                font-size: 14px !important;
                font-weight: 600 !important;
                margin-top: 15px !important;
            }

            div[data-testid="stForm"] button:hover {
                background-color: #333333 !important;
                color: #ffffff !important;
            }

            /* Box de alerta de erro */
            .error-box {
                background-color: #fdf2f2;
                border: 1px solid #f8b4b4;
                border-left: 4px solid #e02424;
                color: #9b1c1c;
                padding: 12px 16px;
                border-radius: 4px;
                font-size: 13px;
                margin-top: 15px;
            }
        </style>
    """, unsafe_allow_html=True)[cite: 16]

    # Centralização do Card via colunas nativas do Streamlit
    _, col_center, _ = st.columns([1, 1.8, 1])[cite: 16]

    with col_center:
        # Renderização segura da Logo
        st.markdown(logo_html, unsafe_allow_html=True)[cite: 16]

        # Form de Login
        with st.form(key="glpi_login_form", clear_on_submit=False):[cite: 16]
            st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)[cite: 16]

            st.write("**Usuário**")[cite: 16]
            usuario = st.text_input("Usuário", value="", label_visibility="collapsed", key="login_user")

            st.write("**Senha**")[cite: 16]
            st.markdown('<a href="#" class="forgot-link">Esqueceu sua senha?</a>', unsafe_allow_html=True)[cite: 16]
            senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

            st.write("**Origem de login**")[cite: 16]
            origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")[cite: 16]

            submit = st.form_submit_button("Entrar", use_container_width=True)[cite: 16]

            if submit:[cite: 16]
                if usuario.strip() != "" and senha.strip() != "":[cite: 16]
                    st.session_state.autenticado = True[cite: 16]
                    st.session_state.erro_login = False[cite: 16]
                    st.rerun()[cite: 16]
                else:
                    st.session_state.erro_login = True[cite: 16]

        # Alerta de erro
        if st.session_state.get("erro_login", False):[cite: 16]
            st.markdown("""
                <div class="error-box">
                    Uso inválido de ID de sessão
                </div>
            """, unsafe_allow_html=True)[cite: 16]

    return False[cite: 16]