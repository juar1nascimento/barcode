"""Adaptador OIDC isolado para homologação do Keycloak.

Este módulo não é ativado pela aplicação atual. O login local continua sendo
a autoridade em produção até que exista um provedor OIDC real e validado.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def oidc_configurado() -> bool:
    """Retorna True somente quando a configuração [auth] mínima existe."""
    try:
        cfg = st.secrets.get("auth", {})
    except Exception:
        return False

    required = (
        "redirect_uri",
        "cookie_secret",
        "client_id",
        "client_secret",
        "server_metadata_url",
    )
    return all(str(cfg.get(item, "")).strip() for item in required)


def _claim(nome: str, padrao: Any = None) -> Any:
    """Lê claim sem assumir que st.user é dict ou objeto."""
    try:
        user = st.user
        if isinstance(user, dict):
            return user.get(nome, padrao)
        return getattr(user, nome, padrao)
    except Exception:
        return padrao


def _normalizar_roles(valor: Any) -> set[str]:
    """Normaliza roles vindas de diferentes mapeamentos OIDC."""
    if isinstance(valor, str):
        valores = [valor]
    elif isinstance(valor, (list, tuple, set)):
        valores = valor
    else:
        valores = []

    return {
        str(item).strip().lower()
        for item in valores
        if str(item).strip()
    }


def usuario_oidc() -> dict[str, Any] | None:
    """Extrai somente identidade mínima e roles explícitas da sessão OIDC."""
    if not oidc_configurado():
        return None

    if not bool(_claim("is_logged_in", False)):
        return None

    # O sub é o identificador técnico estável do IdP e é obrigatório.
    subject = str(_claim("sub", "") or "").strip()
    if not subject:
        return None

    email = str(_claim("email", "") or "").strip().lower()
    username = str(_claim("preferred_username", "") or "").strip().lower()
    name = str(_claim("name", "") or "").strip()

    if not email and not username:
        return None

    roles = _normalizar_roles(_claim("roles", []))

    # Compatibilidade com um mapper Keycloak que entregue realm_access.roles.
    realm_access = _claim("realm_access", {})
    if isinstance(realm_access, dict):
        roles.update(_normalizar_roles(realm_access.get("roles", [])))

    return {
        "sub": subject,
        "email": email,
        "preferred_username": username,
        "name": name,
        "roles": roles,
        "is_admin": "admin" in roles,
    }


def iniciar_login_oidc() -> None:
    """Inicia o fluxo OIDC gerenciado pelo Streamlit."""
    if not oidc_configurado():
        raise RuntimeError("OIDC não configurado no ambiente de homologação.")
    st.login()


def encerrar_login_oidc() -> None:
    """Encerra a sessão OIDC gerenciada pelo Streamlit."""
    st.logout()

def renderizar_login_oidc() -> bool:
    """Renderiza o portal visual original, delegando a autenticação ao Keycloak."""
    if bool(getattr(st.user, "is_logged_in", False)):
        return True

    # O HTML/CSS abaixo preserva deliberadamente a estrutura visual do
    # portal de login original. Nenhuma senha é lida ou enviada pela aplicação.
    logo = ""
    try:
        from login import _logo_uri
        logo = _logo_uri()
    except Exception:
        pass

    st.markdown('''<style>
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main,.stApp{background:#f5f7fb!important}header,footer,#MainMenu{visibility:hidden!important}
.main .block-container{max-width:940px!important;padding-top:15px!important;padding-bottom:20px!important;padding-left:14px!important;padding-right:14px!important}
.login-logo{width:196px;max-width:70vw;height:64px;display:block;margin:0 auto 60px auto;object-fit:contain;object-position:center}
div[data-testid="stForm"]{width:912px!important;max-width:912px!important;box-sizing:border-box!important;background:#fff!important;border:1px solid #e1e4e8!important;border-radius:3px!important;padding:35px 292px!important;min-height:625px!important;margin:0 auto!important;box-shadow:0 1px 3px rgba(0,0,0,.04)!important}
.login-title{text-align:center;font-size:20px;line-height:1.25;font-weight:600;color:#24292e;margin:0 0 0;white-space:nowrap}
.login-divider{width:100%;height:1px;background:#e1e4e8;margin:25px 0 34px 0;display:block}
.login-divider-after-button{width:100%;height:1px;background:#e1e4e8;margin:32px 0 0 0;display:block}
div[data-testid="stForm"] button[kind="secondaryFormSubmit"],div[data-testid="stForm"] button[kind="primaryFormSubmit"]{background:#555!important;color:#fff!important;border:none!important;border-radius:4px!important;height:42px!important;font-size:14px!important;font-weight:600!important;margin-top:15px!important}
@media(max-width:940px){.main .block-container{max-width:100%!important;padding-top:15px!important;padding-left:14px!important;padding-right:14px!important}div[data-testid="stForm"]{width:100%!important;max-width:912px!important;padding-left:31vw!important;padding-right:31vw!important}}
@media(max-width:768px){.main .block-container{padding:15px 12px 25px!important}.login-logo{width:196px;max-width:70vw;height:58px;margin-bottom:35px}div[data-testid="stForm"]{min-height:0!important;padding:28px 24px!important;width:100%!important;max-width:100%!important}.login-title{white-space:normal}}
</style>''', unsafe_allow_html=True)

    _, center, _ = st.columns([.015,1,.015])
    with center:
        if logo:
            st.markdown(f'<img src="{logo}" class="login-logo" alt="Prefeitura Municipal da Serra">', unsafe_allow_html=True)
        with st.form("glpi_login_form", clear_on_submit=False):
            st.markdown('<div class="login-title">Faça login na sua conta</div><div class="login-divider"></div>', unsafe_allow_html=True)
            st.write("**Usuário**")
            st.text_input("Usuário", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="oidc_login_user", disabled=True)
            st.write("**Senha**")
            st.text_input("Senha", type="password", label_visibility="collapsed", key="oidc_login_pass", disabled=True)
            st.write("**Origem de login**")
            st.session_state["login_domain"] = "SERRA.LOCAL"
            st.markdown(
                '<div style="background:#fff;border:1px solid #d1d5da;border-radius:4px;'
                'padding:9px 12px;color:#24292e;min-height:20px;">SERRA.LOCAL</div>',
                unsafe_allow_html=True,
            )
            if st.form_submit_button("Entrar", use_container_width=True):
                iniciar_login_oidc()
            st.markdown('<div class="login-divider-after-button"></div>', unsafe_allow_html=True)
        st.caption("A autenticação e a recuperação de senha são administradas pelo Keycloak.")
    return False
