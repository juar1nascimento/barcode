import base64
import hashlib
import html
import json
import os
import re
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import streamlit as st

ADMIN_EMAIL_DEFAULT = ""
DB_FILE = "db_usuarios.json"
LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo_serra_login.jpg"
DEFAULT_ADMIN_HASH = "3166b70d4b201c3754a99631ace5a8cfa1b240a676b7a4ed0b3fc5ee0a7ae976"

def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def carregar_usuarios() -> dict:
    if not os.path.exists(DB_FILE):
        admin = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT).strip().lower()
        db = {admin: {"senha": DEFAULT_ADMIN_HASH, "aprovado": True}} if admin else {}
        salvar_usuarios(db)
        return db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def salvar_usuarios(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)

def validar_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()))

def validar_senha_alfanumerica_8(senha: str) -> tuple[bool, str]:
    if len(senha) != 8: return False, "A senha deve conter exatamente 8 caracteres."
    if not senha.isalnum(): return False, "A senha deve ser alfanumérica (apenas letras e números, sem símbolos)."
    if not (any(c.isalpha() for c in senha) and any(c.isdigit() for c in senha)): return False, "A senha deve conter ao menos uma letra e um número."
    return True, ""

def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> tuple[bool, str]:
    try:
        cfg = st.secrets.get("email", {}); host = cfg.get("smtp_server", "smtp.gmail.com"); port = int(cfg.get("smtp_port", 587)); sender = cfg.get("sender_email", ""); password = cfg.get("sender_password", "")
        if not sender or not password: return False, "Credenciais SMTP não configuradas nas Secrets."
        msg = MIMEMultipart("alternative"); msg["From"] = sender; msg["To"] = destinatario; msg["Subject"] = assunto; msg.attach(MIMEText(corpo_html, "html"))
        with smtplib.SMTP(host, port) as server: server.starttls(); server.login(sender, password); server.sendmail(sender, destinatario, msg.as_string())
        return True, "E-mail enviado com sucesso."
    except Exception as e: return False, f"Erro SMTP: {e}"

def processar_acao_via_url():
    p = st.query_params
    if "acao" not in p or "usuario" not in p: return
    acao = str(p["acao"]); user = str(p["usuario"]).strip().lower(); st.query_params.clear(); db = carregar_usuarios()
    if user not in db or acao not in {"aprovar", "recusar"}: return
    db[user]["aprovado"] = acao == "aprovar"; salvar_usuarios(db)
    corpo = f"<h3>Prefeitura Municipal da Serra</h3><p>Sua solicitação para <b>{html.escape(user)}</b> foi <b>{'ACEITA' if acao == 'aprovar' else 'RECUSADA'}</b>.</p>"
    enviar_email(user, "Atualização do cadastro - Prefeitura da Serra", corpo)
    (st.success if acao == "aprovar" else st.error)(f"Solicitação do usuário {user} foi {'APROVADA' if acao == 'aprovar' else 'RECUSADA'}.")

def _logo_uri() -> str:
    try: return "data:image/jpeg;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")
    except OSError: return ""

def renderizar_login() -> bool:
    processar_acao_via_url(); st.session_state.setdefault("autenticado", False); st.session_state.setdefault("tela_atual", "login")
    if st.session_state.autenticado: return True
    logo = _logo_uri()
    st.markdown('''<style>
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main,.stApp{background:#f5f7fb!important}header,footer,#MainMenu{visibility:hidden!important}
.main .block-container{max-width:940px!important;padding-top:15px!important;padding-bottom:20px!important;padding-left:14px!important;padding-right:14px!important}
.login-logo{width:196px;max-width:70vw;height:auto;display:block;margin:0 auto 60px auto;object-fit:contain}
div[data-testid="stForm"]{width:912px!important;max-width:912px!important;box-sizing:border-box!important;background:#fff!important;border:1px solid #e1e4e8!important;border-radius:3px!important;padding:35px 292px!important;min-height:625px!important;margin:0 auto!important;box-shadow:0 1px 3px rgba(0,0,0,.04)!important}
.login-title{text-align:center;font-size:20px;line-height:1.25;font-weight:600;color:#24292e;margin:0 0 0;white-space:nowrap}
.login-divider{width:100%;height:1px;background:#e1e4e8;margin:25px 0 34px 0;display:block}
.login-divider-after-button{width:100%;height:1px;background:#e1e4e8;margin:32px 0 0 0;display:block}
button[kind="tertiary"]{display:flex!important;justify-content:flex-end!important;width:100%!important;font-size:12px!important;color:#24292e!important;text-decoration:underline!important;margin:-10px 0 15px!important;padding:0!important;height:auto!important;background:transparent!important;border:none!important}
div[data-baseweb="input"]{background:#f4f6f8!important;border:1px solid #d1d5da!important;border-radius:4px!important}div[data-baseweb="select"]>div{background:#fff!important;border:1px solid #d1d5da!important;border-radius:4px!important}
div[data-testid="stForm"] button[kind="secondaryFormSubmit"],div[data-testid="stForm"] button[kind="primaryFormSubmit"]{background:#555!important;color:#fff!important;border:none!important;border-radius:4px!important;height:42px!important;font-size:14px!important;font-weight:600!important;margin-top:15px!important}
.error-box{background:#fff;border:1px solid #e1e4e8;border-left:4px solid #e02424;color:#374151;padding:12px 16px;border-radius:3px;font-size:13px;margin:30px 0 0;box-sizing:border-box;width:100%}
@media(max-width:940px){.main .block-container{max-width:100%!important;padding-top:15px!important;padding-left:14px!important;padding-right:14px!important}div[data-testid="stForm"]{width:100%!important;max-width:912px!important;padding-left:31vw!important;padding-right:31vw!important}}
@media(max-width:768px){.main .block-container{padding:15px 12px 25px!important}.login-logo{width:196px;max-width:70vw;margin-bottom:35px}div[data-testid="stForm"]{min-height:0!important;padding:28px 24px!important;width:100%!important;max-width:100%!important}.login-title{white-space:normal}}
</style>''', unsafe_allow_html=True)
    _, center, _ = st.columns([.015,1,.015])
    with center:
        if logo: st.markdown(f'<img src="{logo}" class="login-logo" alt="Prefeitura Municipal da Serra">', unsafe_allow_html=True)
        if st.session_state.tela_atual == "redefinicao_solicitar":
            with st.form("form_solicitar_email", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div><div class="login-divider"></div>', unsafe_allow_html=True); st.write("**Informe seu e-mail de acesso**")
                email_req=st.text_input("E-mail",placeholder="seuemail@serra.es.gov.br",label_visibility="collapsed",key="email_req")
                if st.form_submit_button("Avançar",use_container_width=True):
                    if validar_email(email_req): st.session_state.email_solicitante=email_req.strip().lower(); st.session_state.tela_atual="redefinicao_criar"; st.rerun()
                    else: st.error("Por favor, informe um e-mail com formato válido.")
            if st.button("← Voltar ao Login",use_container_width=True,key="btn_voltar_solicitar"): st.session_state.tela_atual="login"; st.rerun()
        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form("form_criar_usuario",clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div><div class="login-divider"></div>',unsafe_allow_html=True); st.write("**Login de Usuário (Obrigatório ser E-mail)**")
                novo=st.text_input("Usuário",value=st.session_state.get("email_solicitante",""),placeholder="usuario@dominio.com",label_visibility="collapsed",key="novo_user"); st.write("**Nova Senha (Exatamente 8 caracteres alfanuméricos)**")
                nova=st.text_input("Nova Senha",type="password",placeholder="Nova senha",label_visibility="collapsed",key="nova_pass"); st.write("**Confirme a Nova Senha**"); confirma=st.text_input("Confirmar Senha",type="password",placeholder="Repita a senha",label_visibility="collapsed",key="confirma_pass")
                if st.form_submit_button("Cadastrar e Solicitar Autorização",use_container_width=True):
                    user=novo.strip().lower()
                    if not validar_email(user): st.error("O nome de usuário deve ser obrigatoriamente um e-mail válido.")
                    elif nova!=confirma: st.error("A confirmação de senha não confere com a nova senha digitada.")
                    else:
                        ok,msg=validar_senha_alfanumerica_8(nova)
                        if not ok: st.error(msg)
                        else:
                            db=carregar_usuarios(); db[user]={"senha":hash_senha(nova),"aprovado":False}; salvar_usuarios(db); cfg=st.secrets.get("email",{}); admin=cfg.get("admin_email",""); base=cfg.get("app_url","http://localhost:8501").rstrip("/"); a=urllib.parse.urlencode({"acao":"aprovar","usuario":user}); r=urllib.parse.urlencode({"acao":"recusar","usuario":user}); body=f'<p>Solicitação de cadastro: <b>{html.escape(user)}</b></p><p><a href="{html.escape(base+"/?"+a,quote=True)}">Autorizar</a> | <a href="{html.escape(base+"/?"+r,quote=True)}">Recusar</a></p>'; enviar_email(admin,"Solicitação de Cadastro",body); st.success("Solicitação enviada ao administrador."); st.session_state.tela_atual="login"
            if st.button("← Cancelar",use_container_width=True,key="btn_cancelar_criar"): st.session_state.tela_atual="login"; st.rerun()
        else:
            with st.form("glpi_login_form",clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div><div class="login-divider"></div>',unsafe_allow_html=True); st.write("**Usuário**"); usuario=st.text_input("Usuário",placeholder="seuemail@serra.es.gov.br",label_visibility="collapsed",key="login_user"); st.write("**Senha**"); senha=st.text_input("Senha",type="password",label_visibility="collapsed",key="login_pass")
                if st.form_submit_button("Esqueceu sua senha?",type="tertiary"): st.session_state.tela_atual="redefinicao_solicitar"; st.rerun()
                st.write("**Origem de login**"); st.selectbox("Origem de login",["SERRA.LOCAL"],label_visibility="collapsed",key="login_domain")
                if st.form_submit_button("Entrar",use_container_width=True):
                    user=usuario.strip().lower()
                    if not user or not senha.strip(): st.session_state.erro_login_msg="Uso inválido de ID de sessão ou credenciais incorretas"
                    else:
                        db=carregar_usuarios()
                        if user not in db: st.session_state.erro_login_msg="Acesso negado: Este e-mail não está cadastrado no sistema"
                        elif not db[user].get("aprovado",False): st.session_state.erro_login_msg="Seu e-mail está cadastrado, porém ainda aguarda AUTORIZAÇÃO do administrador"
                        elif db[user].get("senha")!=hash_senha(senha): st.session_state.erro_login_msg="Uso inválido de ID de sessão ou credenciais incorretas"
                        else: st.session_state.autenticado=True; st.session_state.usuario_logado=user; st.session_state.erro_login_msg=None; st.rerun()
                st.markdown('<div class="login-divider-after-button"></div>', unsafe_allow_html=True)
            if st.session_state.get("erro_login_msg"): st.markdown(f'<div class="error-box">{html.escape(str(st.session_state.erro_login_msg))}</div>',unsafe_allow_html=True)
    return False
