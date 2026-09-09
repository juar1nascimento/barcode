import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from Tabela_de_dados_Inventario_7_2 import (
    ARQUIVO_EXCEL,
    COLUNA_CHAVE,
    COLUNAS_PADRAO,
    LISTA_UBS_PADRAO,
    LISTA_URS_PADRAO,
    carregar_dados_excel,
    excluir_setor,
    formatar_nome_fabricante,
    formatar_nome_patrimonio,
    salvar_no_excel,
)
from inventario_regras import normalizar_fabricante, normalizar_setor, setores_menu, tipos_patrimonio_menu
from servicos.movimentacao import excluir_patrimonio_exato

TIPOS_PATRIMONIO_PERMITIDOS = tuple(tipos_patrimonio_menu())


def opcoes_tipo_patrimonio() -> List[str]:
    return list(tipos_patrimonio_menu())


def opcoes_setor() -> List[str]:
    return list(setores_menu())


def validar_tipo_patrimonio(tipo: str) -> str:
    tipo_limpo = re.sub(r"\s+", " ", str(tipo or "").strip())
    if tipo_limpo not in TIPOS_PATRIMONIO_PERMITIDOS:
        raise ValueError(f"Tipo de patrimônio inválido: {tipo_limpo!r}. Permitidos: " + ", ".join(TIPOS_PATRIMONIO_PERMITIDOS))
    return tipo_limpo


def adicionar_e_salvar_sem_sobrescrever(codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = "") -> bool:
    setor_limpo = normalizar_setor(str(setor or "").strip())
    codigo_limpo = str(codigo or "").strip()
    fabricante_limpo = normalizar_fabricante(str(fabricante or "").strip())
    try:
        patrimonio_validado = validar_tipo_patrimonio(patrimonio)
    except ValueError as e:
        st.error(str(e))
        return False
    patrimonio_cabecalho = formatar_nome_patrimonio(patrimonio_validado)
    coluna_fabricante = formatar_nome_fabricante(patrimonio_validado)
    if not setor_limpo or not codigo_limpo or not unidade:
        return False
    try:
        df_atual, _ = carregar_dados_excel(unidade)
        df = df_atual.copy()
    except Exception:
        df = pd.DataFrame(columns=[COLUNA_CHAVE] + list(TIPOS_PATRIMONIO_PERMITIDOS))
    if df.empty or COLUNA_CHAVE not in df.columns:
        df = pd.DataFrame(columns=[COLUNA_CHAVE])
    if patrimonio_cabecalho not in df.columns:
        df[patrimonio_cabecalho] = ""
    if coluna_fabricante not in df.columns:
        df[coluna_fabricante] = ""
    df = df.fillna("").astype(str)
    df[COLUNA_CHAVE] = df[COLUNA_CHAVE].map(normalizar_setor)
    mask_setor = df[COLUNA_CHAVE].str.strip().str.casefold() == setor_limpo.casefold()
    indices_setor = df[mask_setor].index
    linha_destino_idx = None
    for idx in indices_setor:
        if str(df.at[idx, patrimonio_cabecalho]).strip().casefold() in {"", "nan", "none", "<na>", "null"}:
            linha_destino_idx = idx
            break
    if linha_destino_idx is not None:
        df.at[linha_destino_idx, patrimonio_cabecalho] = codigo_limpo
        if fabricante_limpo:
            df.at[linha_destino_idx, coluna_fabricante] = fabricante_limpo
    else:
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[patrimonio_cabecalho] = codigo_limpo
        nova_linha[coluna_fabricante] = fabricante_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    sucesso = salvar_no_excel(df, unidade)
    carregar_dados_excel.clear()
    return sucesso


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever


def processar_imagem(image_file: Any) -> Tuple[Optional[np.ndarray], List[Dict[str, str]]]:
    try:
        import cv2
        import zxingcpp
        file_bytes = np.frombuffer(image_file.getvalue(), dtype=np.uint8) if hasattr(image_file, "getvalue") else np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return None, []
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        barcodes = zxingcpp.read_barcodes(img_rgb)
        return img_rgb, [{"codigo": barcode.text, "tipo": str(barcode.format).replace("BarcodeFormat.", "")} for barcode in barcodes]
    except Exception:
        return None, []


def renderizar_card_inventario(lista_urs: Optional[List[str]] = None, lista_ubs: Optional[List[str]] = None, *args, **kwargs) -> None:
    urs_opcoes = [u for u in (lista_urs if lista_urs is not None else LISTA_URS_PADRAO) if not str(u).startswith("Selecione")]
    ubs_opcoes = [u for u in (lista_ubs if lista_ubs is not None else LISTA_UBS_PADRAO) if not str(u).startswith("Selecione")]
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📦 Sistema de Inventários</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de gestão e leitura de códigos de barra por URS/UBS.</p>", unsafe_allow_html=True)
        urs_selecionada = st.selectbox("URS - Unidade Regional de Saúde", urs_opcoes, index=None, placeholder="Selecione uma URS...", key="sel_urs_card_inventario")
        ubs_selecionada = st.selectbox("UBS - Unidade Básica de Saúde", ubs_opcoes, index=None, placeholder="Selecione uma UBS...", key="sel_ubs_card_inventario")
        unidade_escolhida = urs_selecionada if urs_selecionada else (ubs_selecionada if ubs_selecionada else "")
        if st.button("📂 Abrir Inventário da Unidade", use_container_width=True, type="primary", key="btn_abrir_inv"):
            if not unidade_escolhida:
                st.warning("⚠️ Selecione uma URS ou UBS válida para continuar.")
            else:
                st.session_state.unidade_selecionada = unidade_escolhida
                st.session_state.pagina_atual = "inventario"
                st.rerun()


def renderizar_portal_principal(lista_urs: Optional[List[str]] = None, lista_ubs: Optional[List[str]] = None, *args, **kwargs) -> None:
    renderizar_card_inventario(lista_urs=lista_urs, lista_ubs=lista_ubs, *args, **kwargs)


def renderizar_sistema_inventario(*args, **kwargs) -> None:
    unidade = st.session_state.get("unidade_selecionada", "")
    if not unidade:
        st.session_state.pagina_atual = "portal"
        st.rerun()
    if st.session_state.get("mensagem_sucesso"):
        st.success(st.session_state.mensagem_sucesso)
        del st.session_state["mensagem_sucesso"]
    try:
        df_inicial, _ = carregar_dados_excel(unidade)
    except Exception:
        carregar_dados_excel.clear()
        df_inicial, _ = carregar_dados_excel(unidade)
    st.session_state.df_historico = df_inicial
    st.session_state.setdefault("saved_setor", "")
    st.session_state.setdefault("saved_descricao", "")
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
    opcoes_setor_menu = opcoes_setor()
    opcoes_patrimonio = opcoes_tipo_patrimonio()
    col_desc1, col_desc2, col_desc3, col_desc4 = st.columns([1, 1, 1, 1])
    with col_desc1:
        setor_selecionado = st.selectbox("Setor:", opcoes_setor_menu, index=None, placeholder="Selecione um setor...", key="setor_oficial_v5")
        setor_input = ""
        if setor_selecionado == "Outro Setor":
            setor_input = st.text_input("Nome do Setor:", placeholder="Digite o nome do setor...", key="outro_setor_nome_v5")
        elif setor_selecionado:
            setor_input = normalizar_setor(setor_selecionado)
        st.session_state.saved_setor = setor_input
    with col_desc2:
        opcao_selecionada = st.selectbox("Tipo de patrimônio:", opcoes_patrimonio, index=None, placeholder="Selecione o patrimônio...", key="tipo_patrimonio_oficial_v5")
    with col_desc3:
        descricao_final = opcao_selecionada or ""
        st.session_state.saved_descricao = descricao_final
    with col_desc4:
        fabricante_input = ""
        if descricao_final:
            rotulo_fabricante = formatar_nome_fabricante(descricao_final)
            fabricante_input = st.text_input(f"{rotulo_fabricante}:", placeholder="Ex: Dell, HP, Samsung...", key="fabricante_input_v5")
    st.divider()
    if not descricao_final or not setor_input.strip():
        st.warning("⚠️ Preencha o **Setor** e o **Tipo de patrimônio** para habilitar o leitor.")
    else:
        tab_unificada, tab_upload = st.tabs(["⚡ Câmera / Scanner USB", "📁 Upload de Imagem"])
        header_patrimonio = formatar_nome_patrimonio(descricao_final)
        header_fabricante = formatar_nome_fabricante(descricao_final)
        with tab_unificada:
            info_fab = f" | **{header_fabricante}:** `{fabricante_input.strip()}`" if fabricante_input.strip() else ""
            st.markdown(f"📍 **Unidade:** `{unidade}` | **Setor:** `{setor_input}` | **Cabeçalho:** `{header_patrimonio}`{info_fab}")
            col_camera, col_usb = st.columns([1.2, 1])
            with col_camera:
                st.caption("Aponte a câmera para o código de barras.")
                html_scanner = """
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                <style>#reader { width: 100% !important; max-width: 100% !important; border-radius: 12px; overflow: hidden; border: 2px solid #1E293B; background-color: #000; } #reader video { object-fit: cover !important; border-radius: 10px; } #scan-status { text-align: center; margin-top: 8px; font-weight: bold; color: #1E293B; font-family: sans-serif; font-size: 14px; }</style>
                <div class="scanner-wrapper"><div id="reader"></div><div id="scan-status">📷 Inicializando câmera...</div></div>
                <script>
                    let lastScannedCode = ""; let lastScannedTime = 0; let audioCtx = null;
                    function tocarBipNativo(){try{if(!audioCtx)audioCtx=new(window.AudioContext||window.webkitAudioContext)();if(audioCtx.state==='suspended')audioCtx.resume();const osc=audioCtx.createOscillator();const gain=audioCtx.createGain();osc.type='sine';osc.frequency.setValueAtTime(1500,audioCtx.currentTime);gain.gain.setValueAtTime(0.4,audioCtx.currentTime);osc.connect(gain);gain.connect(audioCtx.destination);osc.start();osc.stop(audioCtx.currentTime+0.12);}catch(e){}}
                    function onScanSuccess(decodedText){const agora=Date.now();if(decodedText===lastScannedCode&&(agora-lastScannedTime)<3000)return;lastScannedCode=decodedText;lastScannedTime=agora;tocarBipNativo();document.getElementById('scan-status').innerText='✅ Lido: '+decodedText+' (Salvando...)';const parentDoc=window.parent.document;const inputEl=parentDoc.querySelector('input[placeholder*="Aguardando bipagem"]');if(inputEl){const nativeSetter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;nativeSetter.call(inputEl,decodedText);inputEl.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(()=>{const buttons=Array.from(parentDoc.querySelectorAll('button'));const submitBtn=buttons.find(b=>b.innerText.includes('Registrar Manualmente'));if(submitBtn)submitBtn.click();},150);}}
                    const html5QrCode=new Html5Qrcode('reader');const config={fps:25,qrbox:{width:250,height:150}};html5QrCode.start({facingMode:'environment'},config,onScanSuccess).then(()=>{document.getElementById('scan-status').innerText='📷 Leitor pronto. Aponte para o código.';}).catch(()=>{html5QrCode.start({facingMode:'user'},config,onScanSuccess);});
                </script>
                """
                st.components.v1.html(html_scanner, height=390)
            with col_usb:
                st.markdown("##### 🔌 Entrada Manual / Scanner USB")
                with st.form(key="form_bipagem", clear_on_submit=True):
                    codigo_input = st.text_input("Código Lido / Bipado:", autocomplete="off", placeholder="Aguardando bipagem...")
                    if st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True) and codigo_input.strip():
                        if adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input, unidade, fabricante_input.strip()):
                            st.session_state.mensagem_sucesso = f"✅ Código `{codigo_input.strip()}` registrado na coluna `{header_patrimonio}` no setor `{setor_input}` ({unidade})."
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
                        codigos_registrados = [item["codigo"] for item in codigos_encontrados if adicionar_e_salvar(item["codigo"], descricao_final, setor_input, unidade, fabricante_input.strip())]
                        if codigos_registrados:
                            st.session_state.mensagem_sucesso = f"✅ {len(codigos_registrados)} código(s) registrado(s) com sucesso na coluna `{header_patrimonio}`!"
                        st.rerun()
    st.divider()
    st.header(f"📊 Tabela de Patrimônios — {unidade}")
    try:
        df_atual, _ = carregar_dados_excel(unidade)
    except Exception:
        carregar_dados_excel.clear()
        df_atual, _ = carregar_dados_excel(unidade)
    if not df_atual.empty:
        st.dataframe(df_atual, use_container_width=True)
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Recarregar Dados da Unidade", use_container_width=True):
                carregar_dados_excel.clear()
                st.rerun()
        with col_btn2:
            st.download_button(f"⬇️ Baixar Tabela ({unidade})", data=df_atual.to_csv(index=False).encode("utf-8"), file_name=f"Tabela_{unidade.replace(' ', '_')}.csv", mime="text/csv", use_container_width=True)
        st.session_state.setdefault("gerenciador_exclusao_aberto", True)
        st.session_state["gerenciador_exclusao_aberto"] = True
        st.session_state.setdefault("tipo_operacao_exclusao", "Excluir Patrimônio")
        st.session_state.setdefault("del_setor", None)
        st.session_state.setdefault("del_setor_patrimonio", None)
        st.session_state.setdefault("del_coluna_patrimonio", None)
        if st.session_state.pop("reset_del_setor", False): st.session_state.del_setor = None
        if st.session_state.pop("reset_del_coluna_patrimonio", False): st.session_state.del_coluna_patrimonio = None
        with st.expander(f"🗑️ Gerenciador de Exclusão — Aba ({unidade})", expanded=st.session_state.get("gerenciador_exclusao_aberto", False)):
            lista_setores_existentes = sorted(dict.fromkeys(normalizar_setor(s) for s in df_atual[COLUNA_CHAVE].tolist() if str(s).strip()), key=str.casefold)
            st.caption("Selecione a operação. A exclusão de patrimônio atua somente sobre o item escolhido; a exclusão de setor remove todos os registros daquele setor nesta unidade.")
            tipo_operacao = st.radio("Operação de exclusão:", ["Excluir Setor", "Excluir Patrimônio"], horizontal=True, key="tipo_operacao_exclusao")
            if not lista_setores_existentes:
                st.info("ℹ️ Não existem setores cadastrados para exclusão nesta unidade.")
            elif tipo_operacao == "Excluir Setor":
                setor_para_excluir = st.selectbox("Selecione o Setor para apagar inteiramente:", lista_setores_existentes, index=None, key="del_setor", placeholder="Selecione um setor...")
                if setor_para_excluir:
                    st.warning(f"⚠️ A exclusão removerá todas as informações do setor **{setor_para_excluir}** nesta unidade.")
                if setor_para_excluir and st.button(f"🔥 Confirmar Exclusão do Setor '{setor_para_excluir}'", type="primary", use_container_width=True, key="btn_excluir_setor"):
                    sucesso = excluir_setor(setor_para_excluir, unidade)
                    carregar_dados_excel.clear()
                    st.session_state.mensagem_sucesso = (f"🗑️ Setor '{setor_para_excluir}' excluído com sucesso." if sucesso else f"⚠️ Nenhum registro foi excluído para o setor '{setor_para_excluir}'.")
                    st.session_state.gerenciador_exclusao_aberto = True
                    st.session_state.reset_del_setor = True
                    st.session_state.del_setor_patrimonio = None
                    st.session_state.reset_del_coluna_patrimonio = True
                    st.rerun()
            else:
                setor_patrimonio_del = st.selectbox("Selecione o Setor:", lista_setores_existentes, index=None, key="del_setor_patrimonio", placeholder="Selecione um setor...")
                patrimonio_opcoes = []
                if setor_patrimonio_del:
                    mascara_setor = df_atual[COLUNA_CHAVE].astype(str).map(normalizar_setor).str.casefold() == normalizar_setor(setor_patrimonio_del).casefold()
                    linhas_setor = df_atual.loc[mascara_setor]
                    vistos = set()
                    for _, linha in linhas_setor.iterrows():
                        for tipo in opcoes_tipo_patrimonio():
                            if tipo not in df_atual.columns:
                                continue
                            valor = str(linha.get(tipo, "")).strip()
                            if valor and valor.casefold() not in {"nan", "none", "null", "<na>"}:
                                chave = (tipo.casefold(), valor.casefold())
                                if chave not in vistos:
                                    vistos.add(chave)
                                    patrimonio_opcoes.append((tipo, valor))
                    patrimonio_opcoes.sort(key=lambda item: (item[0].casefold(), item[1].casefold()))
                opcoes_exclusao = [f"{tipo} — {valor}" for tipo, valor in patrimonio_opcoes]
                escolha_patrimonio = st.selectbox("Selecione o Patrimônio:", options=opcoes_exclusao, index=None, key="del_coluna_patrimonio", placeholder="Selecione o patrimônio...") if opcoes_exclusao else None
                if setor_patrimonio_del and not opcoes_exclusao:
                    st.info("ℹ️ O setor selecionado não possui patrimônio preenchido para exclusão.")
                elif escolha_patrimonio:
                    tipo_escolhido, valor_escolhido = escolha_patrimonio.split(" — ", 1)
                    st.warning(f"⚠️ Será removido somente o patrimônio **{tipo_escolhido} = {valor_escolhido}** do setor **{setor_patrimonio_del}**. Outros patrimônios do setor serão preservados.")
                if escolha_patrimonio and setor_patrimonio_del and st.button(f"🗑️ Confirmar Exclusão de '{escolha_patrimonio}'", type="secondary", use_container_width=True, key="btn_excluir_patrimonio"):
                    tipo_escolhido, valor_escolhido = escolha_patrimonio.split(" — ", 1)
                    sucesso, detalhe = excluir_patrimonio_exato(setor_patrimonio_del, tipo_escolhido, valor_escolhido, unidade)
                    carregar_dados_excel.clear()
                    st.session_state.mensagem_sucesso = (f"❌ Patrimônio '{tipo_escolhido} = {valor_escolhido}' excluído do setor '{setor_patrimonio_del}'." if sucesso else f"⚠️ {detalhe}")
                    st.session_state.gerenciador_exclusao_aberto = True
                    st.session_state.reset_del_coluna_patrimonio = True
                    st.session_state.del_setor_patrimonio = setor_patrimonio_del
                    st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="Portal GTI-SESA / Inventários", layout="wide")
    st.session_state.setdefault("pagina_atual", "portal")
    st.session_state.setdefault("unidade_selecionada", "")
    if st.session_state.pagina_atual in ["inventario", "inventario_unidade"] and st.session_state.unidade_selecionada:
        renderizar_sistema_inventario()
    else:
        renderizar_card_inventario()