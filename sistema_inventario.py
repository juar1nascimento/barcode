import os
import re
import pandas as pd
import numpy as np
import streamlit as st
from typing import Optional, Tuple, List, Dict, Any

from Tabela_de_dados_Inventario_7_2 import (
    ARQUIVO_EXCEL, COLUNA_CHAVE, COLUNAS_OBSOLETAS, COLUNAS_PADRAO, SETORES_PADRAO,
    LISTA_URS_PADRAO, LISTA_UBS_PADRAO, LISTA_ALMOXARIFADO_PADRAO, formatar_nome_patrimonio, formatar_nome_fabricante,
    carregar_dados_excel, salvar_no_excel, registrar_patrimonio, atualizar_patrimonio, excluir_setor, excluir_patrimonio, auditar_sincronizacao_unidade, auditar_migracao_unidade, auditar_identificadores_unidade
)
import postgresql_persistencia

# ==============================================================================
# TIPOS DE PATRIMÔNIO - LISTA FECHADA E OBRIGATÓRIA
# ==============================================================================
TIPOS_PATRIMONIO_PERMITIDOS = (
    "CPU",
    "Monitores",
    "Teclado",
    "Mouse",
    "Imprenssoras",
    "Outros Dispositivos",
)


def opcoes_tipo_patrimonio() -> List[str]:
    """Retorna exclusivamente os seis tipos oficiais de patrimônio."""
    return list(TIPOS_PATRIMONIO_PERMITIDOS)


def validar_tipo_patrimonio(tipo: str) -> str:
    """Impede gravação de tipos antigos ou não autorizados."""
    tipo_limpo = re.sub(r"\s+", " ", str(tipo or "").strip())
    if tipo_limpo not in TIPOS_PATRIMONIO_PERMITIDOS:
        raise ValueError(
            f"Tipo de patrimônio inválido: {tipo_limpo!r}. "
            "Permitidos: " + ", ".join(TIPOS_PATRIMONIO_PERMITIDOS)
        )
    return tipo_limpo


# ==============================================================================
# LÓGICA DE CADASTRO COM SUPORTE A CABEÇALHOS ARTICULADOS DE FABRICANTE
# ==============================================================================
def adicionar_e_salvar_sem_sobrescrever(
    codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = ""
) -> bool:
    """Ponto único de entrada do cadastro da interface.

    A tela preserva seu layout e seus controles, mas toda validação,
    normalização, prevenção de duplicidade e persistência ficam no backend.
    """
    try:
        validar_tipo_patrimonio(patrimonio)
    except ValueError as e:
        st.error(str(e))
        return False
    return registrar_patrimonio(codigo, patrimonio, setor, unidade, fabricante)


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever

# ==============================================================================
# VISÃO COMPUTACIONAL / LEITURA DE IMAGEM
# ==============================================================================
def processar_imagem(image_file: Any) -> Tuple[Optional[np.ndarray], List[Dict[str, str]]]:
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
            resultados.append({"codigo": barcode.text, "tipo": str(barcode.format).replace("BarcodeFormat.", "")})
        return img_rgb, resultados
    except Exception:
        return None, []

# ==============================================================================
# CARD DE INVENTÁRIO E PORTAL DE NAVEGAÇÃO
# ==============================================================================
def _opcoes_unidade_por_categoria(
    categoria: str,
    urs_opcoes: List[str],
    ubs_opcoes: List[str],
    almox_opcoes: List[str],
) -> List[str]:
    """Retorna somente as unidades pertencentes à categoria escolhida."""
    if categoria == "URS":
        return urs_opcoes
    if categoria == "UBS":
        return ubs_opcoes
    return almox_opcoes


def renderizar_card_inventario(lista_urs: Optional[List[str]] = None, lista_ubs: Optional[List[str]] = None, lista_almoxarifado: Optional[List[str]] = None, *args, **kwargs) -> None:
    almox_opcoes = [u for u in (lista_almoxarifado if lista_almoxarifado is not None else LISTA_ALMOXARIFADO_PADRAO) if not str(u).startswith("Selecione")]
    urs_opcoes = [u for u in (lista_urs if lista_urs is not None else LISTA_URS_PADRAO) if not str(u).startswith("Selecione")]
    ubs_opcoes = [u for u in (lista_ubs if lista_ubs is not None else LISTA_UBS_PADRAO) if not str(u).startswith("Selecione")]

    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📦 Sistema de Inventários</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de gestão e leitura de códigos de barra por URS, UBS ou Almoxarifado Central SESA.</p>", unsafe_allow_html=True)

        categoria_unidade = st.radio(
            "Tipo de unidade:",
            ["URS", "UBS", "Almoxarifado"],
            horizontal=True,
            key="tipo_unidade_card_inventario",
        )
        opcoes_unidade = _opcoes_unidade_por_categoria(
            categoria_unidade,
            urs_opcoes,
            ubs_opcoes,
            almox_opcoes,
        )
        rotulos_categoria = {
            "URS": ("URS - Unidade Regional de Saúde", "Selecione uma URS..."),
            "UBS": ("UBS - Unidade Básica de Saúde", "Selecione uma UBS..."),
            "Almoxarifado": ("Almoxarifado Central SESA", "Selecione o Almoxarifado Central SESA..."),
        }
        rotulo, placeholder = rotulos_categoria[categoria_unidade]
        unidade_escolhida = st.selectbox(
            rotulo,
            opcoes_unidade,
            index=None,
            placeholder=placeholder,
            key="sel_unidade_card_inventario",
        )

        if st.button("📂 Abrir Inventário da Unidade", use_container_width=True, type="primary", key="btn_abrir_inv"):
            if not unidade_escolhida:
                st.warning("⚠️ Selecione uma unidade para continuar.")
            else:
                st.session_state.unidade_selecionada = unidade_escolhida
                st.session_state.pagina_atual = "inventario"
                st.rerun()


def renderizar_portal_principal(lista_urs: Optional[List[str]] = None, lista_ubs: Optional[List[str]] = None, lista_almoxarifado: Optional[List[str]] = None, *args, **kwargs) -> None:
    renderizar_card_inventario(lista_urs=lista_urs, lista_ubs=lista_ubs, lista_almoxarifado=lista_almoxarifado, *args, **kwargs)

# ==============================================================================
# PÁGINA EXCLUSIVA DE INVENTÁRIO POR UNIDADE (URS / UBS)
# ==============================================================================
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

    with st.expander("🔎 Auditoria PostgreSQL × Google Sheets", expanded=False):
        st.caption("Compara o PostgreSQL (fonte principal) com o Google Sheets (espelho) sem alterar dados.")
        if st.button("Executar auditoria desta unidade", key="btn_auditar_sync", use_container_width=True):
            with st.spinner("Comparando os registros..."):
                auditoria = auditar_sincronizacao_unidade(unidade)
            if auditoria.get("erro"):
                st.error(auditoria["erro"])
            else:
                total_dif = len(auditoria["somente_postgresql"]) + len(auditoria["somente_google"]) + len(auditoria["divergentes"])
                if total_dif == 0:
                    st.success(f"Sincronização conferida: {auditoria['postgresql']} registro(s) no PostgreSQL e {auditoria['google_sheets']} no Google Sheets, sem divergências.")
                else:
                    st.warning(f"Foram encontradas {total_dif} divergência(s). O PostgreSQL continua sendo a fonte principal.")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Só PostgreSQL", len(auditoria["somente_postgresql"]))
                    col2.metric("Só Google Sheets", len(auditoria["somente_google"]))
                    col3.metric("Campos divergentes", len(auditoria["divergentes"]))
                    if auditoria["somente_postgresql"]:
                        st.write("**Existem no PostgreSQL e não no Sheets:**")
                        st.dataframe(pd.DataFrame(auditoria["somente_postgresql"]), use_container_width=True, hide_index=True)
                    if auditoria["somente_google"]:
                        st.write("**Existem no Sheets e não no PostgreSQL:**")
                        st.dataframe(pd.DataFrame(auditoria["somente_google"]), use_container_width=True, hide_index=True)
                    if auditoria["divergentes"]:
                        st.write("**Mesmo patrimônio, dados diferentes:**")
                        st.json(auditoria["divergentes"])

    with st.expander("🧪 Pré-auditoria de migração PostgreSQL", expanded=False):
        st.caption("Analisa o Google Sheets legado contra o PostgreSQL. Esta etapa é somente leitura e não migra nem altera dados.")
        if st.button("Executar pré-auditoria de migração", key="btn_auditar_migracao", use_container_width=True):
            with st.spinner("Analisando registros legados..."):
                auditoria_mig = auditar_migracao_unidade(unidade)
            if auditoria_mig.get("erro"):
                st.error(auditoria_mig["erro"])
            else:
                cats = auditoria_mig["categorias"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Legado analisado", auditoria_mig["total_legacy"])
                c2.metric("Já no PostgreSQL", len(cats["ja_existentes_pg"]))
                c3.metric("Prontos para migração", len(cats["validos_para_migracao"]))
                c4, c5, c6 = st.columns(3)
                c4.metric("Duplicados na planilha", len(cats["duplicados_planilha"]))
                c5.metric("Inválidos", len(cats["invalidos"]))
                c6.metric("Divergentes do PostgreSQL", len(cats["divergentes_pg"]))
                st.caption(f"Fonte legada: {auditoria_mig['fonte']}. Nenhuma alteração foi realizada.")
                if cats["validos_para_migracao"]:
                    st.write("**Registros classificados como candidatos à migração:**")
                    st.dataframe(pd.DataFrame(cats["validos_para_migracao"]), use_container_width=True, hide_index=True)
                if cats["duplicados_planilha"]:
                    st.write("**Duplicidades encontradas na fonte legada:**")
                    st.dataframe(pd.DataFrame(cats["duplicados_planilha"]), use_container_width=True, hide_index=True)
                if cats["invalidos"]:
                    st.write("**Registros inválidos/incompletos:**")
                    st.dataframe(pd.DataFrame(cats["invalidos"]), use_container_width=True, hide_index=True)
                if cats["divergentes_pg"]:
                    st.write("**Registros que já existem no PostgreSQL, mas com dados divergentes:**")
                    st.dataframe(pd.DataFrame(cats["divergentes_pg"]), use_container_width=True, hide_index=True)

    with st.expander("🆔 Auditoria de identificadores — Patrimônio × Código de Barras", expanded=False):
        st.caption("Etapa somente leitura: verifica se o modelo atual está tratando o número de patrimônio e o código de barras como identificadores distintos. Nenhum dado é alterado.")
        if st.button("Executar auditoria de identificadores", key="btn_auditar_identificadores", use_container_width=True):
            with st.spinner("Analisando identificadores no PostgreSQL e no legado..."):
                auditoria_id = auditar_identificadores_unidade(unidade)
            if auditoria_id.get("erro"):
                st.error(auditoria_id["erro"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Patrimônios no PostgreSQL", auditoria_id["postgresql"])
                c2.metric("Sem código de barras", auditoria_id["sem_codigo_barras"])
                c3.metric("Patrimônio = código", auditoria_id["iguais"])
                c4, c5, c6 = st.columns(3)
                c4.metric("Códigos duplicados", auditoria_id["codigos_duplicados"])
                c5.metric("Números duplicados", auditoria_id["numeros_duplicados"])
                c6.metric("Campo legado separado", "SIM" if auditoria_id["legado_tem_codigo_barras"] else "NÃO")
                if auditoria_id["codigos_duplicados_detalhes"]:
                    st.write("**Códigos de barras duplicados no PostgreSQL:**")
                    st.dataframe(pd.DataFrame(auditoria_id["codigos_duplicados_detalhes"]), use_container_width=True, hide_index=True)
                st.info(auditoria_id["conclusao"])

    # IMPORTANTE: o menu de Setor é uma lista fechada e única para todas as UBS/URS.
    # Não é montado a partir dos dados existentes na planilha.
    opcoes_setor = [
        "Consultório",
        "Almoxarifado",
        "Farmacia",
        "Sala de Preparo",
        "Sala de Vacina",
        "Sala de curativo",
        "Gerencia",
        "Administração",
        "Odontologia",
        "Recepção",
        "Outro Setor",
    ]

    # IMPORTANTE: o menu de Tipo de patrimônio NÃO é montado a partir das colunas
    # existentes na planilha. Isso impede que opções antigas como Monitor,
    # Computador, Fabricante Monitor, Fabricante Computador etc. reapareçam.
    opcoes_patrimonio = opcoes_tipo_patrimonio()

    col_desc1, col_desc2, col_desc3, col_desc4 = st.columns([1, 1, 1, 1])
    with col_desc1:
        setor_selecionado = st.selectbox("Setor:", opcoes_setor, index=None, placeholder="Selecione um setor...")
        setor_input = ""
        if setor_selecionado == "Consultório":
            setor_input = "Consultório"
        elif setor_selecionado == "Outro Setor":
            setor_input = st.text_input("Nome do Setor:", placeholder="Digite o nome do setor...")
        elif setor_selecionado:
            setor_input = setor_selecionado
        st.session_state.saved_setor = setor_input

    with col_desc2:
        opcao_selecionada = st.selectbox(
            "Tipo de patrimônio:",
            opcoes_patrimonio,
            index=None,
            placeholder="Selecione o patrimônio...",
            key="tipo_patrimonio_oficial_v4"
        )

    with col_desc3:
        descricao_final = opcao_selecionada or ""
        st.session_state.saved_descricao = descricao_final

    with col_desc4:
        fabricante_input = ""
        if descricao_final:
            rotulo_fabricante = formatar_nome_fabricante(descricao_final)
            fabricante_input = st.text_input(f"{rotulo_fabricante}:", placeholder="Ex: Dell, HP, Samsung...")

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
                        const parentWin = window.parent;
              const parentDoc = parentWin.document;
              const inputEl = parentDoc.querySelector('input[placeholder*="Aguardando bipagem"]');
              if (!inputEl) {
                  document.getElementById('scan-status').innerText = "⚠️ Campo de cadastro não encontrado. Recarregue a página.";
                  return;
              }
              try {
                  const setter = Object.getOwnPropertyDescriptor(parentWin.HTMLInputElement.prototype, "value").set;
                  setter.call(inputEl, decodedText);
                  inputEl.dispatchEvent(new parentWin.Event('input', { bubbles: true }));
                  inputEl.dispatchEvent(new parentWin.Event('change', { bubbles: true }));
                  inputEl.focus();
                  document.getElementById('scan-status').innerText = "✅ Lido: " + decodedText + " (enviando...)";
                  setTimeout(() => {
                      const buttons = Array.from(parentDoc.querySelectorAll('button'));
                      const submitBtn = buttons.find(b => (b.innerText || '').includes('Registrar Manualmente'));
                      if (submitBtn) {
                          submitBtn.click();
                      } else {
                          document.getElementById('scan-status').innerText = "⚠️ Botão de registro não encontrado. Use o botão manual.";
                      }
                  }, 500);
              } catch (erro) {
                  document.getElementById('scan-status').innerText = "⚠️ Falha ao transferir o código para o cadastro. Use o botão manual.";
                  console.error('Falha no bridge do scanner:', erro);
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
                    codigo_input = st.text_input("Código Lido / Bipado:", autocomplete="off", placeholder="Aguardando bipagem...")
                    if st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True) and codigo_input.strip():
                        if adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input, unidade, fabricante_input.strip()):
                            if unidade.casefold() == "almoxarifado central sesa".casefold():
                                st.session_state.patrimonio_foto_pendente = codigo_input.strip()
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
                            if unidade.casefold() == "almoxarifado central sesa".casefold():
                                st.session_state.patrimonio_foto_pendente = codigos_registrados[0]
                            st.session_state.mensagem_sucesso = f"✅ {len(codigos_registrados)} código(s) registrado(s) com sucesso na coluna `{header_patrimonio}`!"
                        st.rerun()

    st.divider()
    # Foto do patrimônio: captura + upload automático no Almoxarifado Central SESA.
    # A captura já autoriza o fluxo de persistência: não existe mais botão
    # intermediário. A imagem é tratada no backend e gravada no Storage,
    # enquanto os metadados entram em patrimonio_fotos com a próxima ordem.
    if unidade.casefold() == "almoxarifado central sesa".casefold():
        numero_foto_pendente = st.session_state.get("patrimonio_foto_pendente")
        if numero_foto_pendente:
            st.markdown("### 📸 Fotos do patrimônio")
            st.caption(
                f"📷 Tire a foto de {numero_foto_pendente}. "
                "O envio será automático e cada nova foto receberá a próxima ordem."
            )
            st.session_state.setdefault("foto_contador", 0)

            foto_capturada = st.camera_input(
                "Tire a foto do patrimônio",
                key=f"camera_patrimonio_{numero_foto_pendente}_{st.session_state.foto_contador}",
                resolution="720p",
                help="Ao concluir a captura, o sistema comprime a imagem e inicia o upload automaticamente.",
            )

            if foto_capturada is not None:
                bruto_foto = foto_capturada.getvalue()
                hash_captura = __import__("hashlib").sha256(bruto_foto).hexdigest()
                chave_captura = f"{numero_foto_pendente}:{hash_captura}"

                if st.session_state.get("ultima_foto_captura_processada") != chave_captura:
                    st.session_state["ultima_foto_captura_processada"] = chave_captura
                    with st.spinner("📤 Tratando e enviando a foto automaticamente..."):
                        ok_foto, msg_foto = postgresql_persistencia.salvar_foto_patrimonio(
                            numero_patrimonio=numero_foto_pendente,
                            unidade=unidade,
                            serial=numero_foto_pendente,
                            image_file=foto_capturada,
                        )

                    if ok_foto:
                        st.session_state.foto_contador += 1
                        st.session_state["ultima_foto_upload_ok"] = msg_foto
                        st.rerun()
                    else:
                        st.session_state["ultima_foto_upload_erro"] = msg_foto

            if st.session_state.get("ultima_foto_upload_ok"):
                st.success(f"✅ {st.session_state.pop('ultima_foto_upload_ok')}")
            if st.session_state.get("ultima_foto_upload_erro"):
                st.error(
                    "❌ O upload automático não foi concluído: "
                    f"{st.session_state.pop('ultima_foto_upload_erro')}"
                )
                st.info("Tire uma nova foto para tentar novamente.")

            fotos_existentes, erro_fotos = postgresql_persistencia.listar_fotos_patrimonio(
                numero_foto_pendente, unidade
            )
            if erro_fotos:
                st.caption("ℹ️ A quantidade de fotos será exibida após a conexão com o PostgreSQL.")
            else:
                st.info(
                    f"📷 Fotos já armazenadas para este patrimônio: "
                    f"**{len(fotos_existentes or [])}**"
                )
                if fotos_existentes:
                    st.dataframe(
                        pd.DataFrame(fotos_existentes)[
                            ["ordem", "nome", "arquivo_nome", "tamanho_bytes", "largura", "altura"]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

    st.header(f"📊 Tabela de Patrimônios — {unidade}")

    try:
        df_atual, _ = carregar_dados_excel(unidade)
    except Exception:
        carregar_dados_excel.clear()
        df_atual, _ = carregar_dados_excel(unidade)

    if not df_atual.empty:
        # As fotos ficam no final da tabela, em colunas sequenciais:
        # Foto 1, Foto 2, ... Cada coluna representa a ordem gravada
        # em patrimonio_fotos. Novas fotos nunca sobrescrevem as anteriores.
        colunas_foto = []
        if unidade.casefold() == "almoxarifado central sesa".casefold():
            mapa_fotos, erro_mapa_fotos = postgresql_persistencia.listar_fotos_colunas_patrimonios(unidade)
            if erro_mapa_fotos:
                st.caption(
                    "ℹ️ As colunas de fotos serão exibidas após a conexão com o PostgreSQL: "
                    f"{erro_mapa_fotos}"
                )
            else:
                max_fotos = max((len(fotos) for fotos in mapa_fotos.values()), default=0)
                for ordem in range(1, max_fotos + 1):
                    coluna = f"📷 Foto {ordem}"
                    colunas_foto.append(coluna)
                    df_atual[coluna] = df_atual["Nº de Patrimônio"].map(
                        lambda valor, ordem=ordem: (
                            mapa_fotos.get(str(valor).strip().casefold(), [])[ordem - 1]
                            if len(mapa_fotos.get(str(valor).strip().casefold(), [])) >= ordem
                            else ""
                        )
                    )

        df_styled = df_atual.style.set_properties(**{
            'font-family': "'Inter', 'Segoe UI', -apple-system, sans-serif",
            'font-size': '13px',
            'border-bottom': '1px solid #E2E8F0',
            'padding': '11px 15px',
            'color': '#1E293B'
        }).set_table_styles([
            {'selector': 'thead th', 'props': [
                ('background', 'linear-gradient(135deg, #0F172A 0%, #1E293B 60%, #334155 100%)'),
                ('color', '#F8FAFC'),
                ('font-weight', '700'),
                ('font-size', '12px'),
                ('text-transform', 'uppercase'),
                ('letter-spacing', '0.06em'),
                ('padding', '14px 16px'),
                ('border-bottom', '2px solid #3B82F6'),
                ('text-align', 'center'),
                ('box-shadow', '0 2px 4px rgba(0,0,0,0.1)')
            ]},
            {'selector': 'tbody tr:nth-child(even)', 'props': [('background-color', '#F8FAFC')]},
            {'selector': 'tbody tr:hover', 'props': [('background-color', '#EFF6FF'), ('transition', 'background-color 0.2s ease-in-out')]},
            {'selector': 'td:first-child', 'props': [('font-weight', '700'), ('background-color', '#F1F5F9'), ('color', '#0F172A'), ('border-right', '2px solid #CBD5E1')]}
        ])

        if colunas_foto:
            st.dataframe(
                df_atual,
                column_config={
                    coluna: st.column_config.ImageColumn(
                        coluna,
                        help=f"Foto {indice} do patrimônio, armazenada na ordem {indice}.",
                        width="small",
                    )
                    for indice, coluna in enumerate(colunas_foto, start=1)
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(df_styled, use_container_width=True)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Recarregar Dados da Unidade", use_container_width=True):
                carregar_dados_excel.clear()
                st.rerun()
        with col_btn2:
            st.download_button(f"⬇️ Baixar Tabela ({unidade})", data=df_atual.to_csv(index=False).encode("utf-8"), file_name=f"Tabela_{unidade.replace(' ', '_')}.csv", mime="text/csv", use_container_width=True)

        # O gerenciador permanece aberto durante toda a sessão da página.
        # O st.expander não expõe evento de abertura/fechamento; manter o estado
        # verdadeiro evita que qualquer rerun causado por selectbox/botão feche
        # automaticamente o painel durante a operação de exclusão.
        st.session_state.setdefault("gerenciador_exclusao_aberto", True)
        st.session_state["gerenciador_exclusao_aberto"] = True
        st.session_state.setdefault("tipo_operacao_exclusao", "Excluir Patrimônio")
        st.session_state.setdefault("del_setor", None)
        st.session_state.setdefault("del_setor_patrimonio", None)
        st.session_state.setdefault("del_coluna_patrimonio", None)
        if st.session_state.pop("reset_del_setor", False):
            st.session_state.del_setor = None
        if st.session_state.pop("reset_del_coluna_patrimonio", False):
            st.session_state.del_coluna_patrimonio = None


        with st.expander(
            f"✏️ Gerenciador de Edição — Aba ({unidade})",
            expanded=False,
        ):
            df_edicao = df_atual.copy()
            numeros_edicao = sorted(
                dict.fromkeys(
                    str(v).strip()
                    for v in df_edicao["Nº de Patrimônio"].tolist()
                    if str(v).strip()
                ),
                key=str.casefold,
            )
            if not numeros_edicao:
                st.info("ℹ️ Não existem patrimônios cadastrados para edição nesta unidade.")
            else:
                numero_original_edicao = st.selectbox(
                    "Selecione o Nº de Patrimônio:",
                    numeros_edicao,
                    index=None,
                    placeholder="Selecione um patrimônio...",
                    key="editar_numero_original",
                )
                if numero_original_edicao:
                    linha_edicao = df_edicao[
                        df_edicao["Nº de Patrimônio"].map(str).str.strip().str.casefold()
                        == numero_original_edicao.strip().casefold()
                    ].iloc[0]

                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        novo_numero_edicao = st.text_input(
                            "Novo Nº de Patrimônio:",
                            value=str(linha_edicao["Nº de Patrimônio"]),
                            key="editar_novo_numero",
                        )
                        valor_tipo_edicao = str(linha_edicao["Tipo de Patrimônio"])
                        novo_tipo_edicao = st.selectbox(
                            "Tipo de Patrimônio:",
                            opcoes_patrimonio,
                            index=opcoes_patrimonio.index(valor_tipo_edicao) if valor_tipo_edicao in opcoes_patrimonio else None,
                            key="editar_tipo",
                        )
                    with col_e2:
                        novo_setor_edicao = st.text_input(
                            "Setor:",
                            value=str(linha_edicao["Setor"]),
                            key="editar_setor",
                        )
                        novo_fabricante_edicao = st.text_input(
                            "Fabricante:",
                            value=str(linha_edicao["Fabricante"]),
                            key="editar_fabricante",
                        )

                    if st.button(
                        "💾 Salvar alterações",
                        type="primary",
                        use_container_width=True,
                        key="btn_salvar_edicao",
                    ):
                        novo_numero = novo_numero_edicao.strip()
                        if not novo_numero:
                            st.error("Informe o novo número de patrimônio.")
                        else:
                            ok_edicao, msg_edicao = atualizar_patrimonio(
                                numero_patrimonio_original=numero_original_edicao,
                                codigo_barras=novo_numero,
                                tipo=novo_tipo_edicao or "",
                                setor=novo_setor_edicao,
                                unidade=unidade,
                                fabricante=novo_fabricante_edicao,
                                numero_patrimonio=novo_numero,
                            )
                            if ok_edicao:
                                st.session_state.mensagem_sucesso = f"✏️ {msg_edicao}"
                                carregar_dados_excel.clear()
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_edicao}")

        with st.expander(
            f"🗑️ Gerenciador de Exclusão — Aba ({unidade})",
            expanded=st.session_state.get("gerenciador_exclusao_aberto", False),
        ):
            lista_setores_existentes = sorted(
                dict.fromkeys(
                    str(s).strip()
                    for s in df_atual[COLUNA_CHAVE].tolist()
                    if str(s).strip()
                ),
                key=str.casefold,
            )

            st.caption("Selecione a operação. Após uma exclusão, o gerenciador permanece aberto e preserva o setor selecionado quando ele ainda existir.")
            tipo_operacao = st.radio(
                "Operação de exclusão:",
                ["Excluir Setor", "Excluir Patrimônio"],
                horizontal=True,
                key="tipo_operacao_exclusao",
            )

            if not lista_setores_existentes:
                st.info("ℹ️ Não existem setores cadastrados para exclusão nesta unidade.")
            elif tipo_operacao == "Excluir Setor":
                setor_para_excluir = st.selectbox(
                    "Selecione o Setor para apagar inteiramente:",
                    lista_setores_existentes,
                    index=None,
                    key="del_setor",
                    placeholder="Selecione um setor...",
                )
                if setor_para_excluir:
                    st.warning(f"⚠️ A exclusão removerá todas as informações do setor **{setor_para_excluir}** nesta unidade.")

                if setor_para_excluir and st.button(
                    f"🔥 Confirmar Exclusão do Setor '{setor_para_excluir}'",
                    type="primary",
                    use_container_width=True,
                    key="btn_excluir_setor",
                ):
                    sucesso = excluir_setor(setor_para_excluir, unidade)
                    carregar_dados_excel.clear()
                    if sucesso:
                        st.session_state.mensagem_sucesso = f"🗑️ Setor '{setor_para_excluir}' excluído com sucesso."
                        st.session_state.gerenciador_exclusao_aberto = True
                        st.session_state.reset_del_setor = True
                        st.session_state.del_setor_patrimonio = None
                        st.session_state.reset_del_coluna_patrimonio = True
                    else:
                        st.session_state.mensagem_sucesso = f"⚠️ Nenhum registro foi excluído para o setor '{setor_para_excluir}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                    st.rerun()

            else:
                setor_patrimonio_del = st.selectbox(
                    "Selecione o Setor:",
                    lista_setores_existentes,
                    index=None,
                    key="del_setor_patrimonio",
                    placeholder="Selecione um setor...",
                )

                colunas_com_dados, valores_map = [], {}
                if setor_patrimonio_del:
                    linha_setor_df = df_atual[
                        df_atual[COLUNA_CHAVE].astype(str).str.strip().str.casefold()
                        == str(setor_patrimonio_del).strip().casefold()
                    ]
                    if not linha_setor_df.empty:
                        for col in df_atual.columns:
                            if col == COLUNA_CHAVE or col in COLUNAS_OBSOLETAS or str(col).startswith("Fabricante "):
                                continue
                            val = str(linha_setor_df.iloc[0][col]).strip()
                            if val and val.lower() not in {"nan", "none", "null", "<na>"}:
                                colunas_com_dados.append(col)
                                valores_map[col] = val

                colunas_com_dados = sorted(colunas_com_dados, key=str.casefold)
                coluna_patrimonio_del = st.selectbox(
                    "Selecione o Patrimônio:",
                    options=colunas_com_dados,
                    index=None,
                    key="del_coluna_patrimonio",
                    placeholder="Selecione o patrimônio...",
                    format_func=lambda c: f"{c} (Código: {valores_map.get(c, '')})",
                ) if colunas_com_dados else None

                if setor_patrimonio_del and not colunas_com_dados:
                    st.info("ℹ️ O setor selecionado não possui patrimônio preenchido para exclusão.")
                elif coluna_patrimonio_del:
                    st.warning(
                        f"⚠️ Será removido o patrimônio **{coluna_patrimonio_del}** do setor **{setor_patrimonio_del}** e, quando existir, o fabricante correspondente."
                    )

                if coluna_patrimonio_del and setor_patrimonio_del and st.button(
                    f"🗑️ Confirmar Exclusão de '{coluna_patrimonio_del}'",
                    type="secondary",
                    use_container_width=True,
                    key="btn_excluir_patrimonio",
                ):
                    sucesso = excluir_patrimonio(setor_patrimonio_del, coluna_patrimonio_del, unidade)
                    carregar_dados_excel.clear()
                    if sucesso:
                        st.session_state.mensagem_sucesso = f"❌ Patrimônio '{coluna_patrimonio_del}' e seu fabricante foram excluídos do setor '{setor_patrimonio_del}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                        st.session_state.reset_del_coluna_patrimonio = True
                        st.session_state.del_setor_patrimonio = setor_patrimonio_del
                    else:
                        st.session_state.mensagem_sucesso = f"⚠️ Nenhum patrimônio foi excluído para o setor '{setor_patrimonio_del}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                    st.rerun()



if __name__ == "__main__":
    st.set_page_config(page_title="Portal GTI-SESA / Inventários", layout="wide")
    st.session_state.setdefault("pagina_atual", "portal")
    st.session_state.setdefault("unidade_selecionada", "")

    if st.session_state.pagina_atual in ["inventario", "inventario_unidade"] and st.session_state.unidade_selecionada:
        renderizar_sistema_inventario()
    else:
        renderizar_card_inventario()
