import os
import re
import threading
from datetime import datetime

from auditoria_integridade_google import normalizar_data_hora
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

import gspread
import pandas as pd
import streamlit as st

import postgresql_persistencia
from google.oauth2.service_account import Credentials

ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNA_CHAVE = "Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Código de Barras", "Origem", "Status"]
TIPOS_PATRIMONIO = ("CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos")
COLUNAS_INVENTARIO = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Foto"]
COLUNAS_PADRAO = COLUNAS_INVENTARIO.copy()
SETORES_PADRAO = ["Consultório", "Almoxarifado", "Farmacia", "Sala de Preparo", "Sala de Vacina", "Sala de curativo", "Gerencia", "Administração", "Odontologia", "Recepção", "Outro Setor"]
LISTA_URS_PADRAO = ["URS Novo Horizonte", "URS Jacaraípe", "URS Boa Vista", "URS Feu Rosa", "URS Serra Sede", "URS Serra Dourada"]
LISTA_ALMOXARIFADO_PADRAO = ["Almoxarifado Central SESA"]
LISTA_UBS_PADRAO = ["UBS André Carloni", "UBS Bairro de Fátima", "UBS Feu Rosa", "UBS Barcelona", "UBS Barro Branco", "UBS Campinho da Serra", "UBS Carapebus", "UBS Carapina Grande", "UBS Central Carapina", "UBS Cidade Continental", "UBS Eldorado", "UBS Jardim Carapina", "UBS Jardim Tropical", "UBS José de Anchieta", "UBS Laranjeiras Velha", "UBS Manguinhos", "UBS Manoel Plaza", "UBS Nova Almeida", "UBS Nova Carapina I", "UBS Nova Carapina II", "UBS Oceania", "UBS Pitanga", "UBS Planalto Serrano (Bloco A)", "UBS Planalto Serrano (Bloco B)", "UBS Porto Canoa", "UBS São Diogo", "UBS São Marcos", "UBS Taquara I", "UBS Taquara II", "UBS Vila Nova de Colares", "UBS Vista da Serra", "UBS Itinerante (atendimento na UBS)"]
UNIDADES_PADRAO = LISTA_URS_PADRAO + LISTA_UBS_PADRAO + LISTA_ALMOXARIFADO_PADRAO
FUSO_HORARIO_APLICACAO = ZoneInfo("America/Sao_Paulo")
_PERSISTENCIA_LOCK = threading.RLock()


def _agora_brasilia() -> datetime:
    return datetime.now(FUSO_HORARIO_APLICACAO)


def _data_hora_cadastro() -> str:
    return _agora_brasilia().strftime("%Y-%m-%d %H:%M:%S")


def formatar_nome_patrimonio(patrimonio: str) -> str:
    return str(patrimonio or "").strip()


def formatar_nome_fabricante(patrimonio: str) -> str:
    p = re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$", "", str(patrimonio or "").strip(), flags=re.I)
    return f"Fabricante {p}" if p else "Fabricante"


def _normalizar_tipo(valor: str) -> str:
    valor = re.sub(r"\s+", " ", str(valor or "").strip())
    mapa = {"computador": "CPU", "cpu": "CPU", "monitor": "Monitores", "monitores": "Monitores", "teclado": "Teclado", "mouse": "Mouse", "impressora": "Imprenssoras", "impressoras": "Imprenssoras", "imprenssoras": "Imprenssoras", "outros dispositivos": "Outros Dispositivos"}
    return mapa.get(valor.casefold(), valor if valor in TIPOS_PATRIMONIO else "")


def _normalizar_unidade_aba(nome: str) -> str:
    aliases = {"URS Jacara_pe": "URS Jacaraípe", "UBS Bairro de F_tima": "UBS Bairro de Fátima"}
    return aliases.get(str(nome or "").strip(), str(nome or "").strip())


def _valor_texto(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def _chave_texto(v) -> str:
    return re.sub(r"\s+", " ", _valor_texto(v)).casefold()


def _eh_vazio(v) -> bool:
    return _valor_texto(v).casefold() in {"", "none", "nan", "null", "<na>"}


def _numero_patrimonio_existe_na_planilha(planilha, numero_patrimonio: str) -> bool:
    """Procura um número em todas as abas, tolerando linhas legadas incompletas."""
    chave = _chave_texto(numero_patrimonio)
    if not chave or planilha is None:
        return False
    try:
        for aba in planilha.worksheets():
            valores = aba.get_all_values()
            if not valores or len(valores) < 2:
                continue
            cabecalho = [str(v).strip() for v in valores[0]]
            largura = len(cabecalho)
            linhas = [
                list(linha[:largura]) + [""] * max(0, largura - len(linha))
                for linha in valores[1:]
            ]
            df = _normalizar_legacy_dataframe(pd.DataFrame(linhas, columns=cabecalho))
            if not df.empty and df["Nº de Patrimônio"].map(_chave_texto).eq(chave).any():
                return True
    except Exception:
        return False
    return False


def validar_cadastro_patrimonio(tipo_patrimonio: str, setor: str, unidade: str, numero_patrimonio: str) -> Tuple[bool, str]:
    tipo = _normalizar_tipo(tipo_patrimonio)
    setor_limpo = _valor_texto(setor)
    unidade_limpa = _normalizar_unidade_aba(unidade)
    numero = _valor_texto(numero_patrimonio)
    if not unidade_limpa or unidade_limpa.casefold().startswith("selecione"):
        return False, "Selecione uma unidade válida."
    if not setor_limpo or setor_limpo.casefold().startswith("selecione"):
        return False, "Selecione ou informe um setor válido."
    if not tipo:
        return False, "Selecione um tipo de patrimônio válido."
    if not numero or numero.casefold().startswith("selecione"):
        return False, "Informe ou leia o número de patrimônio."
    return True, ""


def _inferir_tipo_coluna(cabecalho: str) -> Optional[str]:
    h = _valor_texto(cabecalho).casefold()
    if "fabricante" in h or "setor" in h or "local" in h:
        return None
    if "computador" in h or re.search(r"\bcpu\b", h): return "CPU"
    if "monitor" in h: return "Monitores"
    if "teclado" in h: return "Teclado"
    if "mouse" in h: return "Mouse"
    if "impress" in h: return "Imprenssoras"
    return "Outros Dispositivos"


def _inferir_tipo_fabricante(cabecalho: str) -> Optional[str]:
    return _inferir_tipo_coluna(_valor_texto(cabecalho).casefold().replace("fabricante", "").strip())


def _normalizar_legacy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_INVENTARIO)
    df = df.fillna("").copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "Tipo de Patrimônio" in df.columns and "Nº de Patrimônio" in df.columns:
        normalizado = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)
        for coluna in COLUNAS_INVENTARIO:
            normalizado[coluna] = normalizado[coluna].map(_valor_texto)
        normalizado["Data Cadastro"] = normalizado["Data Cadastro"].map(normalizar_data_hora)
        obrigatorias = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"]
        mask_validos = normalizado[obrigatorias].apply(lambda coluna: coluna.map(lambda valor: not _eh_vazio(valor))).all(axis=1)
        return normalizado.loc[mask_validos].reset_index(drop=True)
    setor_col = "Setor" if "Setor" in df.columns else (df.columns[0] if len(df.columns) else "Setor")
    registros = []
    for _, row in df.iterrows():
        setor = _valor_texto(row.get(setor_col, ""))
        if not setor:
            continue
        for col in df.columns:
            tipo = _inferir_tipo_coluna(col)
            if not tipo:
                continue
            valor = _valor_texto(row.get(col, ""))
            if _eh_vazio(valor):
                continue
            fabricante = ""
            for c2 in df.columns:
                if "fabricante" in str(c2).casefold() and _inferir_tipo_fabricante(c2) == tipo:
                    fabricante = _valor_texto(row.get(c2, ""))
                    break
            registros.append({"Setor": setor, "Tipo de Patrimônio": tipo, "Nº de Patrimônio": valor, "Fabricante": fabricante, "Data Cadastro": ""})
    return pd.DataFrame(registros, columns=COLUNAS_INVENTARIO).fillna("").astype(str)


def conectar_google_sheets():
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec = st.secrets["connections"]["gsheets"]
        elif "gcp_service_account" in st.secrets:
            sec = st.secrets["gcp_service_account"]
        else:
            return None
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        keys = ("type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url")
        creds_dict = {k: sec.get(k) for k in keys}
        creds_dict["type"] = creds_dict.get("type") or "service_account"
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet_url = sec.get("spreadsheet") or st.secrets.get("spreadsheet_url")
        return client.open_by_url(sheet_url) if sheet_url else None
    except Exception as e:
        st.warning(f"Não foi possível conectar ao Google Sheets: {e}")
        return None


def _nome_aba(unidade: str) -> str:
    return _normalizar_unidade_aba(unidade)[:90].strip()

def _carregar_dados_postgresql(unidade: str) -> Optional[pd.DataFrame]:
    """Lê o inventário do PostgreSQL quando a conexão estiver configurada.

    Retorna None quando o PostgreSQL não estiver configurado ou estiver indisponível,
    permitindo o fallback controlado para o Google Sheets durante a migração.
    """
    if not postgresql_persistencia._conexao_configurada():
        return None
    teste = postgresql_persistencia.conectar()
    if teste is None:
        return None
    try:
        teste.close()
    except Exception:
        pass
    try:
        registros = postgresql_persistencia.listar_patrimonios(unidade=unidade)
        linhas = []
        for row in registros:
            # id, unidade, setor, numero_consultorio, especialidade, tipo,
            # numero_patrimonio, codigo_barras, fabricante, data_cadastro,
            # atualizado_em, possui_foto
            _, _, nome_setor, numero_consultorio, especialidade, tipo, numero,
            codigo, fabricante, data_cadastro, _, possui_foto = row
            setor = nome_setor or ""
            if numero_consultorio is not None and str(nome_setor).strip().casefold() == "consultório":
                setor = f"Consultório {numero_consultorio}"
                if especialidade:
                    setor += f" - {especialidade}"
            linhas.append({
                "Setor": setor,
                "Tipo de Patrimônio": _normalizar_tipo(tipo),
                "Nº de Patrimônio": _valor_texto(numero),
                "Fabricante": _valor_texto(fabricante),
                "Data Cadastro": normalizar_data_hora(data_cadastro),
                # A imagem permanece no PostgreSQL; a tabela mantém a indicação
                # de foto sem transportar bytes para a interface.
                "Foto": "📷 Foto armazenada" if possui_foto else "",
            })
        return pd.DataFrame(linhas, columns=COLUNAS_INVENTARIO).fillna("").astype(str)
    except Exception as exc:
        st.warning(f"PostgreSQL indisponível para leitura; usando o espelho legado. Detalhes: {exc}")
        return None


@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    unidade = _normalizar_unidade_aba(unidade)

    # ETAPA 5: PostgreSQL passa a ser a fonte preferencial de leitura quando
    # estiver configurado e acessível. Google Sheets continua como fallback.
    dados_postgresql = _carregar_dados_postgresql(unidade)
    if dados_postgresql is not None:
        return dados_postgresql.reindex(columns=COLUNAS_INVENTARIO, fill_value=""), "PostgreSQL"

    planilha = conectar_google_sheets()
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    if planilha:
        try:
            nomes = [nome_aba]
            if nome_aba == "URS Jacaraípe": nomes.append("URS Jacara_pe")
            elif nome_aba == "UBS Bairro de Fátima": nomes.append("UBS Bairro de F_tima")
            partes, fontes = [], []
            for nome in nomes:
                try: aba = planilha.worksheet(nome)
                except gspread.exceptions.WorksheetNotFound: continue
                valores = aba.get_all_values()
                if valores:
                    partes.append(_normalizar_legacy_dataframe(pd.DataFrame(valores[1:], columns=valores[0])))
                    fontes.append(nome)
            if partes:
                combinado = pd.concat(partes, ignore_index=True).drop_duplicates(subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"], keep="first")
                return combinado.reindex(columns=COLUNAS_INVENTARIO, fill_value=""), f"Google Sheets ({' + '.join(fontes)})"
            return pd.DataFrame(columns=COLUNAS_INVENTARIO), f"Google Sheets ({nome_aba})"
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")
    if os.path.exists(nome_arquivo_local):
        try: return _normalizar_legacy_dataframe(pd.read_excel(nome_arquivo_local, dtype=str)), nome_arquivo_local
        except Exception: pass
    return pd.DataFrame(columns=COLUNAS_INVENTARIO), nome_arquivo_local


def _obter_aba_gravacao(planilha, nome_aba: str, linhas_necessarias: int):
    try: return planilha.worksheet(nome_aba)
    except gspread.exceptions.WorksheetNotFound:
        return planilha.add_worksheet(title=nome_aba, rows=max(100, linhas_necessarias + 10), cols=len(COLUNAS_INVENTARIO))


def _verificar_gravacao_google(aba, valores_esperados) -> bool:
    try:
        lidos = aba.get_all_values()
        esperado = [list(map(str, linha)) for linha in valores_esperados]
        recebido = [list(map(str, linha[:len(COLUNAS_INVENTARIO)])) for linha in lidos[:len(esperado)]]
        return recebido == esperado
    except Exception:
        return False


def _garantir_cabecalho_moderno(aba) -> bool:
    """Garante que a aba de destino usa o schema canônico antes de anexar linhas."""
    try:
        valores = aba.get_all_values()
        if not valores:
            aba.update(values=[COLUNAS_INVENTARIO], range_name="A1")
            return True
        cabecalho = [str(v).strip() for v in valores[0][:len(COLUNAS_INVENTARIO)]]
        if cabecalho == COLUNAS_INVENTARIO:
            return True
        return False
    except Exception:
        return False


def _anexar_no_google(df_novos: pd.DataFrame, unidade: str) -> bool:
    """Anexa registros sem limpar/regravar a aba inteira."""
    df_novos = _normalizar_legacy_dataframe(df_novos).fillna("").astype(str)
    if df_novos.empty:
        return False
    planilha = conectar_google_sheets()
    if not planilha:
        st.error("⚠️ Google Sheets indisponível: o cadastro NÃO foi considerado salvo na tabela online.")
        return False
    unidade = _normalizar_unidade_aba(unidade)
    nome_aba = _nome_aba(unidade)
    try:
        aba = _obter_aba_gravacao(planilha, nome_aba, len(df_novos) + 1)
        if not _garantir_cabecalho_moderno(aba):
            existente, _ = carregar_dados_excel(unidade)
            combinado = pd.concat([existente, df_novos], ignore_index=True)
            return salvar_no_excel(combinado, unidade)
        # Releitura imediatamente antes do append: se uma tentativa anterior
        # já chegou ao Sheets mas a resposta se perdeu, não duplicamos a linha.
        atuais = aba.get_all_values()
        existentes = {
            _chave_texto(linha[2])
            for linha in atuais[1:]
            if len(linha) > 2 and not _eh_vazio(linha[2])
        }
        valores = []
        for linha in df_novos[COLUNAS_INVENTARIO].values.tolist():
            chave = _chave_texto(linha[2])
            if chave and chave in existentes:
                continue
            valores.append([str(v) for v in linha])
            if chave:
                existentes.add(chave)
        if not valores:
            carregar_dados_excel.clear()
            return True
        aba.append_rows(valores, value_input_option="RAW", insert_data_option="INSERT_ROWS")
        lidos = aba.get_all_values()
        existentes_pos = [list(map(str, linha[:len(COLUNAS_INVENTARIO)])) for linha in lidos[1:]]
        if sum(1 for linha in valores if linha in existentes_pos) != len(valores):
            st.error("⚠️ O Google Sheets não confirmou todas as linhas anexadas.")
            return False
        carregar_dados_excel.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ Erro ao anexar no Google Sheets: {e}")
        return False


def _serializar_persistencia(func):
    """Serializa operações de persistência no processo Streamlit."""
    def wrapper(*args, **kwargs):
        with _PERSISTENCIA_LOCK:
            return func(*args, **kwargs)
    wrapper.__name__ = getattr(func, "__name__", "wrapper")
    wrapper.__doc__ = getattr(func, "__doc__", None)
    return wrapper


@_serializar_persistencia
def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    unidade = _normalizar_unidade_aba(unidade)
    df_salvar = _normalizar_legacy_dataframe(df).fillna("").astype(str)
    planilha = conectar_google_sheets()
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    valores = [COLUNAS_INVENTARIO] + df_salvar[COLUNAS_INVENTARIO].values.tolist()
    sucesso_sheets = False
    if planilha:
        try:
            aba = _obter_aba_gravacao(planilha, nome_aba, len(df_salvar) + 1)
            linhas_limpeza = max(aba.row_count, len(valores), 100)
            aba.batch_clear([f"A1:F{linhas_limpeza}"])
            aba.update(values=valores, range_name="A1")
            sucesso_sheets = _verificar_gravacao_google(aba, valores)
            if not sucesso_sheets:
                st.error("⚠️ O Google Sheets aceitou a operação, mas a confirmação não corresponde aos dados enviados.")
        except Exception as e:
            st.error(f"⚠️ Erro ao gravar no Google Sheets: {e}")
    else:
        st.error("⚠️ Google Sheets indisponível: o cadastro NÃO foi considerado salvo na tabela online.")
    try: df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception as e: st.error(f"Erro no backup local: {e}")
    carregar_dados_excel.clear()
    return sucesso_sheets


@_serializar_persistencia
def registrar_patrimonio(codigo_barras: str, tipo_patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "", foto_data_url: str = "", foto_bytes: Optional[bytes] = None) -> bool:
    codigo = _valor_texto(codigo_barras)
    setor_limpo = _valor_texto(setor)
    unidade_limpa = _normalizar_unidade_aba(unidade)
    tipo = _normalizar_tipo(tipo_patrimonio)
    fabricante_limpo = _valor_texto(fabricante)
    numero = _valor_texto(numero_patrimonio) or codigo
    valido, mensagem = validar_cadastro_patrimonio(tipo, setor_limpo, unidade_limpa, numero)
    if not valido:
        if mensagem: st.warning(mensagem)
        return False
    pg_configurado = postgresql_persistencia._conexao_configurada()

    # PostgreSQL é a fonte oficial de verdade quando configurado.
    # O Sheets só participa da prevenção de duplicidade no modo legado, sem PostgreSQL.
    if not pg_configurado:
        dados_atuais, _ = carregar_dados_excel(unidade_limpa)
        dados_atuais = _normalizar_legacy_dataframe(dados_atuais)
        numeros_existentes = {
            _chave_texto(valor) for valor in dados_atuais["Nº de Patrimônio"]
            if not _eh_vazio(valor)
        }
        if _chave_texto(numero) in numeros_existentes:
            st.warning("O número de patrimônio/código de barras já está cadastrado na unidade.")
            return False
        planilha_validacao = conectar_google_sheets()
        if planilha_validacao is not None and _numero_patrimonio_existe_na_planilha(planilha_validacao, numero):
            st.warning("O número de patrimônio/código de barras já está cadastrado no Google Sheets.")
            return False

    if pg_configurado:
        ok_pg, msg_pg = postgresql_persistencia.salvar_patrimonio(
            codigo_barras=codigo,
            tipo=tipo,
            setor=setor_limpo,
            unidade=unidade_limpa,
            fabricante=fabricante_limpo,
            numero_patrimonio=numero,
            foto_bytes=foto_bytes,
        )
        if not ok_pg:
            st.warning(msg_pg)
            return False

    nova = {
        "Setor": setor_limpo,
        "Tipo de Patrimônio": tipo,
        "Nº de Patrimônio": numero,
        "Fabricante": fabricante_limpo,
        "Data Cadastro": _data_hora_cadastro(),
        "Foto": _valor_texto(foto_data_url)[:45000],
    }
    sucesso_sheets = _anexar_no_google(
        pd.DataFrame([nova], columns=COLUNAS_INVENTARIO), unidade_limpa
    )

    # Com PostgreSQL ativo, a gravação principal já foi confirmada no banco.
    # O Sheets é espelho durante a migração; sua falha não desfaz a transação.
    if pg_configurado:
        if not sucesso_sheets:
            st.warning(
                "⚠️ PostgreSQL confirmou o patrimônio, mas o espelho Google Sheets "
                "não foi confirmado. O registro permanece salvo no PostgreSQL."
            )
        return True
    return sucesso_sheets


@_serializar_persistencia
def registrar_patrimonios_em_lote(registros, unidade: str):
    """Registra um lote com PostgreSQL como fonte primária e Sheets como espelho."""
    registros = list(registros or [])
    if not registros:
        return False, ["O lote está vazio."]
    if len(registros) > 1000:
        return False, ["O lote excede o limite de 1000 patrimônios por operação."]

    unidade_limpa = _normalizar_unidade_aba(unidade)
    df, _ = carregar_dados_excel(unidade_limpa)
    df = _normalizar_legacy_dataframe(df)

    existentes = set(df["Nº de Patrimônio"].map(_chave_texto))
    vistos, novos, erros = set(), [], []

    for posicao, item in enumerate(registros, start=1):
        item = item or {}
        numero = _valor_texto(item.get("numero_patrimonio", "")) or _valor_texto(item.get("codigo_barras", ""))
        tipo = _normalizar_tipo(item.get("tipo_patrimonio", "") or item.get("tipo", ""))
        setor = _valor_texto(item.get("setor", ""))
        fabricante = _valor_texto(item.get("fabricante", ""))
        foto_data_url = _valor_texto(item.get("foto_data_url", ""))[:45000]
        foto_bytes = item.get("foto_bytes")

        ok, mensagem = validar_cadastro_patrimonio(tipo, setor, unidade_limpa, numero)
        if not ok:
            erros.append(f"Registro {posicao}: {mensagem}")
            continue

        chave = _chave_texto(numero)
        if chave in existentes:
            erros.append(f"Registro {posicao}: o patrimônio {numero} já existe na unidade.")
            continue
        if chave in vistos:
            erros.append(f"Registro {posicao}: o patrimônio {numero} está duplicado no próprio lote.")
            continue

        vistos.add(chave)
        novos.append({
            "Setor": setor,
            "Tipo de Patrimônio": tipo,
            "Nº de Patrimônio": numero,
            "Fabricante": fabricante,
            "Data Cadastro": _data_hora_cadastro(),
            "Foto": foto_data_url,
            "_foto_bytes": foto_bytes,
            "_codigo_barras": _valor_texto(item.get("codigo_barras", "")),
        })

    if erros:
        return False, erros

    if postgresql_persistencia._conexao_configurada():
        registros_pg = [
            {
                "numero_patrimonio": item["Nº de Patrimônio"],
                "codigo_barras": item["_codigo_barras"],
                "tipo": item["Tipo de Patrimônio"],
                "setor": item["Setor"],
                "fabricante": item["Fabricante"],
                "data_cadastro": item["Data Cadastro"],
                "foto_bytes": item["_foto_bytes"],
            }
            for item in novos
        ]
        ok_pg, msg_pg = postgresql_persistencia.salvar_patrimonios_em_lote(
            registros_pg, unidade_limpa
        )
        if not ok_pg:
            return False, [msg_pg]

        df_espelho = pd.DataFrame(novos, columns=COLUNAS_INVENTARIO + ["_foto_bytes", "_codigo_barras"])
        df_espelho = df_espelho[COLUNAS_INVENTARIO]
        sucesso_sheets = _anexar_no_google(df_espelho, unidade_limpa)
        if not sucesso_sheets:
            st.warning(
                "⚠️ O lote foi confirmado no PostgreSQL, mas o espelho Google Sheets "
                "não confirmou a gravação."
            )
        return True, []

    df_espelho = pd.DataFrame(novos, columns=COLUNAS_INVENTARIO + ["_foto_bytes", "_codigo_barras"])
    df_espelho = df_espelho[COLUNAS_INVENTARIO]
    sucesso = _anexar_no_google(df_espelho, unidade_limpa)
    return sucesso, [] if sucesso else ["Falha ao confirmar a gravação do lote no Google Sheets."]

def adicionar_e_salvar_sem_sobrescrever(
    codigo: str,
    patrimonio: str,
    setor: str,
    unidade: str,
    fabricante: str = "",
    numero_patrimonio: str = "",
    foto_data_url: str = "",
    foto_bytes: Optional[bytes] = None,
) -> bool:
    return registrar_patrimonio(
        codigo,
        patrimonio,
        setor,
        unidade,
        fabricante,
        numero_patrimonio,
        foto_data_url,
        foto_bytes,
    )


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever



def _aplicar_edicao_patrimonio(
    df: pd.DataFrame,
    setor_atual: str,
    numero_atual: str,
    novo_setor: str,
    novo_tipo: str,
    novo_numero: str,
    novo_fabricante: str,
) -> Tuple[pd.DataFrame, bool]:
    """Aplica uma edição local ao espelho sem depender de posição da linha."""
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False

    mask = (
        df["Setor"].map(_chave_texto).eq(_chave_texto(setor_atual))
        & df["Nº de Patrimônio"].map(_chave_texto).eq(_chave_texto(numero_atual))
    )
    if not mask.any():
        return df.copy(), False

    novo = df.copy()
    idx = novo.index[mask][0]
    novo.at[idx, "Setor"] = novo_setor
    novo.at[idx, "Tipo de Patrimônio"] = novo_tipo
    novo.at[idx, "Nº de Patrimônio"] = novo_numero
    novo.at[idx, "Fabricante"] = novo_fabricante
    return novo, True


def editar_patrimonio(
    setor_atual: str,
    numero_atual: str,
    novo_setor: str,
    novo_tipo: str,
    novo_numero: str,
    novo_fabricante: str,
    unidade: str,
) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_edicao_patrimonio(
        df, setor_atual, numero_atual, novo_setor, novo_tipo, novo_numero, novo_fabricante
    )
    if not alterado:
        st.warning("⚠️ Patrimônio não encontrado para edição.")
        return False

    ok_validacao, msg_validacao = validar_cadastro_patrimonio(
        novo_tipo, novo_setor, unidade, novo_numero
    )
    if not ok_validacao:
        st.warning(f"⚠️ Edição cancelada: {msg_validacao}")
        return False

    if postgresql_persistencia._conexao_configurada():
        ok_pg, msg_pg = postgresql_persistencia.atualizar_patrimonio_por_identificacao(
            unidade,
            setor_atual,
            numero_atual,
            novo_tipo,
            novo_setor,
            novo_numero,
            novo_fabricante,
        )
        if not ok_pg:
            st.warning(f"⚠️ Edição cancelada: {msg_pg}")
            return False

        sucesso_sheets = salvar_no_excel(novo, unidade)
        if not sucesso_sheets:
            st.warning(
                "⚠️ O patrimônio foi atualizado no PostgreSQL, mas o espelho Google Sheets "
                "não confirmou a atualização."
            )
        return True

    return salvar_no_excel(novo, unidade)


def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> Tuple[pd.DataFrame, bool]:
    df = _normalizar_legacy_dataframe(df)
    if df.empty: return df.copy(), False
    mask = df["Setor"].map(_chave_texto) == _chave_texto(setor)
    return (df.loc[~mask].copy(), True) if mask.any() else (df.copy(), False)


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> Tuple[pd.DataFrame, bool]:
    """Exclui exatamente um patrimônio quando o alvo é um número.

    Mantém compatibilidade com a interface legada que envia o tipo.
    """
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    mask_setor = df["Setor"].map(_chave_texto) == _chave_texto(setor)
    if not mask_setor.any():
        return df.copy(), False
    alvo = _valor_texto(coluna)
    mask_excluir = mask_setor & df["Nº de Patrimônio"].map(_chave_texto).eq(_chave_texto(alvo))
    if mask_excluir.any():
        return df.loc[~mask_excluir].copy(), True
    tipo = _normalizar_tipo(re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio", "", alvo, flags=re.I))
    if not tipo:
        return df.copy(), False
    candidatos = df.index[mask_setor & df["Tipo de Patrimônio"].astype(str).eq(tipo)]
    if len(candidatos) == 0:
        return df.copy(), False
    mask_excluir = df.index == candidatos[0]
    return df.loc[~mask_excluir].copy(), True


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_setor(df, setor)
    if not alterado:
        return False

    if postgresql_persistencia._conexao_configurada():
        ok_pg, msg_pg = postgresql_persistencia.excluir_setor_postgresql(unidade, setor)
        if not ok_pg:
            st.warning(f"⚠️ Exclusão cancelada: {msg_pg}")
            return False

        sucesso_sheets = salvar_no_excel(novo, unidade)
        if not sucesso_sheets:
            st.warning(
                "⚠️ O setor foi excluído do PostgreSQL, mas o espelho Google Sheets "
                "não confirmou a atualização."
            )
        return True

    return salvar_no_excel(novo, unidade)


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    if not alterado:
        return False

    alvo_numero = None
    setor_mask = df["Setor"].map(_chave_texto) == _chave_texto(setor)
    candidatos = df.loc[setor_mask]
    if not candidatos.empty:
        alvo = _valor_texto(coluna)
        por_numero = candidatos[
            candidatos["Nº de Patrimônio"].map(_chave_texto) == _chave_texto(alvo)
        ]
        if not por_numero.empty:
            alvo_numero = _valor_texto(por_numero.iloc[0]["Nº de Patrimônio"])
        else:
            tipo = _normalizar_tipo(
                re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio", "", alvo, flags=re.I)
            )
            por_tipo = candidatos[
                candidatos["Tipo de Patrimônio"].astype(str).map(_normalizar_tipo) == tipo
            ] if tipo else pd.DataFrame()
            if len(por_tipo) == 1:
                alvo_numero = _valor_texto(por_tipo.iloc[0]["Nº de Patrimônio"])

    if postgresql_persistencia._conexao_configurada():
        if not alvo_numero:
            st.warning("⚠️ Não foi possível identificar com segurança o número do patrimônio para excluir.")
            return False

        ok_pg, msg_pg = postgresql_persistencia.excluir_patrimonio_por_identificacao(
            unidade, setor, alvo_numero
        )
        if not ok_pg:
            st.warning(f"⚠️ Exclusão cancelada: {msg_pg}")
            return False

        sucesso_sheets = salvar_no_excel(novo, unidade)
        if not sucesso_sheets:
            st.warning(
                "⚠️ O patrimônio foi excluído do PostgreSQL, mas o espelho Google Sheets "
                "não confirmou a atualização."
            )
        return True

    return salvar_no_excel(novo, unidade)
