import os
import re
import pandas as pd
import numpy as np
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Tuple, List, Dict, Any

# ==============================================================================
# CONFIGURAÇÕES GLOBAIS E ESTRUTURA OFICIAL (GTI-SESA)
# ==============================================================================
ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNA_CHAVE = "Local / Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Status", "Setor"]

# ==============================================================================
# LISTAS PADRONIZADAS DOS MENUS
# Regra: nenhuma opção duplicada, nenhum rótulo de coluna e tudo em ordem alfabética.
# "Local / Setor" é nome interno da coluna e NUNCA é opção de menu.
# "Fabricante ..." também é nome interno de coluna e NUNCA é opção de menu.
# ==============================================================================

def _limpar_opcoes_menu(opcoes, bloqueios=None):
    """Remove vazios/duplicados e retorna as opções em ordem alfabética."""
    bloqueios = [str(x).casefold() for x in (bloqueios or [])]
    unicas = {}
    for valor in opcoes:
        valor = re.sub(r"\s+", " ", str(valor or "").strip())
        if not valor:
            continue
        chave = valor.casefold()
        if any(b in chave for b in bloqueios):
            continue
        if chave not in unicas:
            unicas[chave] = valor
    return sorted(unicas.values(), key=lambda x: x.casefold())


LISTA_UNIDADES_PADRAO = _limpar_opcoes_menu([
    "URS I", "URS II", "URS III",
    "UBS Central", "UBS Jardim", "UBS Vila Nova", "UBS Centro"
])

SETORES_PADRAO = _limpar_opcoes_menu([
    "Almoxarifado", "Consultório 01", "Consultório 02", "Diretoria",
    "Farmácia", "Faturamento", "Laboratório", "Recepção",
    "Sala de Vacina", "TI / Suporte", "Triagem",
    # qualquer ocorrência acidental de rótulos de coluna será descartada
], bloqueios=["local/setor", "local / setor", "fabricante"])

FABRICANTES_PADRAO = _limpar_opcoes_menu([
    "Acer", "AOC", "Apple", "Asus", "Brother", "Cisco", "Daten",
    "Dell", "Epson", "HP", "Intelbras", "Lenovo", "LG", "Logitech",
    "Multilaser", "Outro", "POSITIVO", "Samsung", "TP-Link", "Zebra",
    # Estes rótulos não podem entrar no menu de fabricantes:
    "Fabricante Monitor", "Fabricante do Monitor",
    "Fabricante Computador", "Fabricante do Computador",
    "Fabricante CPU", "Fabricante Nobreak", "Fabricante Teclado",
    "Fabricante Mouse", "Fabricante Impressora", "Fabricante Switch",
    "Fabricante Estabilizador", "Fabricante dos Monitores",
    "Local / Setor"
], bloqueios=[
    "fabricante", "local/setor", "local / setor",
    "nº de patrimônio", "n° de patrimônio", "patrimônio", "setor"
])

# ==============================================================================
# REGRA GLOBAL DE AUDITORIA — TIPO DE PATRIMÔNIO
# Esta é a lista única e fechada usada em TODAS as UBS/URS e em todas as páginas.
# Qualquer opção antiga ou inesperada é bloqueada.
# ==============================================================================
TIPOS_PATRIMONIO_PERMITIDOS = (
    "CPU",
    "Monitores",
    "Teclado",
    "Mouse",
    "Imprenssoras",
    "Outros Dispositivos",
)

# Mapeamento único do menu para as colunas da tabela.
EQUIPAMENTOS_OPCOES = {
    "CPU": ("CPU - Nº de Patrimônio", "Fabricante CPU"),
    "Monitores": ("Monitores - Nº de Patrimônio", "Fabricante dos Monitores"),
    "Teclado": ("Teclado - Nº de Patrimônio", "Fabricante Teclado"),
    "Mouse": ("Mouse - Nº de Patrimônio", "Fabricante Mouse"),
    "Imprenssoras": ("Imprenssoras - Nº de Patrimônio", "Fabricante Imprenssoras"),
    "Outros Dispositivos": (
        "Outros Dispositivos - Nº de Patrimônio",
        "Fabricante Outros Dispositivos",
    ),
}

def opcoes_tipo_patrimonio():
    """
    FONTE ÚNICA E FECHADA DO MENU "Tipo de Patrimônio".
    Nenhum dado do Sheets, fabricante ou coluna pode acrescentar opções.
    """
    return [
        "CPU",
        "Monitores",
        "Teclado",
        "Mouse",
        "Imprenssoras",
        "Outros Dispositivos",
    ]


def validar_tipo_patrimonio(tipo: str) -> str:
    """Aceita somente os seis tipos oficialmente autorizados."""
    tipo_limpo = re.sub(r"\s+", " ", str(tipo or "").strip())
    if tipo_limpo not in TIPOS_PATRIMONIO_PERMITIDOS:
        raise ValueError(
            f"Tipo de patrimônio inválido: {tipo_limpo!r}. "
            "Permitidos: " + ", ".join(TIPOS_PATRIMONIO_PERMITIDOS)
        )
    return tipo_limpo


def formatar_nome_patrimonio(patrimonio: str) -> str:
    p_limpo = validar_tipo_patrimonio(patrimonio)
    if p_limpo in EQUIPAMENTOS_OPCOES:
        return EQUIPAMENTOS_OPCOES[p_limpo][0]
    if not re.search(r'-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', p_limpo, flags=re.IGNORECASE):
        p_limpo = f"{p_limpo} - Nº de Patrimônio"
    return MAPA_RENOMEAR_COLUNAS.get(p_limpo, p_limpo)

def formatar_nome_fabricante(patrimonio: str) -> str:
    p_limpo = validar_tipo_patrimonio(patrimonio)
    if p_limpo in EQUIPAMENTOS_OPCOES:
        return EQUIPAMENTOS_OPCOES[p_limpo][1]
    
    base_nome = re.sub(r'\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', '', p_limpo, flags=re.IGNORECASE)
    if "monitor" in base_nome.lower():
        return "Fabricante dos Monitores"
    nome_fab = f"Fabricante {base_nome}"
    return MAPA_RENOMEAR_COLUNAS.get(nome_fab, nome_fab)

# ==============================================================================
# CONEXÃO GOOGLE SHEETS
# ==============================================================================
def conectar_google_sheets():
    """Conecta ao Google Sheets buscando as credenciais em [connections.gsheets]."""
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec_gsheets = st.secrets["connections"]["gsheets"]
        elif "gcp_service_account" in st.secrets:
            sec_gsheets = st.secrets["gcp_service_account"]
        else:
            return None

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets", 
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds_dict = {
            "type": sec_gsheets.get("type", "service_account"),
            "project_id": sec_gsheets.get("project_id"),
            "private_key_id": sec_gsheets.get("private_key_id"),
            "private_key": sec_gsheets.get("private_key"),
            "client_email": sec_gsheets.get("client_email"),
            "client_id": sec_gsheets.get("client_id"),
            "auth_uri": sec_gsheets.get("auth_uri"),
            "token_uri": sec_gsheets.get("token_uri"),
            "auth_provider_x509_cert_url": sec_gsheets.get("auth_provider_x509_cert_url"),
            "client_x509_cert_url": sec_gsheets.get("client_x509_cert_url")
        }

        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_url = sec_gsheets.get("spreadsheet") or st.secrets.get("spreadsheet_url")
        if sheet_url:
            return client.open_by_url(sheet_url)

    except Exception as e:
        st.warning(f"Não foi possível conectar ao Google Sheets: {e}")
    return None

def expurgar_e_normalizar_setores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Auditoria estrutural antes de ler/salvar:
    - remove Local / Setor e Setor como opções/colunas alternativas;
    - consolida nomes equivalentes de patrimônio/fabricante;
    - elimina colunas duplicadas;
    - mantém somente a estrutura oficial;
    - ordena registros alfabeticamente por setor;
    - nunca cria uma coluna a partir de um texto de menu.
    """
    df = df.copy().fillna("").astype(str)

    # 1. Migra a antiga coluna "Setor" para a coluna oficial.
    if "Setor" in df.columns:
        if COLUNA_CHAVE in df.columns:
            atual = df[COLUNA_CHAVE].replace("", np.nan)
            df[COLUNA_CHAVE] = atual.fillna(df["Setor"]).fillna("")
        else:
            df[COLUNA_CHAVE] = df["Setor"]
        df = df.drop(columns=["Setor"])

    # 2. Consolida nomes antigos/duplicados.
    for col_antiga, col_oficial in MAPA_RENOMEAR_COLUNAS.items():
        if col_antiga in df.columns:
            if col_oficial not in df.columns:
                df[col_oficial] = df[col_antiga]
            else:
                atual = df[col_oficial].replace("", np.nan)
                df[col_oficial] = atual.fillna(df[col_antiga]).fillna("")
            df = df.drop(columns=[col_antiga])

    # 3. Elimina colunas obsoletas.
    cols_para_remover = [c for c in COLUNAS_OBSOLETAS if c in df.columns]
    if cols_para_remover:
        df = df.drop(columns=cols_para_remover)

    # 4. Assegura a coluna oficial de setor.
    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    # 5. Consolida qualquer coluna repetida pelo mesmo nome.
    #    Se houver duplicata, preserva o primeiro valor preenchido.
    if df.columns.duplicated().any():
        novo = pd.DataFrame(index=df.index)
        for nome in dict.fromkeys(df.columns):
            partes = df.loc[:, df.columns == nome]
            serie = partes.iloc[:, 0].astype(str)
            for i in range(1, partes.shape[1]):
                outra = partes.iloc[:, i].astype(str)
                serie = serie.mask(serie.str.strip().eq(""), outra)
            novo[nome] = serie
        df = novo

    # 6. Garante somente as colunas oficiais.
    for col in ORDEM_COLUNAS_OFICIAL:
        if col not in df.columns:
            df[col] = ""

    df = df[ORDEM_COLUNAS_OFICIAL].fillna("").astype(str)

    # 7. Remove linhas totalmente vazias.
    cols_dados = ORDEM_COLUNAS_OFICIAL
    vazias = df[cols_dados].apply(
        lambda row: all(str(v).strip() == "" for v in row), axis=1
    )
    df = df[~vazias].copy()

    # 8. Ordenação alfabética dos setores armazenados.
    df[COLUNA_CHAVE] = df[COLUNA_CHAVE].astype(str).str.strip()
    df = df.sort_values(
        by=COLUNA_CHAVE,
        ascending=True,
        key=lambda x: x.str.casefold(),
        kind="stable"
    )

    return df.reset_index(drop=True)[ORDEM_COLUNAS_OFICIAL]


def aplicar_estilizacao_sheets(aba: gspread.Worksheet, total_linhas: int, total_colunas: int):
    """Aplica formatação visual no Google Sheets."""
    try:
        aba.freeze(rows=1)
        aba.format(f"A1:{gspread.utils.rowcol_to_a1(1, total_colunas)}", {
            "backgroundColor": {"red": 0.12, "green": 0.30, "blue": 0.47},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE"
        })

        if total_linhas > 1:
            intervalo_dados = f"A2:{gspread.utils.rowcol_to_a1(total_linhas, total_colunas)}"
            aba.format(intervalo_dados, {
                "textFormat": {"fontSize": 9},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
    except Exception:
        pass

@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """Carrega dados do Google Sheets organizando colunas e eliminando duplicatas."""
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows="100", cols="20")

            valores = aba.get_all_values()
            if valores and len(valores) > 1:
                df = pd.DataFrame(valores[1:], columns=valores[0])
                df = df.fillna("").astype(str)
                df = expurgar_e_normalizar_setores(df)
                return df, f"Google Sheets ({nome_aba})"
            elif valores and len(valores) == 1:
                df = pd.DataFrame(columns=valores[0])
                df = expurgar_e_normalizar_setores(df)
                return df, f"Google Sheets ({nome_aba})"
            else:
                return pd.DataFrame(columns=ORDEM_COLUNAS_OFICIAL), f"Google Sheets ({nome_aba})"
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")

    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            df = df.fillna("")
            df = expurgar_e_normalizar_setores(df)
            return df, nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=ORDEM_COLUNAS_OFICIAL), nome_arquivo_local

# ==============================================================================
# FUNÇÕES DE PERSISTÊNCIA E OPERAÇÃO
# ==============================================================================
def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """Salva os dados no Google Sheets mantendo a estrutura limpa e organizada."""
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    df_salvar = expurgar_e_normalizar_setores(df).fillna("").astype(str)
    df_salvar = df_salvar.reindex(columns=ORDEM_COLUNAS_OFICIAL, fill_value="")

    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows="100", cols="20")

            aba.clear()
            valores = [df_salvar.columns.tolist()] + df_salvar.values.tolist()
            aba.update(values=valores, range_name="A1")
            
            aplicar_estilizacao_sheets(aba, len(valores), len(df_salvar.columns))
            sucesso_sheets = True
        except Exception as e:
            st.error(f"⚠️ Erro ao gravar no Google Sheets: {e}")

    try:
        df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception as e:
        st.error(f"Erro no backup local: {e}")

    st.cache_data.clear()
    return sucesso_sheets or os.path.exists(nome_arquivo_local)

def adicionar_ou_atualizar_registro(unidade: str, setor_selecionado: str, dados_equipamentos: Dict[str, str]) -> bool:
    """Insere/atualiza registros garantindo o uso exclusivo das colunas oficiais."""
    df, _ = carregar_dados_excel(unidade)
    setor_limpo = setor_selecionado.strip()
    
    dados_normalizados = {}
    for k, v in dados_equipamentos.items():
        col_destino = MAPA_RENOMEAR_COLUNAS.get(k, k)
        if col_destino in ORDEM_COLUNAS_OFICIAL:
            dados_normalizados[col_destino] = v

    indices_setor = df[df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor_limpo.lower()].index
    linha_destino_idx = None

    if len(indices_setor) > 0:
        for idx in indices_setor:
            colisoes = False
            for col, val in dados_normalizados.items():
                if val and col in df.columns:
                    val_atual = str(df.at[idx, col]).strip()
                    if val_atual != "":
                        colisoes = True
                        break
            if not colisoes:
                linha_destino_idx = idx
                break

    if linha_destino_idx is None:
        nova_linha = {c: "" for c in ORDEM_COLUNAS_OFICIAL}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        for col, val in dados_normalizados.items():
            if val and col in nova_linha:
                nova_linha[col] = str(val).strip()
        
        df_nova = pd.DataFrame([nova_linha])
        df = pd.concat([df, df_nova], ignore_index=True)
    else:
        for col, val in dados_normalizados.items():
            if val and col in df.columns:
                df.at[linha_destino_idx, col] = str(val).strip()

    return salvar_no_excel(df, unidade)

def adicionar_e_salvar_sem_sobrescrever(
    codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = ""
) -> bool:
    """Cadastra um patrimônio individual vindo do leitor de código de barras."""
    setor_limpo = setor.strip()
    codigo_limpo = codigo.strip()
    fabricante_limpo = fabricante.strip()
    
    patrimonio_col = formatar_nome_patrimonio(patrimonio)
    coluna_fabricante = formatar_nome_fabricante(patrimonio)

    if not setor_limpo or not codigo_limpo or not patrimonio_col or not unidade:
        return False

    dados_envio = {
        patrimonio_col: codigo_limpo,
        coluna_fabricante: fabricante_limpo
    }
    
    return adicionar_ou_atualizar_registro(unidade, setor_limpo, dados_envio)

def excluir_setor(setor: str, unidade: str) -> bool:
    """Exclui todas as entradas de um setor específico."""
    df, _ = carregar_dados_excel(unidade)
    if not df.empty and COLUNA_CHAVE in df.columns:
        setor_limpo = setor.strip().lower()
        mask_manter = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() != setor_limpo
        df_filtrado = df[mask_manter]
        return salvar_no_excel(df_filtrado, unidade)
    return False

def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    """Exclui o código do patrimônio e o fabricante associado."""
    df, _ = carregar_dados_excel(unidade)
    coluna_oficial = MAPA_RENOMEAR_COLUNAS.get(coluna, coluna)

    if not df.empty and COLUNA_CHAVE in df.columns and coluna_oficial in df.columns:
        df = df.fillna("").astype(str)
        coluna_fabricante = formatar_nome_fabricante(coluna_oficial)
        
        mask = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor.strip().lower()
        if mask.any():
            df.loc[mask, coluna_oficial] = ""
            if coluna_fabricante in df.columns:
                df.loc[mask, coluna_fabricante] = ""
            
            cols_dados = [c for c in df.columns if c != COLUNA_CHAVE]
            mask_vazia = df[cols_dados].apply(lambda row: "".join(row.values).strip() == "", axis=1)
            df = df[~mask_vazia]

            return salvar_no_excel(df, unidade)
    return False

# ==============================================================================
# INTERFACE STREAMLIT E PADRONIZAÇÃO DE PÁGINAS
# ==============================================================================
st.set_page_config(page_title="Sistema de Inventário GTI-SESA", layout="wide")

st.title("🖥️ Sistema de Inventário GTI-SESA")

# Sidebar - Seleção da Unidade e Página
st.sidebar.header("⚙️ Configurações Gerais")
unidade_selecionada = st.sidebar.selectbox("Selecione a Unidade (URS / UBS):", LISTA_UNIDADES_PADRAO)

pagina = st.sidebar.radio("Navegação de Páginas:", [
    "1. Cadastro / Leitor de Código de Barras",
    "2. Cadastramento por Setor (Lote)",
    "3. Consulta e Gerenciamento do Inventário"
])

st.sidebar.markdown("---")
st.sidebar.caption(f"Unidade Atual: **{unidade_selecionada}**")

# ------------------------------------------------------------------------------
# PÁGINA 1: CADASTRO RÁPIDO / LEITOR DE CÓDIGO DE BARRAS
# ------------------------------------------------------------------------------
if pagina == "1. Cadastro / Leitor de Código de Barras":
    st.subheader("📦 Cadastro Rápido via Leitor de Código de Barras")
    
    col1, col2 = st.columns(2)
    with col1:
        setor_input = st.selectbox("Selecione o Setor:", SETORES_PADRAO)
        tipo_equipamento = st.selectbox("Selecione o Tipo de Patrimônio:", opcoes_tipo_patrimonio(), key="tipo_patrimonio_principal")
    
    with col2:
        fabricante_input = st.selectbox("Selecione o Fabricante:", FABRICANTES_PADRAO)
        codigo_patrimonio = st.text_input("Código de Patrimônio (Bipagem):", key="bip_codigo")

    if st.button("💾 Gravar Registro Único", type="primary"):
        if codigo_patrimonio.strip():
            sucesso = adicionar_e_salvar_sem_sobrescrever(
                codigo=codigo_patrimonio,
                patrimonio=tipo_equipamento,
                setor=setor_input,
                unidade=unidade_selecionada,
                fabricante=fabricante_input
            )
            if sucesso:
                st.success(f"Patrimônio `{codigo_patrimonio}` salvo com sucesso na unidade {unidade_selecionada}!")
            else:
                st.error("Erro ao salvar no Google Sheets.")
        else:
            st.warning("Insira ou bipe um código de patrimônio válido.")

# ------------------------------------------------------------------------------
# PÁGINA 2: CADASTRAMENTO POR SETOR (EM LOTE)
# ------------------------------------------------------------------------------
elif pagina == "2. Cadastramento por Setor (Lote)":
    st.subheader("📋 Cadastramento Completo por Setor")
    
    setor_lote = st.selectbox("Selecione o Setor para Preenchimento:", SETORES_PADRAO, key="setor_lote")
    
    st.markdown("---")
    st.markdown("##### Preencha os Patrimônios e Fabricantes do Setor:")
    
    dados_formulario = {}
    cols = st.columns(2)
    
    for idx, (nome_eq, (col_pat, col_fab)) in enumerate(EQUIPAMENTOS_OPCOES.items()):
        col_pos = cols[idx % 2]
        with col_pos:
            st.markdown(f"**{nome_eq}**")
            pat_val = st.text_input(f"Patrimônio ({nome_eq}):", key=f"pat_{col_pat}")
            fab_val = st.selectbox(f"Fabricante ({nome_eq}):", FABRICANTES_PADRAO, key=f"fab_{col_fab}")
            
            if pat_val.strip():
                dados_formulario[col_pat] = pat_val.strip()
                dados_formulario[col_fab] = fab_val if fab_val != "Outro" else ""

    st.markdown("---")
    if st.button("💾 Salvar Inventário do Setor", type="primary"):
        if dados_formulario:
            sucesso = adicionar_ou_atualizar_registro(unidade_selecionada, setor_lote, dados_formulario)
            if sucesso:
                st.success(f"Dados do setor `{setor_lote}` salvos com sucesso na aba {unidade_selecionada}!")
            else:
                st.error("Erro ao salvar no Google Sheets.")
        else:
            st.warning("Preencha ao menos um código de patrimônio.")

# ------------------------------------------------------------------------------
# PÁGINA 3: CONSULTA E GERENCIAMENTO DO INVENTÁRIO
# ------------------------------------------------------------------------------
elif pagina == "3. Consulta e Gerenciamento do Inventário":
    st.subheader("📊 Consulta e Exclusão de Inventário")
    
    df_inventario, origem = carregar_dados_excel(unidade_selecionada)
    st.caption(f"Fonte de Dados: **{origem}**")

    if not df_inventario.empty:
        st.dataframe(df_inventario, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### 🗑️ Gerenciamento e Exclusão")
        
        tab1, tab2 = st.tabs(["Excluir Patrimônio Específico", "Excluir Setor Completo"])
        
        with tab1:
            setores_existentes = ordenar_valores_unicos_alfabeticamente(df_inventario[COLUNA_CHAVE].unique().tolist())
            if setores_existentes:
                setor_exc = st.selectbox("Selecione o Setor:", setores_existentes, key="exc_pat_setor")
                coluna_exc = st.selectbox(
                    "Selecione o Tipo de Patrimônio a ser Removido:",
                    opcoes_tipo_patrimonio(),
                    key="exc_pat_col"
                )
                
                if st.button("❌ Remover Patrimônio Selecionado"):
                    col_real = EQUIPAMENTOS_OPCOES[coluna_exc][0]
                    if excluir_patrimonio(setor_exc, col_real, unidade_selecionada):
                        st.success(f"Patrimônio do equipamento `{coluna_exc}` removido com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao remover o patrimônio.")
        
        with tab2:
            setores_existentes_del = ordenar_valores_unicos_alfabeticamente(df_inventario[COLUNA_CHAVE].unique().tolist())
            if setores_existentes_del:
                setor_del = st.selectbox("Selecione o Setor Completo a Excluir:", setores_existentes_del, key="exc_setor_full")
                if st.button("🔥 Excluir Todo o Setor", type="primary"):
                    if excluir_setor(setor_del, unidade_selecionada):
                        st.success(f"Setor `{setor_del}` e todos os seus itens foram excluídos!")
                        st.rerun()
                    else:
                        st.error("Erro ao excluir o setor.")
    else:
        st.info(f"Nenhum registro encontrado para a unidade **{unidade_selecionada}**.")