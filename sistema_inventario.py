import os
import pandas as pd
import numpy as np
import streamlit as st
from typing import Optional, Tuple, List, Dict, Any

# Importação dos módulos independentes e constantes (AGORA INCLUI ARQUIVO_EXCEL)
from Tabela_de_dados_Inventário import (
    ARQUIVO_EXCEL, COLUNA_CHAVE, COLUNAS_OBSOLETAS, COLUNAS_PADRAO, SETORES_PADRAO,
    LISTA_URS_PADRAO, LISTA_UBS_PADRAO,
    carregar_dados_excel, excluir_setor, excluir_patrimonio
)

# ==============================================================================
# SALVAMENTO SEGURO EM EXCEL
# ==============================================================================
def salvar_excel_seguro(df: pd.DataFrame, caminho_excel: str, sheet_name: str) -> bool:
    """
    Salva o DataFrame na aba especificada do Excel de forma segura,
    evitando erros de substituição de abas inexistentes.
    """
    try:
        if os.path.exists(caminho_excel):
            try:
                with pd.ExcelFile(caminho_excel, engine="openpyxl") as reader:
                    abas_existentes = reader.sheet_names
            except Exception:
                abas_existentes = []

            if sheet_name in abas_existentes:
                with pd.ExcelWriter(caminho_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                with pd.ExcelWriter(caminho_excel, engine="openpyxl", mode="a") as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            with pd.ExcelWriter(caminho_excel, engine="openpyxl", mode="w") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        return True
    except Exception as err:
        st.error(f"❌ Erro ao salvar na planilha Excel: {err}")
        print(f"[ERRO AO SALVAR PLANILHA]: {err}")
        return False


# ==============================================================================
# LÓGICA DE CADASTRO SEM SOBRESCREVER (MÚLTIPLOS PATRIMÔNIOS POR SETOR)
# ==============================================================================
def adicionar_e_salvar_sem_sobrescrever(codigo: str, patrimonio: str, setor: str, unidade: str) -> bool:
    """
    Garante que o cadastro do código não sobrescreva patrimônios existentes.
    Se o setor já possui aquele patrimônio preenchido, insere em uma nova linha.
    """
    setor_limpo = setor.strip()
    codigo_limpo = codigo.strip()
    patrimonio_limpo = patrimonio.strip()

    if not setor_limpo or not codigo_limpo or not patrimonio_limpo or not unidade:
        return False

    # 1. Carrega o DataFrame atual e o caminho da planilha (CORRIGIDO)
    try:
        df_atual, _ = carregar_dados_excel(unidade)
        df = df_atual.copy()
        caminho_excel = ARQUIVO_EXCEL
    except Exception as e:
        print(f"[ERRO CARREGAR EXCEL]: {e}")
        df = pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO)
        caminho_excel = ARQUIVO_EXCEL

    if df.empty or COLUNA_CHAVE not in df.columns:
        df = pd.DataFrame(columns=[COLUNA_CHAVE])

    # 2. Garante que a coluna do patrimônio existe no DataFrame
    if patrimonio_limpo not in df.columns:
        df[patrimonio_limpo] = ""

    # Normaliza valores para string
    df = df.fillna("").astype(str)

    # 3. Localiza linhas do setor onde a célula deste patrimônio esteja vaga
    mask_setor = df[COLUNA_CHAVE].str.strip().str.lower() == setor_limpo.lower()
    indices_setor = df[mask_setor].index

    linha_destino_idx = None
    for idx in indices_setor:
        val_celula = str(df.at[idx, patrimonio_limpo]).strip().lower()
        if val_celula in ["", "nan", "none", "<na>", "null"]:
            linha_destino_idx = idx
            break

    # 4. Preenche em linha com espaço vago ou adiciona nova linha ao setor
    if linha_destino_idx is not None:
        df.at[linha_destino_idx, patrimonio_limpo] = codigo_limpo
    else:
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[patrimonio_limpo] = codigo_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

    # 5. Salva no Excel de forma segura
    sucesso = salvar_excel_seguro(df, caminho_excel, unidade)

    # 6. Invalida cache do Streamlit para recarregar dados novos
    carregar_dados_excel.clear()
    
    return sucesso


# Substitui a função global para uso unificado no sistema
adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever


# ==============================================================================
# VISÃO COMPUTACIONAL / LEITURA DE IMAGEM
# ==============================================================================
def processar_imagem(image_file: Any) -> Tuple[Optional[np.ndarray], List[Dict[str, str]]]:
    """Processa o upload de imagem e extrai códigos de barra/QR codes com ZXing."""
    try:
        import cv2
        import zxingcpp

        if hasattr(image_file, "getvalue"):
            file_bytes = np.frombuffer(image_file.getvalue(), dtype=np.uint8)
        else:
            file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)

        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return None, []

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        barcodes = zxingcpp.read_barcodes(img_rgb)
        resultados = []

        for barcode in barcodes:
            if hasattr(barcode, "position") and barcode.position:
                try:
                    pos = barcode.position
                    if hasattr(pos, "top_left"):
                        pts_list = [
                            [int(pos.top_left.x), int(pos.top_left.y)],
                            [int(pos.top_right.x), int(pos.top_right.y)],
                            [int(pos.bottom_right.x), int(pos.bottom_right.y)],
                            [int(pos.bottom_left.x), int(pos.bottom_left.y)]
                        ]
                    else:
                        pts_list = [[int(getattr(pt, "x", pt[0])), int(getattr(pt, "y", pt[1]))] for pt in pos]

                    if pts_list:
                        pts = np.array(pts_list, np.int32).reshape((-1, 1, 2))
                        cv2.polylines(img_rgb, [pts], True, (0, 255, 0), 3)
                except Exception:
                    pass

            resultados.append({
                "codigo": barcode.text,
                "tipo": str(barcode.format).replace("BarcodeFormat.", "")
            })
        return img_rgb, resultados
    except Exception as err:
        print(f"[ERRO PROCESSAR IMAGEM]: {err}")
        return None, []


# ==============================================================================
# CARD DE INVENTÁRIO E PORTAL DE NAVEGAÇÃO
# ==============================================================================
def renderizar_card_inventario(
    lista_urs: Optional[List[str]] = None, 
    lista_ubs: Optional[List[str]] = None, 
    *args, 
    **kwargs
) -> None:
    """Renderiza exclusivamente o Card do Sistema de Inventários com chaves isoladas."""
    urs_opcoes = [u for u in (lista_urs if lista_urs is not None else LISTA_URS_PADRAO) if not str(u).startswith("Selecione")]
    ubs_opcoes = [u for u in (lista_ubs if lista_ubs is not None else LISTA_UBS_PADRAO) if not str(u).startswith("Selecione")]

    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📦 Sistema de Inventários</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de gestão e leitura de códigos de barra por URS/UBS.</p>", unsafe_allow_html=True)
        
        urs_selecionada = st.selectbox(
            "URS - Unidade Regional de Saúde", 
            urs_opcoes, 
            index=None,
            placeholder="Selecione uma URS...",
            key="sel_urs_card_inventario"
        )
        ubs_selecionada = st.selectbox(
            "UBS - Unidade Básica de Saúde", 
            ubs_opcoes, 
            index=None,
            placeholder="Selecione uma UBS...",
            key="sel_ubs_card_inventario"
        )

        unidade_escolhida = urs_selecionada if urs_selecionada else (ubs_selecionada if ubs_selecionada else "")

        if st.button("📂 Abrir Inventário da Unidade", use_container_width=True, type="primary", key="btn_abrir_inv"):
            if not unidade_escolhida:
                st.warning("⚠️ Selecione uma URS ou UBS válida para continuar.")
            else:
                st.session_state.unidade_selecionada = unidade_escolhida
                st.session_state.pagina_atual = "inventario"
                st.rerun()


def renderizar_portal_principal(
    lista_urs: Optional[List[str]] = None, 
    lista_ubs: Optional[List[str]] = None,
    *args, 
    **kwargs
) -> None:
    """Suporte para execução standalone ou redirecionamento para o card de inventário."""
    renderizar_card_inventario(lista_urs=lista_urs, lista_ubs=lista_ubs, *args, **kwargs)


# ==============================================================================
# PÁGINA EXCLUSIVA DE INVENTÁRIO POR UNIDADE (URS / UBS)
# ==============================================================================
def renderizar_sistema_inventario(*args, **kwargs) -> None:
    """Renderiza a página exclusiva de inventário com tabela e dados dedicados à URS/UBS."""
    unidade = st.session_state.get("unidade_selecionada", "")
    
    if not unidade:
        st.session_state.pagina_atual = "portal"
        st.rerun()

    # Exibe mensagem de confirmação persistente após rerun
    if st.session_state.get("mensagem_sucesso"):
        st.success(st.session_state.mensagem_sucesso)
        del st.session_state["mensagem_sucesso"]

    # Carrega dados atualizados da aba específica da URS/UBS
    try:
        df_inicial, _ = carregar_dados_excel(unidade)
    except Exception as e:
        print(f"[CACHE ERRO]: Falha ao recuperar cache para {unidade}: {e}")
        carregar_dados_excel.clear()
        df_inicial, _ = carregar_dados_excel(unidade)

    # Atualiza o DataFrame no estado da sessão
    st.session_state.df_historico = df_inicial
    st.session_state.setdefault("saved_setor", "")
    st.session_state.setdefault("saved_descricao", "")

    # Cabeçalho da página
    col_titulo, col_voltar = st.columns([3, 1])
    with col_titulo:
        st.title("📦 Sistema de Inventários - GTI-SESA")
        st.subheader(f"🏥 Tabela Exclusiva: **`{unidade}`**")
    with col_voltar:
        st.write("")
        if st.button("⬅️ Trocar de Unidade / Portal", use_container_width=True):
            st.session_state.unidade_selecionada = ""
            st.session_state.pagina_atual = "portal"
            st.rerun()

    st.divider()

    # Opções de setor limpas
    opcoes_setor = [s for s in (SETORES_PADRAO if isinstance(SETORES_PADRAO, (list, tuple)) else []) if not str(s).startswith("Selecione")]
    if "Consultório" not in opcoes_setor:
        opcoes_setor.append("Consultório")
    if "➕ Outro Setor" not in opcoes_setor:
        opcoes_setor.append("➕ Outro Setor")

    colunas_df_atuais = [col for col in st.session_state.df_historico.columns if col != COLUNA_CHAVE and col not in COLUNAS_OBSOLETAS]
    opcoes_patrimonio = list(dict.fromkeys(colunas_df_atuais + [c for c in COLUNAS_PADRAO if c != COLUNA_CHAVE])) + ["➕ Outros Patrimônios"]

    col_desc1, col_desc2, col_desc3 = st.columns(3)

    with col_desc1:
        setor_selecionado = st.selectbox(
            "Setor:", 
            opcoes_setor, 
            index=None, 
            placeholder="Selecione um setor...", 
            key="setor_selecionado_key"
        )

        setor_input = ""
        # Regra para 'Consultório' (Contador + Especialidade)
        if setor_selecionado == "Consultório":
            col_num, col_esp = st.columns([1, 1.5])
            with col_num:
                num_consultorio = st.number_input(
                    "Nº Consultório:",
                    min_value=1,
                    max_value=999,
                    value=1,
                    step=1,
                    key="num_consultorio_key"
                )
            with col_esp:
                especialidade = st.text_input(
                    "Especialidade:",
                    placeholder="Ex: Odontologia...",
                    key="especialidade_consultorio_key"
                )
            
            if especialidade.strip():
                setor_input = f"Consultório {num_consultorio} - {especialidade.strip()}"
            else:
                setor_input = f"Consultório {num_consultorio}"

        # Regra para '➕ Outro Setor'
        elif setor_selecionado == "➕ Outro Setor":
            setor_input = st.text_input(
                "Nome do Setor:",
                placeholder="Ex: Raio-X...",
                key="setor_custom_key"
            )
        elif setor_selecionado:
            setor_input = setor_selecionado

        st.session_state.saved_setor = setor_input

    with col_desc2:
        opcao_selecionada = st.selectbox(
            "Tipo de patrimônio:", 
            opcoes_patrimonio, 
            index=None, 
            placeholder="Selecione o patrimônio...", 
            key="opcao_selecionada_key"
        )

    with col_desc3:
        if opcao_selecionada == "➕ Outros Patrimônios":
            descricao_final = st.text_input(
                "Nome do Novo Patrimônio:", 
                placeholder="Ex: Servidor", 
                key="descricao_nova_key"
            )
        elif opcao_selecionada:
            descricao_final = opcao_selecionada
        else:
            descricao_final = ""

        st.session_state.saved_descricao = descricao_final

    st.divider()

    if not descricao_final or not setor_input.strip():
        st.warning("⚠️ Preencha o **Setor** e o **Tipo de patrimônio** para habilitar o leitor.")
    else:
        tab_unificada, tab_upload = st.tabs(["⚡ Câmera / Scanner USB", "📁 Upload de Imagem"])
        
        with tab_unificada:
            st.markdown(f"📍 **Unidade:** `{unidade}` | **Setor:** `{setor_input}` | **Patrimônio:** `{descricao_final}`")
            col_camera, col_usb = st.columns([1.2, 1])

            with col_camera:
                st.caption("Aponte a câmera para o código de barras.")
                html_scanner = """
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                <style>
                    #reader { width: 100% !important; max-width: 100% !important; border-radius: 12px; overflow: hidden; border: 2px solid #1E293B; background-color: #000; }
                    #reader video { object-fit: cover !important; border-radius: 10px; }
                    #scan-status { text-align: center; margin-top: 8px; font-weight: bold; color: #1E293B; font-family: sans-serif; font-size: 14px; }
                </style>
                <div class="scanner-wrapper">
                    <div id="reader"></div>
                    <div id="scan-status">📷 Inicializando câmera...</div>
                </div>
                <script>
                    let lastScannedCode = ""; let lastScannedTime = 0; let audioCtx = null;
                    function tocarBipNativo() {
                        try {
                            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                            if (audioCtx.state === 'suspended') audioCtx.resume();
                            const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
                            osc.type = 'sine'; osc.frequency.setValueAtTime(1500, audioCtx.currentTime);
                            gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
                            osc.connect(gain); gain.connect(audioCtx.destination);
                            osc.start(); osc.stop(audioCtx.currentTime + 0.12);
                        } catch(e) {}
                    }
                    function onScanSuccess(decodedText) {
                        const agora = Date.now();
                        if (decodedText === lastScannedCode && (agora - lastScannedTime) < 3000) return;
                        lastScannedCode = decodedText; lastScannedTime = agora;
                        tocarBipNativo();
                        document.getElementById('scan-status').innerText = "✅ Lido: " + decodedText + " (Salvando...)";
                        const parentDoc = window.parent.document;
                        const inputEl = parentDoc.querySelector('input[placeholder*="Aguardando bipagem"]');
                        if (inputEl) {
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            nativeSetter.call(inputEl, decodedText);
                            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                            setTimeout(() => {
                                const buttons = Array.from(parentDoc.querySelectorAll('button'));
                                const submitBtn = buttons.find(b => b.innerText.includes('Registrar Manualmente'));
                                if (submitBtn) submitBtn.click();
                            }, 150);
                        }
                    }
                    const html5QrCode = new Html5Qrcode("reader");
                    const config = { fps: 25, qrbox: { width: 250, height: 150 } };
                    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
                    .then(() => { document.getElementById('scan-status').innerText = "📷 Leitor pronto. Aponte para o código."; })
                    .catch(() => { html5QrCode.start({ facingMode: "user" }, config, onScanSuccess); });
                </script>
                """
                st.components.v1.html(html_scanner, height=390)

            with col_usb:
                st.markdown("##### 🔌 Entrada Manual / Scanner USB")
                with st.form(key="form_bipagem", clear_on_submit=True):
                    codigo_input = st.text_input("Código Lido / Bipado:", autocomplete="off", placeholder="Aguardando bipagem...", key="input_codigo_bip")
                    if st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True) and codigo_input.strip():
                        salvou = adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input, unidade)
                        if salvou:
                            st.session_state.mensagem_sucesso = f"✅ Código `{codigo_input.strip()}` registrado com sucesso no setor `{setor_input}` ({unidade})."
                        st.rerun()

        with tab_upload:
            uploaded_file = st.file_uploader("Envie uma imagem do código de barras", type=["jpg", "png", "jpeg"])
            if uploaded_file is not None:
                img_processada, codigos_encontrados = processar_imagem(uploaded_file)
                col_img1, col_img2 = st.columns(2)
                with col_img1:
                    if img_processada is not None:
                        st.image(img_processada, caption="Imagem Analisada", use_container_width=True)
                with col_img2:
                    if codigos_encontrados:
                        codigos_registrados = []
                        for item in codigos_encontrados:
                            if adicionar_e_salvar(item["codigo"], descricao_final, setor_input, unidade):
                                codigos_registrados.append(item["codigo"])
                        
                        if codigos_registrados:
                            st.session_state.mensagem_sucesso = f"✅ {len(codigos_registrados)} código(s) registrado(s) com sucesso!"
                        st.rerun()

    st.divider()
    st.header(f"📊 Tabela de Patrimônios — {unidade}")
    
    try:
        df_atual, _ = carregar_dados_excel(unidade)
    except Exception:
        carregar_dados_excel.clear()
        df_atual, _ = carregar_dados_excel(unidade)

    if not df_atual.empty:
        df_styled = df_atual.style.set_properties(**{'font-family': 'Segoe UI, sans-serif', 'font-size': '14px'}).set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#1E293B'), ('color', '#FFFFFF'), ('font-weight', 'bold'), ('text-align', 'center')]},
            {'selector': 'td:first-child', 'props': [('font-weight', 'bold'), ('background-color', '#F1F5F9')]}
        ])
        st.dataframe(df_styled, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Recarregar Dados da Unidade", use_container_width=True):
                carregar_dados_excel.clear()
                st.rerun()
        with col_btn2:
            nome_arquivo_csv = f"Tabela_{unidade.replace(' ', '_')}.csv"
            st.download_button(f"⬇️ Baixar Tabela ({unidade})", data=df_atual.to_csv(index=False).encode("utf-8"), file_name=nome_arquivo_csv, mime="text/csv", use_container_width=True)

        with st.expander(f"🗑️ Gerenciador de Exclusão — Aba ({unidade})", expanded=False):
            lista_setores_existentes = list(dict.fromkeys([s for s in df_atual[COLUNA_CHAVE].tolist() if str(s).strip()]))
            tab_excluir_setor, tab_excluir_patrimonio = st.tabs(["🗑️ Excluir Setor", "❌ Excluir Patrimônio"])

            with tab_excluir_setor:
                if lista_setores_existentes:
                    setor_para_excluir = st.selectbox(
                        "Selecione o Setor para apagar inteiramente:", 
                        lista_setores_existentes, 
                        index=None,
                        placeholder="Selecione um setor para apagar...",
                        key="sb_excluir_setor"
                    )
                    if setor_para_excluir and st.button(f"🔥 Confirmar Exclusão do Setor '{setor_para_excluir}'", type="primary", key="btn_del_setor"):
                        excluir_setor(setor_para_excluir, unidade)
                        carregar_dados_excel.clear()
                        st.session_state.mensagem_sucesso = f"🗑️ Setor '{setor_para_excluir}' excluído com sucesso."
                        st.rerun()

            with tab_excluir_patrimonio:
                if lista_setores_existentes:
                    c_del1, c_del2 = st.columns(2)
                    with c_del1:
                        setor_patrimonio_del = st.selectbox(
                            "Selecione o Setor:", 
                            lista_setores_existentes, 
                            index=None,
                            placeholder="Selecione um setor...",
                            key="sb_setor_del_patrimonio"
                        )
                    
                    colunas_com_dados, valores_map = [], {}
                    if setor_patrimonio_del:
                        linha_setor_df = df_atual[df_atual[COLUNA_CHAVE].str.strip().str.lower().eq(setor_patrimonio_del.strip().lower())]
                        if not linha_setor_df.empty:
                            for col in df_atual.columns:
                                if col != COLUNA_CHAVE and col not in COLUNAS_OBSOLETAS:
                                    val = str(linha_setor_df.iloc[0][col]).strip()
                                    if val and val.lower() not in ["", "nan", "none", "null", "<na>"]:
                                        colunas_com_dados.append(col)
                                        valores_map[col] = val

                    with c_del2:
                        coluna_patrimonio_del = st.selectbox(
                            "Selecione o Tipo de Patrimônio:", 
                            options=colunas_com_dados, 
                            index=None,
                            placeholder="Selecione o patrimônio...",
                            format_func=lambda c: f"{c} (Código: {valores_map.get(c, '')})", 
                            key=f"sb_coluna_del_{setor_patrimonio_del}"
                        ) if colunas_com_dados else None
                    
                    if coluna_patrimonio_del and setor_patrimonio_del and st.button(f"🗑️ Apagar '{coluna_patrimonio_del}'", type="secondary", key=f"btn_del_patrimonio_{setor_patrimonio_del}"):
                        excluir_patrimonio(setor_patrimonio_del, coluna_patrimonio_del, unidade)
                        carregar_dados_excel.clear()
                        st.session_state.mensagem_sucesso = f"❌ Patrimônio '{coluna_patrimonio_del}' excluído do setor '{setor_patrimonio_del}'."
                        st.rerun()


# ==============================================================================
# PONTO DE ENTRADA DO APLICATIVO E ROTEAMENTO
# ==============================================================================
if __name__ == "__main__":
    st.set_page_config(page_title="Portal GTI-SESA / Inventários", layout="wide")
    
    st.session_state.setdefault("pagina_atual", "portal")
    st.session_state.setdefault("unidade_selecionada", "")

    if st.session_state.pagina_atual in ["inventario", "inventario_unidade"] and st.session_state.unidade_selecionada:
        renderizar_sistema_inventario()
    else:
        renderizar_card_inventario()