import base64
import hashlib
import html
import hmac
import json
import os
import re
import secrets
import smtplib
import time
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import psycopg
import streamlit as st

ADMIN_EMAIL_DEFAULT = ""
DB_FILE = "db_usuarios.json"
LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo_serra_login.jpg"
PBKDF2_ITERATIONS = 310_000
APPROVAL_TOKEN_TTL_SECONDS = 15 * 60
RESET_TOKEN_TTL_SECONDS = 15 * 60
LOGIN_MAX_TENTATIVAS = 5
LOGIN_BLOQUEIO_SEGUNDOS = 15 * 60
SESSAO_INATIVA_SEGUNDOS = 30 * 60
AUTH_DB_CONNECT_TIMEOUT_SECONDS = 5


def _auth_database_url() -> str:
    """Obtém a conexão persistente do cadastro sem usar Supabase Auth."""
    try:
        valor = st.secrets.get("GTI_DATABASE_URL", "")
        if valor:
            return str(valor).strip()
    except Exception:
        pass
    return str(os.environ.get("GTI_DATABASE_URL", "")).strip()


def _carregar_usuarios_local() -> dict:
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _salvar_usuarios_local(db: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except OSError:
        # O cache local é apenas uma camada de contingência; a persistência
        # principal fica no PostgreSQL.
        pass


def _carregar_usuarios_persistentes() -> dict | None:
    url = _auth_database_url()
    if not url:
        return None
    try:
        with psycopg.connect(url, connect_timeout=AUTH_DB_CONNECT_TIMEOUT_SECONDS) as conn:
            rows = conn.execute(
                """
                select usuario, senha, aprovado, approval_token_digests
                from public.gti_auth_usuarios
                order by usuario
                """
            ).fetchall()
        return {
            str(usuario).strip().lower(): {
                "senha": str(senha or ""),
                "aprovado": bool(aprovado),
                "approval_token_digests": digests if isinstance(digests, dict) else {},
            }
            for usuario, senha, aprovado, digests in rows
        }
    except Exception:
        return None


def _salvar_usuarios_persistentes(db: dict) -> bool:
    url = _auth_database_url()
    if not url:
        return False
    try:
        with psycopg.connect(url, connect_timeout=AUTH_DB_CONNECT_TIMEOUT_SECONDS) as conn:
            with conn.cursor() as cur:
                for usuario, dados in db.items():
                    cur.execute(
                        """
                        insert into public.gti_auth_usuarios
                            (usuario, senha, aprovado, approval_token_digests, updated_at)
                        values (%s, %s, %s, %s::jsonb, now())
                        on conflict (usuario) do update set
                            senha = excluded.senha,
                            aprovado = excluded.aprovado,
                            approval_token_digests = excluded.approval_token_digests,
                            updated_at = now()
                        """,
                        (
                            str(usuario).strip().lower(),
                            str(dados.get("senha", "")),
                            bool(dados.get("aprovado", False)),
                            json.dumps(dados.get("approval_token_digests", {})),
                        ),
                    )
            conn.commit()
        return True
    except Exception:
        return False


def hash_senha(senha: str) -> str:
    """Gera hash de senha moderno, com salt aleatório e PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verificar_senha(senha: str, armazenada: str) -> tuple[bool, bool]:
    """Retorna (válida, precisa_migrar).

    Hashes SHA-256 legados continuam aceitos temporariamente para permitir
    migração transparente no primeiro login bem-sucedido.
    """
    valor = str(armazenada or "")
    if valor.startswith("pbkdf2_sha256$"):
        try:
            _, iteracoes, salt_hex, digest_hex = valor.split("$", 3)
            iteracoes = int(iteracoes)
            salt = bytes.fromhex(salt_hex)
            esperado = bytes.fromhex(digest_hex)
            atual = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)
            return hmac.compare_digest(atual, esperado), False
        except (ValueError, TypeError):
            return False, False
    if re.fullmatch(r"[0-9a-f]{64}", valor):
        atual = hashlib.sha256(senha.encode("utf-8")).hexdigest()
        return hmac.compare_digest(atual, valor), True
    return False, False


def carregar_usuarios() -> dict:
    """Carrega contas de forma persistente, mantendo o login fora do Supabase Auth."""
    persistente = _carregar_usuarios_persistentes()
    if persistente is not None:
        if persistente:
            _salvar_usuarios_local(persistente)
            return persistente

        # Primeira execução após a evolução: migra o cadastro local existente
        # antes de criar qualquer conta nova.
        local = _carregar_usuarios_local()
        if local:
            if _salvar_usuarios_persistentes(local):
                return local

        # Bootstrap seguro do administrador a partir das Secrets já existentes.
        admin = str(st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)).strip().lower()
        admin_hash = str(st.secrets.get("email", {}).get("admin_password_hash", "")).strip()
        db = {admin: {"senha": admin_hash, "aprovado": True}} if admin and admin_hash else {}
        if db:
            _salvar_usuarios_persistentes(db)
            _salvar_usuarios_local(db)
        return db

    # Contingência: mantém o comportamento anterior se o PostgreSQL estiver
    # temporariamente indisponível, sem apagar ou substituir credenciais.
    local = _carregar_usuarios_local()
    if local:
        return local

    admin = str(st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)).strip().lower()
    admin_hash = str(st.secrets.get("email", {}).get("admin_password_hash", "")).strip()
    db = {admin: {"senha": admin_hash, "aprovado": True}} if admin and admin_hash else {}
    _salvar_usuarios_local(db)
    return db


def salvar_usuarios(db: dict):
    _salvar_usuarios_local(db)
    _salvar_usuarios_persistentes(db)


def registrar_novo_usuario(db: dict, usuario: str, senha: str) -> bool:
    """Cria apenas contas inexistentes; nunca sobrescreve credenciais existentes."""
    usuario = str(usuario or "").strip().lower()
    if not usuario or usuario in db:
        return False
    db[usuario] = {"senha": hash_senha(senha), "aprovado": False}
    return True


def validar_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()))


def validar_senha_alfanumerica_8(senha: str) -> tuple[bool, str]:
    if len(senha) != 8:
        return False, "A senha deve conter exatamente 8 caracteres."
    if not senha.isalnum():
        return False, "A senha deve ser alfanumérica (apenas letras e números, sem símbolos)."
    if not (any(c.isalpha() for c in senha) and any(c.isdigit() for c in senha)):
        return False, "A senha deve conter ao menos uma letra e um número."
    return True, ""


def _segredo_aprovacao() -> str:
    return str(st.secrets.get("email", {}).get("approval_secret", "")).strip()


def _email_config_status() -> tuple[bool, str]:
    """Valida a configuração mínima do mecanismo de recuperação."""
    try:
        cfg = st.secrets.get("email", {})
        admin = str(cfg.get("admin_email", "")).strip().lower()
        sender = str(cfg.get("sender_email", "")).strip().lower()
        password = str(cfg.get("sender_password", "")).strip()
        secret = str(cfg.get("approval_secret", "")).strip()
        if not validar_email(admin):
            return False, "admin_email não está configurado corretamente."
        if not validar_email(sender):
            return False, "sender_email não está configurado corretamente."
        if not password:
            return False, "sender_password não está configurado."
        if not secret:
            return False, "approval_secret não está configurado."
        return True, ""
    except Exception:
        return False, "Configuração [email] indisponível nas Secrets."


def _criar_token_aprovacao(acao: str, usuario: str) -> str:
    segredo = _segredo_aprovacao()
    if not segredo:
        raise RuntimeError("approval_secret não configurado nas Secrets.")
    expira = int(time.time()) + APPROVAL_TOKEN_TTL_SECONDS
    payload = f"{acao}|{usuario.strip().lower()}|{expira}"
    assinatura = hmac.new(segredo.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.token_urlsafe(8) + "." + urllib.parse.quote(payload, safe="") + "." + assinatura


def _digest_token_aprovacao(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _validar_token_aprovacao(token: str) -> tuple[str, str] | None:
    segredo = _segredo_aprovacao()
    try:
        token = str(token).strip()

        # O payload contém o e-mail do usuário e pode conter pontos.
        # Por isso, o token deve ser separado apenas no primeiro e no último ponto.
        nonce, restante = token.split(".", 1)
        payload_encoded, assinatura = restante.rsplit(".", 1)

        if not nonce or not payload_encoded or not assinatura or not segredo:
            return None

        payload = urllib.parse.unquote(payload_encoded)
        esperado = hmac.new(
            segredo.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(assinatura, esperado):
            return None

        partes = payload.split("|", 2)
        if len(partes) != 3:
            return None

        acao, usuario, expira = partes
        if acao not in {"aprovar", "recusar", "redefinir", "redefinir_usuario"}:
            return None

        try:
            expira = int(expira)
        except (ValueError, TypeError):
            return None

        if int(time.time()) > expira:
            return None

        return acao, usuario.strip().lower()
    except (ValueError, TypeError):
        return None


def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> tuple[bool, str]:
    try:
        cfg = st.secrets.get("email", {})
        host = str(cfg.get("smtp_server", "smtp.gmail.com")).strip()
        port = int(cfg.get("smtp_port", 587))
        sender = str(cfg.get("sender_email", "")).strip()
        password = str(cfg.get("sender_password", "")).strip()
        if not sender or not password:
            return False, "Credenciais SMTP não configuradas nas Secrets."
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo_html, "html"))
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, [destinatario], msg.as_string())
        return True, "E-mail enviado com sucesso."
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        return False, f"Falha SMTP: {type(exc).__name__}."


def processar_acao_via_url():
    token = st.query_params.get("token")
    if not token:
        return

    dados = _validar_token_aprovacao(str(token))

    if not dados:
        st.query_params.clear()
        st.error("Link de autorização inválido ou expirado.")
        return

    st.query_params.clear()

    acao, user = dados
    db = carregar_usuarios()
    if user not in db:
        st.error("Usuário da solicitação não encontrado.")
        return

    # Tokens de aprovação são de uso único. O HMAC garante autenticidade,
    # enquanto o digest persistido impede replay dentro do TTL de 15 minutos.
    token_digest = _digest_token_aprovacao(str(token))
    digests = db[user].get("approval_token_digests", {})
    esperado = str(digests.get(acao, ""))
    if not esperado or not hmac.compare_digest(token_digest, esperado):
        st.error("Link de autorização já utilizado ou inválido.")
        return

    if acao == "redefinir":
        # Este token pertence ao ADMINISTRADOR. Somente após a aprovação
        # explícita o sistema gera um segundo token, destinado ao usuário.
        db[user].setdefault("approval_token_digests", {}).pop("redefinir", None)
        try:
            token_usuario = _criar_token_aprovacao("redefinir_usuario", user)
        except RuntimeError:
            st.error("Não foi possível gerar o link de redefinição. Verifique approval_secret nas Secrets.")
            return

        db[user].setdefault("approval_token_digests", {})["redefinir_usuario"] = _digest_token_aprovacao(token_usuario)
        salvar_usuarios(db)

        cfg = st.secrets.get("email", {})
        base = str(cfg.get("app_url", "http://localhost:8501")).rstrip("/")
        link_usuario = base + "/?" + urllib.parse.urlencode({"token": token_usuario})
        corpo = (
            "<h3>Prefeitura Municipal da Serra</h3>"
            f"<p>A recuperação de acesso para <b>{html.escape(user)}</b> foi autorizada pelo administrador.</p>"
            f'<p><a href="{html.escape(link_usuario, quote=True)}">Criar nova senha</a></p>'
            "<p>Este link expira em 15 minutos e pode ser usado uma única vez.</p>"
        )
        enviado, mensagem = enviar_email(user, "Recuperação de acesso autorizada - Prefeitura da Serra", corpo)
        if enviado:
            st.success(f"Recuperação de acesso de {user} autorizada. O link de redefinição foi enviado ao usuário.")
        else:
            st.error(
                "A autorização foi registrada, mas o e-mail ao usuário não pôde ser enviado. "
                + mensagem
            )
        return

    if acao == "redefinir_usuario":
        db[user].setdefault("approval_token_digests", {}).pop("redefinir_usuario", None)
        salvar_usuarios(db)
        st.session_state.email_solicitante = user
        st.session_state.tela_atual = "redefinicao_criar"
        st.session_state.reset_autorizado = True
        st.success("Solicitação autorizada. Defina sua nova senha.")
        return

    db[user]["aprovado"] = acao == "aprovar"
    db[user].pop("approval_token_digests", None)
    salvar_usuarios(db)
    corpo = f"<h3>Prefeitura Municipal da Serra</h3><p>Sua solicitação para <b>{html.escape(user)}</b> foi <b>{'ACEITA' if acao == 'aprovar' else 'RECUSADA'}</b>.</p>"
    enviar_email(user, "Atualização do cadastro - Prefeitura da Serra", corpo)
    (st.success if acao == "aprovar" else st.error)(f"Solicitação do usuário {user} foi {'APROVADA' if acao == 'aprovar' else 'RECUSADA'}.")


def _logo_uri() -> str:
    try:
        return "data:image/jpeg;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode("ascii")
    except OSError:
        return ""


def _limpar_sessao_autenticacao():
    st.session_state.autenticado = False
    st.session_state.pop("usuario_logado", None)
    st.session_state.pop("ultimo_acesso_em", None)
    st.session_state.pop("login_domain", None)
    st.session_state.pop("erro_login_msg", None)


def _login_bloqueado() -> bool:
    agora = time.time()
    bloqueado_ate = float(st.session_state.get("login_bloqueado_ate", 0) or 0)
    if bloqueado_ate > agora:
        return True
    if bloqueado_ate:
        st.session_state.pop("login_bloqueado_ate", None)
        st.session_state["login_tentativas"] = 0
    return False


def renderizar_login() -> bool:
    processar_acao_via_url()
    st.session_state.setdefault("autenticado", False)
    st.session_state.setdefault("tela_atual", "login")
    if st.session_state.get("autenticado"):
        ultimo_acesso = float(st.session_state.get("ultimo_acesso_em", 0) or 0)
        if ultimo_acesso and time.time() - ultimo_acesso > SESSAO_INATIVA_SEGUNDOS:
            _limpar_sessao_autenticacao()
            st.warning("Sua sessão expirou por inatividade. Faça login novamente.")
        else:
            st.session_state["ultimo_acesso_em"] = time.time()
            return True
    logo = _logo_uri()
    st.markdown('''<style>
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main,.stApp{background:#f5f7fb!important}header,footer,#MainMenu{visibility:hidden!important}
.main .block-container{max-width:940px!important;padding-top:15px!important;padding-bottom:20px!important;padding-left:14px!important;padding-right:14px!important}
.login-logo{width:196px;max-width:70vw;height:64px;display:block;margin:0 auto 60px auto;object-fit:contain;object-position:center}
div[data-testid="stForm"]{width:912px!important;max-width:912px!important;box-sizing:border-box!important;background:#fff!important;border:1px solid #e1e4e8!important;border-radius:3px!important;padding:35px 292px!important;min-height:625px!important;margin:0 auto!important;box-shadow:0 1px 3px rgba(0,0,0,.04)!important}
.login-title{text-align:center;font-size:20px;line-height:1.25;font-weight:600;color:#24292e;margin:0 0 0;white-space:nowrap}
.login-divider{width:100%;height:1px;background:#e1e4e8;margin:25px 0 34px 0;display:block}
.login-divider-after-button{width:100%;height:1px;background:#e1e4e8;margin:32px 0 0 0;display:block}
button[kind="tertiary"]{display:flex!important;justify-content:flex-end!important;width:100%!important;font-size:12px!important;color:#24292e!important;text-decoration:underline!important;margin:-10px 0 15px!important;padding:0!important;height:auto!important;background:transparent!important;border:none!important}
div[data-baseweb="input"]{background:#f4f6f8!important;border:1px solid #d1d5da!important;border-radius:4px!important}div[data-baseweb="select"]>div{background:#fff!important;border:1px solid #d1d5da!important;border-radius:4px!important}
div[data-testid="stForm"] button[kind="secondaryFormSubmit"],div[data-testid="stForm"] button[kind="primaryFormSubmit"]{background:#555!important;color:#fff!important;border:none!important;border-radius:4px!important;height:42px!important;font-size:14px!important;font-weight:600!important;margin-top:15px!important}
.error-box{background:#fff;border:1px solid #e1e4e8;border-left:4px solid #e02424;color:#374151;padding:12px 16px;border-radius:3px;font-size:13px;margin:30px 0 0;box-sizing:border-box;width:100%}
@media(max-width:940px){.main .block-container{max-width:100%!important;padding-top:15px!important;padding-left:14px!important;padding-right:14px!important}div[data-testid="stForm"]{width:100%!important;max-width:912px!important;padding-left:31vw!important;padding-right:31vw!important}}
@media(max-width:768px){.main .block-container{padding:15px 12px 25px!important}.login-logo{width:196px;max-width:70vw;height:58px;margin-bottom:35px}div[data-testid="stForm"]{min-height:0!important;padding:28px 24px!important;width:100%!important;max-width:100%!important}.login-title{white-space:normal}}
</style>''', unsafe_allow_html=True)
    _, center, _ = st.columns([.015,1,.015])
    with center:
        if logo:
            st.markdown(f'<img src="{logo}" class="login-logo" alt="Prefeitura Municipal da Serra">', unsafe_allow_html=True)
        if st.session_state.tela_atual == "redefinicao_solicitar":
            with st.form("form_solicitar_email", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div><div class="login-divider"></div>', unsafe_allow_html=True)
                st.write("**Informe seu e-mail de acesso**")
                email_req = st.text_input("E-mail", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="email_req")
                if st.form_submit_button("Avançar", use_container_width=True):
                    email_alvo = email_req.strip().lower()
                    if not validar_email(email_alvo):
                        st.error("Por favor, informe um e-mail com formato válido.")
                    else:
                        db = carregar_usuarios()
                        if email_alvo not in db or not bool(db[email_alvo].get("aprovado", False)):
                            st.success("Se o e-mail estiver cadastrado e aprovado, as instruções de recuperação serão enviadas.")
                        else:
                            try:
                                # Primeiro estágio: o pedido vai obrigatoriamente para o
                                # administrador. O usuário não recebe autorização automática.
                                admin = str(st.secrets.get("email", {}).get("admin_email", "")).strip().lower()
                                if not validar_email(admin):
                                    st.error("E-mail administrador não configurado corretamente nas Secrets.")
                                else:
                                    token = _criar_token_aprovacao("redefinir", email_alvo)
                                    db[email_alvo]["approval_token_digests"] = {
                                        "redefinir": _digest_token_aprovacao(token)
                                    }
                                    salvar_usuarios(db)

                                    base = str(st.secrets.get("email", {}).get("app_url", "http://localhost:8501")).rstrip("/")
                                    link_aprovar = base + "/?" + urllib.parse.urlencode({"token": token})
                                    body = (
                                        "<h3>Prefeitura Municipal da Serra</h3>"
                                        f"<p>Foi solicitada a <b>recuperação de senha</b> para o usuário "
                                        f"<b>{html.escape(email_alvo)}</b>.</p>"
                                        f'<p><a href="{html.escape(link_aprovar, quote=True)}">Autorizar recuperação</a></p>'
                                        "<p>Se você não reconhece a solicitação, não autorize.</p>"
                                        "<p>O link de autorização expira em 15 minutos e pode ser usado uma única vez.</p>"
                                    )
                                    enviado, mensagem = enviar_email(
                                        admin,
                                        "Solicitação de recuperação de senha - GTI-SESA",
                                        body,
                                    )
                                    if enviado:
                                        st.success(
                                            "Solicitação enviada ao administrador. "
                                            "Aguarde a autorização para receber o link de redefinição."
                                        )
                                    else:
                                        # Não deixa um pedido aparentemente pendente se o
                                        # SMTP falhar: remove o token de autorização.
                                        db[email_alvo].setdefault("approval_token_digests", {}).pop("redefinir", None)
                                        salvar_usuarios(db)
                                        st.error(
                                            "A solicitação não foi enviada ao administrador. "
                                            + mensagem
                                        )
                            except RuntimeError as exc:
                                st.error(
                                    "Não foi possível iniciar a recuperação. "
                                    + str(exc)
                                )
            if st.button("← Voltar ao Login", use_container_width=True, key="btn_voltar_solicitar"):
                st.session_state.tela_atual = "login"
                st.rerun()
        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form("form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div><div class="login-divider"></div>', unsafe_allow_html=True)
                st.write("**Login de Usuário (Obrigatório ser E-mail)**")
                novo = st.text_input("Usuário", value=st.session_state.get("email_solicitante", ""), placeholder="usuario@dominio.com", label_visibility="collapsed", key="novo_user")
                st.write("**Nova Senha (Exatamente 8 caracteres alfanuméricos)**")
                nova = st.text_input("Nova Senha", type="password", placeholder="Nova senha", label_visibility="collapsed", key="nova_pass")
                st.write("**Confirme a Nova Senha**")
                confirma = st.text_input("Confirmar Senha", type="password", placeholder="Repita a senha", label_visibility="collapsed", key="confirma_pass")
                rotulo_botao = "Redefinir Senha" if st.session_state.get("reset_autorizado") else "Cadastrar e Solicitar Autorização"
                if st.form_submit_button(rotulo_botao, use_container_width=True):
                    user = novo.strip().lower()
                    if not validar_email(user):
                        st.error("O nome de usuário deve ser obrigatoriamente um e-mail válido.")
                    elif nova != confirma:
                        st.error("A confirmação de senha não confere com a nova senha digitada.")
                    else:
                        ok, msg = validar_senha_alfanumerica_8(nova)
                        if not ok:
                            st.error(msg)
                        else:
                            db = carregar_usuarios()
                            if st.session_state.get("reset_autorizado"):
                                if user not in db or not bool(db[user].get("aprovado", False)):
                                    st.error("Cadastro não encontrado ou não aprovado.")
                                else:
                                    db[user]["senha"] = hash_senha(nova)
                                    db[user].pop("approval_token_digests", None)
                                    salvar_usuarios(db)
                                    st.session_state.reset_autorizado = False
                                    st.session_state.tela_atual = "login"
                                    st.success("Senha redefinida com sucesso. Agora você pode entrar com a nova senha.")
                                    return False
                            elif not registrar_novo_usuario(db, user, nova):
                                st.error(
                                    "Este e-mail já possui cadastro. "
                                    "Para redefinir uma conta existente, utilize o fluxo "
                                    "de recuperação autorizado; não é permitido sobrescrever "
                                    "credenciais ou aprovação existentes."
                                )
                                return False
                            salvar_usuarios(db)
                            cfg = st.secrets.get("email", {})
                            admin = cfg.get("admin_email", "")
                            base = cfg.get("app_url", "http://localhost:8501").rstrip("/")
                            try:
                                token_aprovar = _criar_token_aprovacao("aprovar", user)
                                token_recusar = _criar_token_aprovacao("recusar", user)
                                db = carregar_usuarios()
                                if user not in db:
                                    st.error("Não foi possível localizar o cadastro recém-criado.")
                                    return False
                                db[user]["approval_token_digests"] = {
                                    "aprovar": _digest_token_aprovacao(token_aprovar),
                                    "recusar": _digest_token_aprovacao(token_recusar),
                                }
                                salvar_usuarios(db)
                                link_aprovar = base + "/?" + urllib.parse.urlencode({"token": token_aprovar})
                                link_recusar = base + "/?" + urllib.parse.urlencode({"token": token_recusar})
                                body = f'<p>Solicitação de cadastro: <b>{html.escape(user)}</b></p><p><a href="{html.escape(link_aprovar, quote=True)}">Autorizar</a> | <a href="{html.escape(link_recusar, quote=True)}">Recusar</a></p>'
                                enviado, mensagem = enviar_email(admin, "Solicitação de Cadastro", body)
                                if not enviado:
                                    st.error(mensagem)
                                else:
                                    st.success("Solicitação enviada ao administrador.")
                                    st.session_state.tela_atual = "login"
                            except RuntimeError:
                                st.error("Não foi possível processar a solicitação de autorização. Verifique a configuração do ambiente.")
            if st.button("← Cancelar", use_container_width=True, key="btn_cancelar_criar"):
                st.session_state.tela_atual = "login"
                st.rerun()
        else:
            with st.form("glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div><div class="login-divider"></div>', unsafe_allow_html=True)
                st.write("**Usuário**")
                usuario = st.text_input("Usuário", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user")
                st.write("**Senha**")
                senha = st.text_input("Senha", type="password", label_visibility="collapsed", key="login_pass")
                if st.form_submit_button("Esqueceu sua senha?", type="tertiary"):
                    st.session_state.tela_atual = "redefinicao_solicitar"
                    st.rerun()
                st.write("**Origem de login**")
                # A origem é fixa neste sistema. Não usamos st.selectbox aqui:
                # isso mantém a tela de login independente de qualquer contexto
                # específico do módulo de inventário.
                st.session_state["login_domain"] = "SERRA.LOCAL"
                st.markdown(
                    '<div style="background:#fff;border:1px solid #d1d5da;border-radius:4px;'
                    'padding:9px 12px;color:#24292e;min-height:20px;">SERRA.LOCAL</div>',
                    unsafe_allow_html=True,
                )
                if st.form_submit_button("Entrar", use_container_width=True):
                    if _login_bloqueado():
                        st.session_state.erro_login_msg = "Acesso temporariamente bloqueado. Aguarde 15 minutos antes de tentar novamente."
                    else:
                        user = usuario.strip().lower()
                        db = carregar_usuarios()
                        valido = False
                        aprovado = False
                        migrar = False
                        if user and senha.strip() and user in db:
                            aprovado = bool(db[user].get("aprovado", False))
                            if aprovado:
                                valido, migrar = verificar_senha(senha, db[user].get("senha", ""))
                        if not (user and senha.strip() and user in db and aprovado and valido):
                            tentativas = int(st.session_state.get("login_tentativas", 0)) + 1
                            st.session_state["login_tentativas"] = tentativas
                            if tentativas >= LOGIN_MAX_TENTATIVAS:
                                st.session_state["login_bloqueado_ate"] = time.time() + LOGIN_BLOQUEIO_SEGUNDOS
                                st.session_state["login_tentativas"] = 0
                                st.session_state.erro_login_msg = "Acesso temporariamente bloqueado por excesso de tentativas. Aguarde 15 minutos."
                            elif user in db and aprovado:
                                st.session_state.erro_login_msg = "Usuário ou senha inválidos."
                            elif user in db:
                                st.session_state.erro_login_msg = "Usuário ou senha inválidos."
                            else:
                                st.session_state.erro_login_msg = "Usuário ou senha inválidos."
                        else:
                            if migrar:
                                db[user]["senha"] = hash_senha(senha)
                                salvar_usuarios(db)
                            st.session_state.autenticado = True
                            st.session_state.usuario_logado = user
                            st.session_state.ultimo_acesso_em = time.time()
                            st.session_state.login_tentativas = 0
                            st.session_state.erro_login_msg = None
                            st.rerun()
                st.markdown('<div class="login-divider-after-button"></div>', unsafe_allow_html=True)
            if st.session_state.get("erro_login_msg"):
                st.markdown(f'<div class="error-box">{html.escape(str(st.session_state.erro_login_msg))}</div>', unsafe_allow_html=True)
    return False
