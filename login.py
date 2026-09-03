import streamlit as st

# Logo da Prefeitura da Serra em SVG Vetorial Nativo (Alta Definição / Sem Sombra ou Artefatos)
LOGO_SERRA_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180" width="280" height="97">
  <g>
    <!-- Brasão Escudo -->
    <path d="M 15,15 L 145,15 C 145,105 130,150 80,170 C 30,150 15,105 15,15 Z" fill="#1b8e42" stroke="#146830" stroke-width="2"/>
    <path d="M 27,27 L 133,27 C 133,98 120,138 80,155 C 40,138 27,98 27,27 Z" fill="#ffffff"/>
    
    <!-- Topo Verde do Brasão -->
    <path d="M 27,27 L 133,27 L 133,48 L 27,48 Z" fill="#1b8e42"/>
    <text x="80" y="42" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="15" fill="#ffffff" text-anchor="middle">SERRA</text>
    <text x="44" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1535</text>
    <text x="116" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1822</text>
    <text x="33" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text>
    <text x="127" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text>
    
    <!-- Engrenagem Interna -->
    <circle cx="80" cy="72" r="16" fill="none" stroke="#000000" stroke-width="4" stroke-dasharray="6,4"/>
    <circle cx="80" cy="72" r="11" fill="#fbd100" stroke="#000000" stroke-width="1.5"/>
    <path d="M 74,78 L 74,68 L 82,68 L 80,64 L 86,64 L 84,68 L 86,78 Z" fill="#000000"/>
    
    <!-- Muralha -->
    <rect x="42" y="93" width="76" height="10" fill="#000000"/>
    <rect x="46" y="89" width="8" height="4" fill="#000000"/>
    <rect x="58" y="89" width="8" height="4" fill="#000000"/>
    <rect x="70" y="89" width="8" height="4" fill="#000000"/>
    <rect x="82" y="89" width="8" height="4" fill="#000000"/>
    <rect x="94" y="89" width="8" height="4" fill="#000000"/>
    <rect x="106" y="89" width="8" height="4" fill="#000000"/>

    <!-- Sol e Montanhas -->
    <path d="M 40,135 L 120,135 C 120,120 40,120 40,135 Z" fill="#fbd100"/>
    <line x1="80" y1="105" x2="80" y2="120" stroke="#fbd100" stroke-width="2"/>
    <line x1="65" y1="108" x2="72" y2="121" stroke="#fbd100" stroke-width="2"/>
    <line x1="95" y1="108" x2="88" y2="121" stroke="#fbd100" stroke-width="2"/>
    <line x1="53" y1="115" x2="65" y2="124" stroke="#fbd100" stroke-width="2"/>
    <line x1="107" y1="115" x2="95" y2="124" stroke="#fbd100" stroke-width="2"/>

    <path d="M 33,138 Q 50,122 65,135 Q 80,118 95,138 Q 110,125 127,138 L 127,143 C 115,152 45,152 33,143 Z" fill="#2d8647" stroke="#1e5c30" stroke-width="1"/>
    <path d="M 36,143 Q 80,158 124,143 C 110,157 50,157 36,143 Z" fill="#1b4d89"/>

    <!-- Estrelas Inferiores -->
    <text x="35" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text>
    <text x="125" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text>
    <text x="80" y="152" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text>
  </g>

  <!-- Tipografia Oficial -->
  <text x="195" y="62" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="normal" fill="#000000" letter-spacing="1">PREFEITURA MUNICIPAL DA</text>
  <text x="193" y="135" font-family="Arial Black, Gadget, sans-serif" font-size="76" font-weight="900" fill="#000000" letter-spacing="-1">SERRA</text>
</svg>
"""

def renderizar_login() -> bool:
    """
    Renderiza a interface de autenticação baseada no GLPI.
    Retorna True se o usuário estiver autenticado e False caso contrário.
    """
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if st.session_state.autenticado:
        return True

    # Estilização CSS personalizada para replicar o layout da imagem
    st.markdown("""
        <style>
            /* Fundo global cinza claro */
            .stApp {
                background-color: #f2f4f7 !important;
            }
            
            /* Oculta componentes padrão do Streamlit */
            header, footer, #MainMenu {
                visibility: hidden;
            }

            /* Container principal de login */
            .login-wrapper {
                max-width: 620px;
                margin: 40px auto 20px auto;
                padding: 0 10px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }

            .logo-container {
                text-align: center;
                margin-bottom: 25px;
            }

            /* Card Branco */
            .login-card {
                background-color: #ffffff;
                border: 1px solid #e1e4e8;
                border-radius: 4px;
                padding: 40px 50px 35px 50px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            }

            .login-title {
                text-align: center;
                font-size: 22px;
                font-weight: 600;
                color: #24292e;
                margin-bottom: 30px;
            }

            /* Labels dos Inputs */
            .input-label {
                font-size: 13px;
                font-weight: 600;
                color: #333333;
                margin-bottom: 6px;
                display: block;
            }

            .label-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .forgot-link {
                font-size: 12px;
                color: #333333;
                text-decoration: none;
            }

            /* Ajuste de estilo para os inputs nativos do Streamlit */
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

            /* Botão 'Entrar' escuro */
            div.stButton > button {
                background-color: #555555 !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 4px !important;
                height: 42px !important;
                font-size: 14px !important;
                font-weight: 600 !important;
                margin-top: 10px !important;
            }

            div.stButton > button:hover {
                background-color: #333333 !important;
                color: #ffffff !important;
            }

            /* Box de alerta de erro na parte inferior do card */
            .error-box {
                background-color: #fdf2f2;
                border: 1px solid #f8b4b4;
                border-left: 4px solid #e02424;
                color: #9b1c1c;
                padding: 12px 16px;
                border-radius: 4px;
                font-size: 13px;
                margin-top: 25px;
            }

            /* Footer com Copyright */
            .login-footer {
                text-align: center;
                font-size: 12px;
                color: #6a737d;
                margin-top: 30px;
            }
            
            /* Ajustes para telas menores (Mobile) */
            @media (max-width: 640px) {
                .login-card {
                    padding: 25px 20px;
                }
            }
        </style>
    """, unsafe_allow_html=True)

    # Renderização da Estrutura HTML/Streamlit
    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    
    # Header: Logotipo Centrado
    st.markdown(f'<div class="logo-container">{LOGO_SERRA_SVG}</div>', unsafe_allow_html=True)

    # Card Principal
    with st.container():
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)

        # Formulário de Autenticação
        with st.form(key="glpi_login_form", clear_on_submit=False):
            st.markdown('<span class="input-label">Usuário</span>', unsafe_allow_html=True)
            usuario = st.text_input("Usuário", value="juari.nascimento", label_visibility="collapsed", key="login_user")

            st.markdown("""
                <div class="label-row">
                    <span class="input-label">Senha</span>
                    <a href="#" class="forgot-link">Esqueceu sua senha?</a>
                </div>
            """, unsafe_allow_html=True)
            senha = st.text_input("Senha", value="1234567890", type="password", label_visibility="collapsed", key="login_pass")

            st.markdown('<span class="input-label" style="margin-top: 10px;">Origem de login</span>', unsafe_allow_html=True)
            origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")

            submit = st.form_submit_button("Entrar", use_container_width=True)

            if submit:
                # Validação dos dados de acesso
                if usuario.strip() != "" and senha.strip() != "":
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.session_state.erro_login = True

        # Mensagem de validação equivalente ao alerta exibido na imagem
        if st.session_state.get("erro_login", False):
            st.markdown("""
                <div class="error-box">
                    Uso inválido de ID de sessão
                </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # Rodapé da aplicação
    st.markdown("""
        <div class="login-footer">
            GLPI Copyright (C) 2015-2025 Teclib' and contributors
        </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    return False