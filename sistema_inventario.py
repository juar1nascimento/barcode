import os
import json
import re
import pandas as pd
import numpy as np
import streamlit as st
from typing import Optional, Tuple, List, Dict, Any
from html import escape
from urllib.parse import quote

from Tabela_de_dados_Inventario_7_2 import (
    ARQUIVO_EXCEL, COLUNA_CHAVE, COLUNAS_OBSOLETAS, COLUNAS_PADRAO, SETORES_PADRAO,
    LISTA_URS_PADRAO, LISTA_UBS_PADRAO, LISTA_ALMOXARIFADO_PADRAO, formatar_nome_patrimonio, formatar_nome_fabricante,
    carregar_dados_excel, salvar_no_excel, registrar_patrimonio, excluir_setor, excluir_patrimonio
)
from fotos_patrimonio import renderizar_fotos_patrimonio
from historico_movimentacoes import renderizar_historico_movimentacoes
from postgresql_persistencia import conectar as conectar_postgresql
from consultorio_contexto import selecionar_setor

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


def _renderizar_fotos_ultimo_patrimonio(unidade: str) -> None:
    """Exibe as fotografias do último patrimônio gravado nesta unidade."""
    patrimonio_id = st.session_state.get("ultimo_patrimonio_id")
    patrimonio_unidade = st.session_state.get("ultimo_patrimonio_unidade", "")
    if not patrimonio_id or patrimonio_unidade != unidade:
        return

    st.divider()
    renderizar_fotos_patrimonio(int(patrimonio_id))



def _url_publica_foto_site(bucket: str, path: str) -> str:
    """Monta a URL pública de uma fotografia no Supabase Storage."""
    sec = st.secrets.get("supabase") or {}
    base = str(sec.get("url") or "").strip().rstrip("/")
    if not base or not str(bucket or "").strip() or not str(path or "").strip():
        return ""
    return (
        f"{base}/storage/v1/object/public/"
        f"{quote(str(bucket).strip('/'))}/"
        f"{quote(str(path).lstrip('/'), safe='/')}"
    )


def _renderizar_tabela_site(df_atual: pd.DataFrame) -> None:
    """Renderiza cada patrimônio com suas fotos na mesma linha e visualização ampliada."""
    if df_atual is None or df_atual.empty:
        return

    df = df_atual.copy()
    numeros = [
        str(v).strip() for v in df.get("Nº de Patrimônio", pd.Series(dtype=str)).tolist()
        if str(v).strip() and str(v).strip().lower() not in {"nan", "none", "null", "<na>"}
    ]
    fotos_por_numero: Dict[str, List[str]] = {}
    erro_fotos = ""

    if numeros:
        conn = None
        try:
            conn = conectar_postgresql()
            if conn is None:
                raise RuntimeError("PostgreSQL indisponível.")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.numero_patrimonio, f.storage_bucket, f.storage_path
                    FROM public.patrimonios p
                    LEFT JOIN public.patrimonio_fotos f
                      ON f.patrimonio_id = p.id
                    WHERE p.numero_patrimonio = ANY(%s)
                    ORDER BY p.id, f.ordem, f.id
                    """,
                    (numeros,),
                )
                for numero, bucket, path in cur.fetchall():
                    chave = str(numero or "").strip()
                    if bucket and path:
                        url = _url_publica_foto_site(str(bucket), str(path))
                        if url:
                            fotos_por_numero.setdefault(chave, []).append(url)
        except Exception as exc:
            erro_fotos = str(exc).strip()[:240] or "Não foi possível carregar as fotos."
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    colunas = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Fotos"]
    linhas_html = []
    for indice_linha, (_, row) in enumerate(df.iterrows()):
        numero = str(row.get("Nº de Patrimônio", "") or "").strip()
        fotos = fotos_por_numero.get(numero, [])

        if fotos:
            miniaturas = []
            for i, url in enumerate(fotos[:10], start=1):
                safe_url = escape(url, quote=True)
                miniaturas.append(
                    f'<a href="#" class="foto-link" title="Ampliar foto {i}" '
                    f'onclick="abrirFoto({json.dumps(url)}); return false;">'
                    f'<img src="{safe_url}" alt="Foto {i} - {escape(numero)}" loading="lazy" '
                    f'width="72" height="72" class="foto-miniatura"></a>'
                )
            fotos_html = '<div class="photos">' + "".join(miniaturas) + "</div>"
        else:
            fotos_html = '<span style="color:#64748B;">Sem foto</span>'

        celulas = [
            row.get("Setor", ""),
            row.get("Tipo de Patrimônio", ""),
            numero,
            row.get("Fabricante", ""),
            row.get("Data Cadastro", ""),
            fotos_html,
        ]
        linhas_html.append(
            "<tr>" + "".join(
                f'<td>{valor if i == 5 else escape(str(valor or ""))}</td>'
                for i, valor in enumerate(celulas)
            ) + "</tr>"
        )

    aviso = (
        '<div style="margin:8px 0;padding:10px;border-radius:8px;background:#FFF7ED;'
        'color:#9A3412;border:1px solid #FED7AA;">⚠️ As fotos não puderam ser carregadas agora. '
        'Os dados do patrimônio continuam disponíveis.</div>'
        if erro_fotos else ""
    )
    html = f"""
    <style>
      body {{ margin:0; font-family:Inter,'Segoe UI',Arial,sans-serif; color:#1E293B; }}
      .table-wrap {{ width:100%; overflow-x:auto; }}
      table {{ width:100%; border-collapse:collapse; min-width:920px; }}
      th {{ background:#0F172A; color:#F8FAFC; padding:12px; font-size:12px;
            text-transform:uppercase; letter-spacing:.04em; text-align:center; }}
      td {{ padding:10px 12px; border-bottom:1px solid #E2E8F0; vertical-align:middle; }}
      tr:nth-child(even) {{ background:#F8FAFC; }}
      tr:hover {{ background:#EFF6FF; }}
      .photos {{ display:flex; gap:6px; align-items:center; flex-wrap:wrap; max-width:430px; }}
      .foto-link {{ display:inline-flex; cursor:zoom-in; border-radius:8px; }}
      .foto-miniatura {{ display:block; object-fit:cover; border-radius:8px;
                         border:1px solid #CBD5E1; transition:transform .15s, box-shadow .15s; }}
      .foto-link:hover .foto-miniatura {{ transform:scale(1.06); box-shadow:0 4px 14px rgba(15,23,42,.22); }}
      #foto-modal {{ display:none; position:fixed; inset:0; z-index:9999; background:rgba(15,23,42,.88);
                     align-items:center; justify-content:center; padding:24px; box-sizing:border-box; }}
      #foto-modal.aberta {{ display:flex; }}
      #foto-modal img {{ max-width:96vw; max-height:88vh; width:auto; height:auto; object-fit:contain;
                         border-radius:10px; box-shadow:0 12px 40px rgba(0,0,0,.45); }}
      #foto-modal .fechar {{ position:absolute; top:14px; right:18px; width:42px; height:42px;
                             border:0; border-radius:50%; background:#F8FAFC; color:#0F172A;
                             font-size:28px; line-height:42px; cursor:pointer; }}
      #foto-modal .legenda {{ position:absolute; bottom:12px; left:50%; transform:translateX(-50%);
                              color:#F8FAFC; background:rgba(15,23,42,.72); padding:7px 12px;
                              border-radius:8px; font-size:12px; }}
    </style>
    {aviso}
    <div class="table-wrap"><table>
      <thead><tr>{''.join(f'<th>{escape(col)}</th>' for col in colunas)}</tr></thead>
      <tbody>{''.join(linhas_html)}</tbody>
    </table></div>

    <div id="foto-modal" role="dialog" aria-modal="true" aria-label="Foto ampliada"
         onclick="fecharFoto(event)">
      <button type="button" class="fechar" aria-label="Fechar" onclick="fecharFoto(event)">×</button>
      <img id="foto-modal-imagem" src="" alt="Foto ampliada">
      <div id="foto-modal-legenda" class="legenda"></div>
    </div>

    <script>
      function abrirFoto(url) {{
        var modal = document.getElementById('foto-modal');
        var imagem = document.getElementById('foto-modal-imagem');
        var legenda = document.getElementById('foto-modal-legenda');
        imagem.src = url;
        legenda.textContent = 'Clique fora da imagem ou no × para fechar';
        modal.classList.add('aberta');
      }}
      function fecharFoto(event) {{
        if (event) {{
          event.stopPropagation();
          if (event.target && event.target.id === 'foto-modal-imagem') return;
        }}
        var modal = document.getElementById('foto-modal');
        var imagem = document.getElementById('foto-modal-imagem');
        imagem.src = '';
        modal.classList.remove('aberta');
      }}
      document.addEventListener('keydown', function(event) {{
        if (event.key === 'Escape') fecharFoto(event);
      }});
    </script>

    <div style="margin-top:8px;color:#64748B;font-size:12px;">
      As fotos aparecem na mesma linha do patrimônio bipado. Clique na miniatura para ampliar.
    </div>
    """
    st.components.v1.html(
        html,
        height=min(820, 210 + len(linhas_html) * 115),
        scrolling=True,
    )

# ==============================================================================
# VISÃO COMPUTACIONAL / LEITURA DE IMAGEM
# ==============================================================================
def processar_imagem(image_file: Any) -> Tuple[Optional[np.ndarray], List[Dict[str, str]]]:
    """Lê código de barras sem decodificar a foto original em resolução integral.

    Fotos de smartphones podem ter dezenas de megapixels. A rotina anterior
    mantinha simultaneamente bytes, BGR e RGB em resolução original, o que
    podia derrubar o processo Streamlit por excesso de memória.
    """
    try:
        import io
        import gc
        import cv2
        import zxingcpp
        from PIL import Image, ImageOps, UnidentifiedImageError

        MAX_INPUT_BYTES = 20 * 1024 * 1024
        MAX_SCAN_DIMENSION = 1600

        if hasattr(image_file, "getvalue"):
            raw = image_file.getvalue()
        else:
            raw = image_file.read()

        if not raw:
            return None, []
        if len(raw) > MAX_INPUT_BYTES:
            return None, []

        # PIL faz a primeira decodificação e reduz a imagem antes de criar
        # qualquer matriz OpenCV grande.
        with Image.open(io.BytesIO(raw)) as original:
            original = ImageOps.exif_transpose(original).convert("RGB")
            original.thumbnail((MAX_SCAN_DIMENSION, MAX_SCAN_DIMENSION), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            original.save(buffer, format="JPEG", quality=82, optimize=True)
            scan_bytes = buffer.getvalue()
            preview_width, preview_height = original.size

        del raw
        gc.collect()

        file_bytes = np.frombuffer(scan_bytes, dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        del file_bytes, scan_bytes
        if img is None:
            return None, []

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        del img
        barcodes = zxingcpp.read_barcodes(img_rgb)
        resultados = []

        for barcode in barcodes:
            codigo = str(getattr(barcode, "text", "") or "").strip()
            if not codigo:
                continue
            if hasattr(barcode, "position") and barcode.position:
                try:
                    pos = barcode.position
                    if hasattr(pos, "top_left"):
                        pts_list = [
                            [int(pos.top_left.x), int(pos.top_left.y)],
                            [int(pos.top_right.x), int(pos.top_right.y)],
                            [int(pos.bottom_right.x), int(pos.bottom_right.y)],
                            [int(pos.bottom_left.x), int(pos.bottom_left.y)],
                        ]
                    else:
                        pts_list = [
                            [int(getattr(pt, "x", pt[0])), int(getattr(pt, "y", pt[1]))]
                            for pt in pos
                        ]
                    if pts_list:
                        pts = np.array(pts_list, np.int32).reshape((-1, 1, 2))
                        cv2.polylines(img_rgb, [pts], True, (0, 255, 0), 3)
                except Exception:
                    pass
            resultados.append({
                "codigo": codigo,
                "tipo": str(barcode.format).replace("BarcodeFormat.", ""),
            })

        # Garante que a imagem devolvida à UI também permanece limitada.
        if img_rgb.shape[1] != preview_width or img_rgb.shape[0] != preview_height:
            img_rgb = cv2.resize(img_rgb, (preview_width, preview_height), interpolation=cv2.INTER_AREA)

        gc.collect()
        return img_rgb, resultados

    except (UnidentifiedImageError, OSError, ValueError):
        return None, []
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

        if st.button("🧾 Consultar Histórico de Movimentações", use_container_width=True, key="btn_historico_movimentacoes"):
            st.session_state.pagina_atual = "historico_movimentacoes"
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
        if st.session_state.pop("sheets_sync_pendente", False):
            st.info(
                "📌 Cadastro confirmado no PostgreSQL. A integração com o "
                "Google Sheets está pendente e não bloqueia a bipagem."
            )
        st.session_state.pop("sheets_sync_ultimo_erro", None)
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
        setor_selecionado = selecionar_setor(opcoes_setor)
        setor_input = setor_selecionado
        if setor_selecionado == "Outro Setor":
            setor_input = st.text_input("Nome do Setor:", placeholder="Digite o nome do setor...")
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
                        const codigo = String(decodedText || "").replace(/[\\r\\n\\t]/g, "").trim();
                        if (!codigo) return;
                        if (codigo === lastScannedCode && (agora - lastScannedTime) < 3000) return;
                        lastScannedCode = codigo; lastScannedTime = agora;
                        tocarBipNativo();
                        document.getElementById('scan-status').innerText = "✅ Lido: " + codigo + " (Salvando...)";
                        try {
                            const parentWin = window.parent;
                            const parentDoc = parentWin.document;
                            const inputEl =
                                parentDoc.querySelector('input[aria-label="Código Lido / Bipado:"]') ||
                                parentDoc.querySelector('input[placeholder*="Aguardando bipagem"]');
                            if (!inputEl) throw new Error("Campo de bipagem não encontrado");

                            const prototype = parentWin.HTMLInputElement.prototype;
                            const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
                            if (!descriptor || !descriptor.set) throw new Error("Setter do campo indisponível");

                            descriptor.set.call(inputEl, codigo);
                            inputEl.dispatchEvent(new parentWin.Event('input', { bubbles: true }));
                            inputEl.dispatchEvent(new parentWin.Event('change', { bubbles: true }));
                            inputEl.focus();

                            setTimeout(() => {
                                const form = inputEl.closest("form");
                                const submitBtn = form
                                    ? Array.from(form.querySelectorAll("button")).find(b => (b.innerText || "").includes("Registrar Manualmente"))
                                    : Array.from(parentDoc.querySelectorAll("button")).find(b => (b.innerText || "").includes("Registrar Manualmente"));
                                if (submitBtn) {
                                    submitBtn.click();
                                    document.getElementById('scan-status').innerText = "✅ Código " + codigo + " enviado para registro.";
                                } else {
                                    document.getElementById('scan-status').innerText = "⚠️ Botão de registro não encontrado. Use o botão manual.";
                                }
                            }, 250);
                        } catch (erro) {
                            document.getElementById('scan-status').innerText = "⚠️ Falha ao transferir o código. Use o campo do scanner USB.";
                            console.error("Falha no bridge do scanner:", erro);
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
                            st.session_state.mensagem_sucesso = f"✅ Código `{codigo_input.strip()}` registrado na coluna `{header_patrimonio}` no setor `{setor_input}` ({unidade})."
                            st.session_state.ultimo_patrimonio_numero = codigo_input.strip()
                            st.session_state.ultimo_patrimonio_unidade = unidade
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
                            st.session_state.ultimo_patrimonio_numero = codigos_registrados[-1]
                            st.session_state.ultimo_patrimonio_unidade = unidade
                        st.rerun()

    _renderizar_fotos_ultimo_patrimonio(unidade)

    st.divider()
    st.header(f"📊 Tabela de Patrimônios — {unidade}")

    try:
        df_atual, _ = carregar_dados_excel(unidade)
    except Exception:
        carregar_dados_excel.clear()
        df_atual, _ = carregar_dados_excel(unidade)

    if not df_atual.empty:
        _renderizar_tabela_site(df_atual)

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
    elif st.session_state.pagina_atual == "historico_movimentacoes":
        renderizar_historico_movimentacoes()
    else:
        renderizar_card_inventario()
