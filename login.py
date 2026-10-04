from __future__ import annotations

import base64
import html
import time
from pathlib import Path

import streamlit as st

from auth_supabase import (
    get_profile,
    get_user,
    request_password_reset,
    senha_forte,
    sign_in,
    sign_out,
    update_password,
    validar_email,
    exchange_code,
)

LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo_serra_login.jpg"
SESSAO_INATIVA_SEGUNDOS = 30 * 60
LOGIN_MAX_TENTATIVAS = 5
LOGIN_BLOQUEIO_SEGUNDOS = 15 * 60


def _logo_uri() -> str:
    try:
        return "data:image/jpeg;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")
    except OSError:
        return ""


def _limpar_sessao_autenticacao() -> None:
    try:
        sign_out()
    except Exception:
        pass
    for key in (
        "autenticado",
        "usuario_logado",
        "usuario_id",
        "usuario_papel",
        "usuario_aprovado",
        "ultimo_acesso_em",
        "login_domain",
        "erro_login_msg",
    ):
        st.session_state.pop(key, None)
    st.session_state["autenticado"] = False


def _login_bloqueado() -> bool:
    agora = time.time()
    bloqueado_ate = float(st.session_state.get("login_bloqueado_ate", 0) or 0)
    if bloqueado_ate > agora:
        return True
    if bloqueado_ate:
        st.session_state.pop("login_bloqueado_ate", None)
        st.session_state["login_tentativas"] = 0
    return False


APP_URL_PRODUCAO = "https://barcode-prxfe2eu4o34ae9tpejqpc.streamlit.app"


def _url_base() -> str:
    cfg = st.secrets.get("supabase", {})
    email_cfg = st.secrets.get("email", {})
    return str(
        cfg.get("app_url")
        or email_cfg.get("app_url")
        or APP_URL_PRODUCAO
    ).rstrip("/")


def _processar_recovery() -> bool:
    code = st.query_params.get("code")
    if not code:
        return False

    if st.session_state.get("_recovery_code_processado") != str(code):
        try:
            exchange_code(str(code))
            st.session_state["_recovery_code_processado"] = str(code)
            st.session_state["tela_atual"] = "redefinir_senha"
            st.query_params.clear()
        except Exception:
            st.query_params.clear()
            st.error("O link de recuperação é inválido, expirou ou já foi utilizado.")
    return st.session_state.get("tela_atual") == "redefinir_senha"


def _renderizar_redefinicao() -> None:
    with st.form("form_redefinir_senha", clear_on_submit=False):
        st.markdown('<div class="login-title">Criar nova senha</div><div class="login-divider"></div>', unsafe_allow_html=True)
        nova = st.text_input("Nova senha", type="password", placeholder="Digite uma nova senha", label_visibility="collapsed")
        confirma = st.text_input("Confirmar nova senha", type="password", placeholder="Repita a nova senha", label_visibility="collapsed")
        if st.form_submit_button("Salvar nova senha", use_container_width=True):
            if nova != confirma:
                st.error("As senhas não conferem.")
            else:
                ok, msg = senha_forte(nova)
                if not ok:
                    st.error(msg)
                else:
                    try:
                        update_password(nova)
                        _limpar_sessao_autenticacao()
                        st.session_state["tela_atual"] = "login"
                        st.success("Senha alterada com sucesso. Faça login com a nova senha.")
                        st.rerun()
                    except Exception:
                        st.error("Não foi possível alterar a senha. Solicite um novo link de recuperação.")
    if st.button("← Voltar ao Login", use_container_width=True, key="voltar_recovery"):
        _limpar_sessao_autenticacao()
        st.session_state["tela_atual"] = "login"
        st.rerun()


def _renderizar_recuperacao() -> None:
    with st.form("form_recuperar_acesso", clear_on_submit=True):
        st.markdown('<div class="login-title">Recuperar acesso</div><div class="login-divider"></div>', unsafe_allow_html=True)
        email = st.text_input("E-mail", placeholder="seuemail@dominio.gov.br", label_visibility="collapsed")
        if st.form_submit_button("Enviar link de recuperação", use_container_width=True):
            if not validar_email(email):
                st.error("Informe um e-mail válido.")
            else:
                try:
                    request_password_reset(email.strip().lower(), _url_base())
                except Exception:
                    # Não revelar se a conta existe.
                    pass
                st.success("Se existir uma conta para este e-mail, enviaremos as instruções de recuperação.")
    if st.button("← Voltar ao Login", use_container_width=True, key="voltar_login_recovery"):
        st.session_state["tela_atual"] = "login"
        st.rerun()


def renderizar_login() -> bool:
    st.session_state.setdefault("autenticado", False)
    st.session_state.setdefault("tela_atual", "login")

    if _processar_recovery():
        pass

    if st.session_state.get("autenticado"):
        try:
            user = get_user()
            user_data = getattr(user, "user", None)
            if user_data is None:
                raise RuntimeError("Sessão inválida.")
            perfil = get_profile(str(user_data.id))
            if not perfil or not perfil.get("ativo") or not perfil.get("aprovado"):
                _limpar_sessao_autenticacao()
                st.error("Sua conta não está autorizada para acessar o sistema.")
                return False
        except Exception:
            _limpar_sessao_autenticacao()
            return False

        ultimo = float(st.session_state.get("ultimo_acesso_em", 0) or 0)
        if ultimo and time.time() - ultimo > SESSAO_INATIVA_SEGUNDOS:
            _limpar_sessao_autenticacao()
            st.warning("Sua sessão expirou por inatividade. Faça login novamente.")
        else:
            st.session_state["ultimo_acesso_em"] = time.time()
            return True

    logo = _logo_uri()
    st.markdown('''<style>
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main,.stApp{background:#f5f7fb!important}
header,footer,#MainMenu{visibility:hidden!important}
.main .block-container{max-width:940px!important;padding:15px 14px 25px!important}
.login-logo{width:196px;max-width:70vw;height:64px;display:block;margin:0 auto 50px auto;object-fit:contain}
div[data-testid="stForm"]{width:min(100%,620px)!important;box-sizing:border-box!important;background:#fff!important;border:1px solid #e1e4e8!important;border-radius:8px!important;padding:34px 42px!important;min-height:0!important;margin:0 auto!important;box-shadow:0 3px 14px rgba(0,0,0,.06)!important}
.login-title{text-align:center;font-size:20px;line-height:1.25;font-weight:600;color:#24292e}
.login-divider{width:100%;height:1px;background:#e1e4e8;margin:22px 0 30px}
div[data-baseweb="input"]{background:#f8fafc!important;border:1px solid #cbd5e1!important;border-radius:5px!important}
div[data-testid="stForm"] button{min-height:44px!important}
@media(max-width:768px){.main .block-container{padding:14px 12px 24px!important}.login-logo{height:58px;margin-bottom:30px}div[data-testid="stForm"]{padding:28px 22px!important;width:100%!important}.login-title{white-space:normal}}
</style>''', unsafe_allow_html=True)

    _, center, _ = st.columns([0.08, 0.84, 0.08])
    with center:
        if logo:
            st.markdown(f'<img src="{logo}" class="login-logo" alt="Prefeitura Municipal da Serra">', unsafe_allow_html=True)

        if st.session_state.get("tela_atual") == "recuperacao":
            _renderizar_recuperacao()
            return False

        if st.session_state.get("tela_atual") == "redefinir_senha":
            _renderizar_redefinicao()
            return False

        with st.form("glpi_login_form", clear_on_submit=False):
            st.markdown('<div class="login-title">Faça login na sua conta</div><div class="login-divider"></div>', unsafe_allow_html=True)
            usuario = st.text_input("Usuário", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user")
            senha = st.text_input("Senha", type="password", placeholder="Sua senha", label_visibility="collapsed", key="login_pass")
            st.caption("A senha é gerenciada pelo Supabase Auth e nunca é armazenada pelo aplicativo em texto aberto.")

            if st.form_submit_button("Entrar", use_container_width=True):
                if _login_bloqueado():
                    st.session_state["erro_login_msg"] = "Acesso temporariamente bloqueado. Aguarde antes de tentar novamente."
                else:
                    email = usuario.strip().lower()
                    try:
                        response = sign_in(email, senha)
                        user = getattr(response, "user", None)
                        if user is None:
                            raise RuntimeError("Credenciais inválidas.")

                        perfil = get_profile(str(user.id))
                        if not perfil or not perfil.get("ativo") or not perfil.get("aprovado"):
                            sign_out()
                            st.session_state["erro_login_msg"] = "Usuário ou senha inválidos."
                        else:
                            st.session_state["autenticado"] = True
                            st.session_state["usuario_logado"] = str(user.email or email).lower()
                            st.session_state["usuario_id"] = str(user.id)
                            st.session_state["usuario_papel"] = str(perfil.get("papel") or "usuario")
                            st.session_state["usuario_aprovado"] = True
                            st.session_state["ultimo_acesso_em"] = time.time()
                            st.session_state["login_tentativas"] = 0
                            st.session_state.pop("erro_login_msg", None)
                            st.rerun()
                    except Exception:
                        tentativas = int(st.session_state.get("login_tentativas", 0)) + 1
                        st.session_state["login_tentativas"] = tentativas
                        if tentativas >= LOGIN_MAX_TENTATIVAS:
                            st.session_state["login_bloqueado_ate"] = time.time() + LOGIN_BLOQUEIO_SEGUNDOS
                            st.session_state["login_tentativas"] = 0
                            st.session_state["erro_login_msg"] = "Acesso temporariamente bloqueado por excesso de tentativas."
                        else:
                            st.session_state["erro_login_msg"] = "Usuário ou senha inválidos."

        if st.button("Esqueci minha senha / recuperar acesso", use_container_width=True, key="abrir_recuperacao"):
            st.session_state["tela_atual"] = "recuperacao"
            st.rerun()

        if st.session_state.get("erro_login_msg"):
            st.error(html.escape(str(st.session_state["erro_login_msg"])))

    return False
