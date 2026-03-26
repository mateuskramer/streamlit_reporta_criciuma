import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
import uuid
import requests
import time

from ia.gpt    import classificar_gpt
from ia.gemini import classificar_gemini
from ia.yolo   import detectar_buraco_yolo, classe_yolo
from auth.login import (
    inicializar_sessao, esta_logado, e_admin,
    tela_login, sidebar_usuario
)

# ==============================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================
st.set_page_config(
    page_title="Reporta Criciúma",
    page_icon="🏙️",
    layout="wide"
)

# ==============================================================
# CONEXÃO COM SUPABASE
# ==============================================================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase()

# ==============================================================
# SESSÃO E LOGIN
# ==============================================================
inicializar_sessao()

if not esta_logado():
    tela_login(supabase)
    st.stop()

# ==============================================================
# GEOCODIFICAÇÃO
# ==============================================================
CRICIUMIA_BBOX = (-28.75, -28.60, -49.45, -49.28)
CRICIUMIA_LAT  = -28.6775
CRICIUMIA_LON  = -49.3700

@st.cache_data(show_spinner=False, ttl=86400)
def geocodificar(endereco: str):
    try:
        api_key = st.secrets["google"]["maps_api_key"]
    except Exception:
        return None, None
    try:
        params = {
            "address":    f"{endereco}, Criciúma, SC, Brasil",
            "key":        api_key,
            "language":   "pt-BR",
            "region":     "BR",
            "components": "country:BR|administrative_area:SC",
        }
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params, timeout=10,
        )
        data = r.json()
        status = data.get("status")
        if status != "OK" or not data.get("results"):
            st.error(f"🗺️ Google Maps: status={status}")
            return None, None
        loc = data["results"][0]["geometry"]["location"]
        lat, lon = loc["lat"], loc["lng"]
        lat_min, lat_max, lon_min, lon_max = CRICIUMIA_BBOX
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return lat, lon
        st.warning(f"🗺️ Coordenadas fora de Criciúma: {lat}, {lon}")
        return None, None
    except Exception as e:
        st.error(f"🗺️ Exceção: {str(e)}")
        return None, None

# ==============================================================
# RUAS / BAIRROS
# ==============================================================
RUAS_FALLBACK = sorted([
    "Rua Cel. Pedro Benedet", "Rua Henrique Lage", "Rua Gen. Osvaldo Pinto da Veiga",
    "Avenida Centenário", "Avenida Universitária", "Rua Coronel Marcos Rovaris",
    "Rua Conselheiro João Zanette", "Rua Dom Joaquim", "Rua XV de Novembro",
    "Rua Marechal Deodoro", "Rua Felipe Schmidt", "Rua Lauro Müller",
    "Rua Santos Dumont", "Rua Sete de Setembro", "Rua Florianópolis",
    "Rua São Paulo", "Rua Curitiba", "Rua Rio de Janeiro",
    "Rua Porto Alegre", "Rua Belo Horizonte", "Avenida Santos Dumont",
    "Rua Joinville", "Rua Blumenau", "Rua Chapecó",
    "Rua Itajaí", "Rua Lages", "Rua Tubarão",
    "Rua Araranguá", "Rua Içara", "Rua Siderópolis",
    "Rua Urussanga", "Rua Nova Veneza", "Rua Cocal do Sul",
    "Rua Morro da Fumaça", "Rua Forquilhinha", "Rua Treviso",
    "Avenida Álvaro Catão", "Avenida Luiz Gualberto",
    "Rua Anita Garibaldi", "Rua Pedro II", "Rua Duque de Caxias",
    "Rua Visconde de Ouro Preto", "Rua Barão do Rio Branco",
    "Rua Tiradentes", "Rua Benjamin Constant",
])

BAIRROS_FALLBACK = sorted([
    "Centro", "Comerciário", "Próspera", "Rio Maina", "Santa Augusta",
    "São Luís", "Michel", "Pinheirinho", "Içara", "Quarta Linha",
    "Boa Vista", "Universitário", "Líder", "Mina Brasil", "Operária Nova",
    "Santa Bárbara", "Cruzeiro", "São Sebastião", "Jardim Angélica",
    "Ana Maria", "Ceará", "São Cristóvão", "Presidente Médici",
    "Vila Manaus", "Paraíso", "Metropol", "Santa Luzia",
    "São Francisco", "Tereza Cristina", "Jardim Maristela",
])

@st.cache_data(show_spinner=False, ttl=86400)
def carregar_todas_ruas_e_bairros():
    import urllib.parse
    termos = [
        "rua", "avenida", "travessa", "estrada", "rodovia",
        "alameda", "linha", "servidão", "vila", "beco",
        "largo", "praça", "loteamento", "parque"
    ]
    ruas_set, bairros_set = set(), set()
    rua_p_bairro, bairro_p_rua = {}, {}
    for termo in termos:
        try:
            url = (
                f"https://viacep.com.br/ws/SC/Crici%C3%BAma/"
                f"{urllib.parse.quote(termo)}/json/"
            )
            r = requests.get(url, timeout=10)
            if r.status_code != 200: continue
            data = r.json()
            if not isinstance(data, list): continue
            for item in data:
                logradouro = item.get("logradouro", "").strip()
                bairro     = item.get("bairro", "").strip()
                if logradouro: ruas_set.add(logradouro)
                if bairro:     bairros_set.add(bairro)
                if logradouro and bairro:
                    rua_p_bairro.setdefault(logradouro, set()).add(bairro)
                    bairro_p_rua.setdefault(bairro, set()).add(logradouro)
            time.sleep(0.1)
        except Exception:
            continue
    ruas_set    |= set(RUAS_FALLBACK)
    bairros_set |= set(BAIRROS_FALLBACK)
    return (
        sorted(ruas_set), sorted(bairros_set),
        {k: sorted(v) for k, v in rua_p_bairro.items()},
        {k: sorted(v) for k, v in bairro_p_rua.items()},
    )

CATEGORIAS_SUGERIDAS = ["Buraco", "Lixo", "Barulho", "Lâmpada Apagada", "Outro"]

# ==============================================================
# SIDEBAR
# ==============================================================
st.sidebar.image("https://img.icons8.com/fluency/96/city-buildings.png", width=80)
st.sidebar.title("Reporta Criciúma")
st.sidebar.markdown("---")

# Info do usuário + logout
sidebar_usuario(supabase)
st.sidebar.markdown("---")

# Navegação baseada no role
if e_admin():
    pagina = st.sidebar.radio(
        "Painel Admin",
        ["📍 Mapa", "📋 Demandas", "📊 Análise"]
    )
else:
    pagina = st.sidebar.radio(
        "Navegação",
        ["🆕 Nova Solicitação", "📋 Minhas Solicitações", "📊 Dashboard"]
    )

st.sidebar.markdown("---")
st.sidebar.caption("Reporta Criciúma v1.6 — Criciúma, SC")

# ██████████████████████████████████████████████████████████████
#  CIDADÃO — NOVA SOLICITAÇÃO
# ██████████████████████████████████████████████████████████████

if not e_admin() and pagina == "🆕 Nova Solicitação":
    st.header("📍 Reportar Problema")
    st.write("Descreva o problema e informe o local. Nossa equipe cuida do resto!")

    defaults = {
        "rua_sel": "", "numero": "", "bairro_sel": "",
        "descricao": "", "coord_lat": None, "coord_lon": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    with st.spinner("🔄 Carregando logradouros de Criciúma..."):
        todas_ruas, todos_bairros, rua_p_bairro, bairro_p_rua = carregar_todas_ruas_e_bairros()

    st.subheader("📎 Foto, Vídeo ou Áudio (opcional)")
    aba_upload, aba_camera = st.tabs(["📁 Fazer upload", "📷 Tirar foto agora"])

    arquivo = None
    with aba_upload:
        arquivo_upload = st.file_uploader(
            "Envie uma foto, vídeo ou áudio do problema",
            type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "avi", "mp3", "wav", "ogg"],
            label_visibility="collapsed"
        )
        if arquivo_upload is not None:
            arquivo = arquivo_upload
            tipo = arquivo.type
            if tipo.startswith("image/"):   st.image(arquivo, use_column_width=True); arquivo.seek(0)
            elif tipo.startswith("video/"): st.video(arquivo); arquivo.seek(0)
            elif tipo.startswith("audio/"): st.audio(arquivo); arquivo.seek(0)

    with aba_camera:
        foto_camera = st.camera_input("Tire uma foto do problema")
        if foto_camera is not None:
            arquivo = foto_camera
            st.image(foto_camera, use_column_width=True)

    st.markdown("---")
    st.subheader("📌 Localização do Problema")

    bairro_ativo = st.session_state.bairro_sel
    rua_ativa    = st.session_state.rua_sel

    if bairro_ativo and bairro_ativo in bairro_p_rua:
        ruas_disponiveis = [""] + sorted(bairro_p_rua[bairro_ativo])
        hint_rua = f"Mostrando ruas do bairro {bairro_ativo}."
    else:
        ruas_disponiveis = [""] + todas_ruas
        hint_rua = f"{len(todas_ruas)} logradouros disponíveis."

    if rua_ativa and rua_ativa in rua_p_bairro:
        bairros_disponiveis = [""] + sorted(rua_p_bairro[rua_ativa])
        hint_bairro = "Bairro(s) compatível(is) com a rua selecionada."
    else:
        bairros_disponiveis = [""] + todos_bairros
        hint_bairro = f"{len(todos_bairros)} bairros disponíveis."

    if rua_ativa and rua_ativa not in ruas_disponiveis:
        ruas_disponiveis = ["", rua_ativa] + ruas_disponiveis[1:]
    if bairro_ativo and bairro_ativo not in bairros_disponiveis:
        bairros_disponiveis = ["", bairro_ativo] + bairros_disponiveis[1:]

    idx_rua    = ruas_disponiveis.index(rua_ativa)       if rua_ativa    in ruas_disponiveis    else 0
    idx_bairro = bairros_disponiveis.index(bairro_ativo) if bairro_ativo in bairros_disponiveis else 0

    col_rua, col_num = st.columns([5, 1])
    with col_rua:
        rua_selecionada = st.selectbox(
            "🏠 Rua / Avenida", options=ruas_disponiveis,
            index=idx_rua, placeholder="Digite para filtrar...", help=hint_rua
        )
        if rua_selecionada != st.session_state.rua_sel:
            st.session_state.rua_sel = rua_selecionada
            if rua_selecionada and rua_selecionada in rua_p_bairro:
                bairros_da_rua = rua_p_bairro[rua_selecionada]
                if len(bairros_da_rua) == 1:
                    st.session_state.bairro_sel = bairros_da_rua[0]
            elif not rua_selecionada:
                st.session_state.bairro_sel = ""
            st.rerun()
    with col_num:
        numero = st.text_input("Nº", value=st.session_state.numero, placeholder="123")
        st.session_state.numero = numero

    bairro_selecionado = st.selectbox(
        "🏘️ Bairro", options=bairros_disponiveis,
        index=idx_bairro, placeholder="Digite para filtrar...", help=hint_bairro
    )
    if bairro_selecionado != st.session_state.bairro_sel:
        st.session_state.bairro_sel = bairro_selecionado
        if not bairro_selecionado:
            st.session_state.rua_sel = ""
        st.rerun()

    if st.button("🗺️ Verificar localização no mapa"):
        if not rua_selecionada:
            st.warning("⚠️ Selecione a rua antes de continuar.")
        else:
            tentativas = []
            if numero and bairro_selecionado:
                tentativas.append(f"{rua_selecionada}, {numero}, {bairro_selecionado}")
            if bairro_selecionado:
                tentativas.append(f"{rua_selecionada}, {bairro_selecionado}")
            tentativas.append(rua_selecionada)
            if bairro_selecionado: tentativas.append(bairro_selecionado)
            tentativas.append("Criciúma, SC")

            lat, lon, usou = None, None, ""
            with st.spinner("Verificando localização..."):
                for tentativa in tentativas:
                    lat, lon = geocodificar(tentativa)
                    if lat and lon:
                        usou = tentativa
                        break

            if lat and lon:
                st.session_state.coord_lat = lat
                st.session_state.coord_lon = lon
                if usou == rua_selecionada:
                    st.warning("📍 Localização aproximada — sem número exato.")
                elif usou == bairro_selecionado:
                    st.warning("📍 Localização aproximada — centralizando no bairro.")
                elif usou == "Criciúma, SC":
                    st.warning("📍 Endereço não encontrado. Pin centralizado em Criciúma.")
                else:
                    st.success("✅ Localização confirmada!")
            else:
                st.session_state.coord_lat = None
                st.session_state.coord_lon = None
                st.error("❌ Erro inesperado ao geocodificar.")

    coord_ok = bool(st.session_state.coord_lat and st.session_state.coord_lon)
    if coord_ok:
        st.map(
            pd.DataFrame({"lat": [st.session_state.coord_lat],
                          "lon": [st.session_state.coord_lon]}),
            latitude=st.session_state.coord_lat,
            longitude=st.session_state.coord_lon,
            zoom=16
        )
        st.caption("📍 Confirme se o pin está no local correto.")

    st.markdown("---")
    descricao = st.text_area(
        "📝 Descrição (opcional, mas ajuda!)",
        value=st.session_state.descricao,
        placeholder="Ex: Buraco grande na pista próximo à padaria..."
    )
    st.session_state.descricao = descricao

    classe_cidadao = st.selectbox(
        "🏷️ Qual o tipo de problema?",
        options=CATEGORIAS_SUGERIDAS,
    )

    st.markdown("")
    if st.button("📤 Enviar Demanda", type="primary"):
        if not rua_selecionada:
            st.warning("⚠️ Selecione a rua antes de enviar.")
        elif not coord_ok:
            st.warning("⚠️ Verifique a localização no mapa antes de enviar.")
        else:
            partes = [rua_selecionada]
            if numero:             partes.append(numero)
            if bairro_selecionado: partes.append(bairro_selecionado)
            endereco_completo = ", ".join(partes)

            with st.spinner("Enviando sua solicitação..."):
                url_do_arquivo = None
                tipo_arquivo_salvo = None
                if arquivo is not None:
                    ext  = arquivo.name.split(".")[-1]
                    nome = f"{uuid.uuid4()}.{ext}"
                    arquivo.seek(0)
                    supabase.storage.from_("anexos").upload(
                        nome, arquivo.read(), {"content-type": arquivo.type}
                    )
                    url_do_arquivo     = supabase.storage.from_("anexos").get_public_url(nome)
                    tipo_arquivo_salvo = arquivo.type
                    arquivo.seek(0)

                with st.spinner("Analisando com IA..."):
                    classe_gpt     = classificar_gpt(descricao, arquivo, tipo_arquivo_salvo or "")
                    classe_gemini  = classificar_gemini(descricao, arquivo, tipo_arquivo_salvo or "")
                    resultado_yolo = detectar_buraco_yolo(arquivo, tipo_arquivo_salvo or "")
                    classe_yolo_str = classe_yolo(resultado_yolo)

                supabase.table("solicitacoes").insert({
                    "data":           datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "classe":         classe_cidadao,
                    "classe_ia":      classe_gpt,
                    "classe_gemini":  classe_gemini,
                    "classe_yolo":    classe_yolo_str,
                    "endereco":       endereco_completo,
                    "descricao":      descricao,
                    "status":         "🔴 Pendente",
                    "resposta":       "Aguardando análise técnica",
                    "url_arquivo":    url_do_arquivo,
                    "tipo_arquivo":   tipo_arquivo_salvo,
                    "lat":            st.session_state.coord_lat,
                    "lon":            st.session_state.coord_lon,
                    "usuario_id":     st.session_state.usuario_id,
                }).execute()

            for k in ["rua_sel", "bairro_sel", "numero", "descricao"]:
                st.session_state[k] = ""
            st.session_state.coord_lat = None
            st.session_state.coord_lon = None
            st.success("✅ Solicitação enviada! Acompanhe em 'Minhas Solicitações'.")

# ---------------------------------------------------------------
elif not e_admin() and pagina == "📋 Minhas Solicitações":
    st.header("📋 Minhas Solicitações")
    with st.spinner("Carregando..."):
        # Filtra só as solicitações do usuário logado
        dados = (
            supabase.table("solicitacoes")
            .select("*")
            .eq("usuario_id", st.session_state.usuario_id)
            .order("id", desc=True)
            .execute()
            .data
        )

    if not dados:
        st.info("Você ainda não enviou nenhuma solicitação.")
    else:
        for item in dados:
            s = item.get("status", "")
            icon = "🔴" if "Pendente" in s else "🟡" if "andamento" in s.lower() else "🟢"
            with st.expander(f"{icon} {item.get('data','')} — {item.get('classe','')} | {s}"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.write(f"**📌 Endereço:** {item.get('endereco','')}")
                    st.write(f"**📝 Descrição:** {item.get('descricao','') or '—'}")
                    st.info(f"**💬 Resposta da Prefeitura:** {item.get('resposta','')}")
                    resp_url  = item.get("resp_url_arquivo")
                    resp_tipo = str(item.get("resp_tipo_arquivo", ""))
                    if resp_url:
                        st.caption("📎 Arquivo enviado pela Prefeitura:")
                        if resp_tipo.startswith("image/"): st.image(resp_url)
                        elif resp_tipo.startswith("video/"): st.video(resp_url)
                        else: st.markdown(f"[📎 Ver arquivo]({resp_url})")
                with col_b:
                    url = item.get("url_arquivo"); tipo = item.get("tipo_arquivo", "")
                    if url:
                        if str(tipo).startswith("image/"): st.image(url)
                        elif str(tipo).startswith("video/"): st.video(url)
                        elif str(tipo).startswith("audio/"): st.audio(url)
                        else: st.markdown(f"[📎 Ver anexo]({url})")

# ---------------------------------------------------------------
elif not e_admin() and pagina == "📊 Dashboard":
    st.header("📊 Impacto na Cidade")
    dados = supabase.table("solicitacoes").select("*").execute().data
    if dados:
        df = pd.DataFrame(dados)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(df))
        c2.metric("Pendentes", len(df[df["status"].str.contains("Pendente", na=False)]))
        c3.metric("Resolvidas", len(df[df["status"].str.contains("Resolvido", na=False)]))
        st.markdown("---")
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Por Tipo"); st.bar_chart(df["classe"].value_counts())
        with g2:
            st.subheader("Por Status"); st.bar_chart(df["status"].value_counts())
    else:
        st.warning("Sem dados ainda.")

# ██████████████████████████████████████████████████████████████
#  ADMIN
# ██████████████████████████████████████████████████████████████

elif e_admin():
    with st.spinner("Carregando ocorrências..."):
        df_raw = supabase.table("solicitacoes").select("*").order("id", desc=True).execute().data

    if not df_raw:
        st.info("Nenhuma solicitação cadastrada.")
        st.stop()

    df = pd.DataFrame(df_raw)

    st.title("🗺️ Painel de Gestão — Reporta Criciúma")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", len(df))
    m2.metric("Pendentes",    len(df[df["status"].str.contains("Pendente",  na=False)]))
    m3.metric("Em Andamento", len(df[df["status"].str.contains("andamento", case=False, na=False)]))
    m4.metric("Resolvidas",   len(df[df["status"].str.contains("Resolvido", na=False)]))
    st.markdown("---")

    TODOS_STATUS = ["Todos", "🔴 Pendente", "🟡 Em andamento", "🟢 Resolvido"]
    filtro_status_radio = st.radio("Status", TODOS_STATUS, horizontal=True, index=0)

    with st.expander("🔧 Filtros avançados"):
        filtro_classe = st.multiselect(
            "Tipo de problema",
            options=sorted(df["classe"].unique().tolist()),
            default=sorted(df["classe"].unique().tolist()),
        )

    filtro_status = df["status"].unique().tolist() if filtro_status_radio == "Todos" else [filtro_status_radio]
    df_f = df[df["classe"].isin(filtro_classe) & df["status"].isin(filtro_status)].copy()

    COR_STATUS = {
        "🔴 Pendente":     [220, 38,  38],
        "🟡 Em andamento": [234, 179, 8],
        "🟢 Resolvido":    [34,  197, 94],
    }

    if pagina == "📍 Mapa":
        st.subheader("📍 Mapa de Ocorrências")
        col_leg = st.columns(3)
        for i, (status, cor) in enumerate(COR_STATUS.items()):
            hex_cor = "#{:02x}{:02x}{:02x}".format(*cor)
            col_leg[i].markdown(
                f"<span style='display:inline-block;width:14px;height:14px;"
                f"border-radius:50%;background:{hex_cor};margin-right:6px;'></span>{status}",
                unsafe_allow_html=True
            )
        st.markdown("")

        if "lat" not in df_f.columns: df_f["lat"] = None
        if "lon" not in df_f.columns: df_f["lon"] = None

        sem_coord = df_f["lat"].isna()
        if sem_coord.any():
            with st.spinner("Geocodificando endereços sem coordenadas..."):
                for idx in df_f[sem_coord].index:
                    lat, lon = geocodificar(df_f.at[idx, "endereco"])
                    df_f.at[idx, "lat"] = lat
                    df_f.at[idx, "lon"] = lon

        df_mapa = df_f.dropna(subset=["lat", "lon"]).copy()

        if not df_mapa.empty:
            import pydeck as pdk
            df_mapa["cor"]     = df_mapa["status"].map(lambda s: COR_STATUS.get(s, [100, 100, 100]))
            df_mapa["tooltip"] = df_mapa.apply(
                lambda r: r["classe"] + " — " + r["status"] + "\n" + r["endereco"], axis=1
            )
            layer = pdk.Layer(
                "ScatterplotLayer", data=df_mapa,
                get_position=["lon", "lat"], get_fill_color="cor",
                get_radius=60, pickable=True,
            )
            view = pdk.ViewState(latitude=CRICIUMIA_LAT, longitude=CRICIUMIA_LON, zoom=13)
            st.pydeck_chart(pdk.Deck(
                layers=[layer], initial_view_state=view,
                tooltip={"text": "{tooltip}"},
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            ))
            st.caption(f"✅ {len(df_mapa)} de {len(df_f)} endereços no mapa.")
            st.dataframe(
                df_mapa[["id", "classe", "status", "endereco", "data"]].reset_index(drop=True),
                use_container_width=True
            )
        else:
            st.warning("Nenhum endereço geolocalizado para os filtros selecionados.")

    elif pagina == "📋 Demandas":
        st.subheader(f"📋 Demandas ({len(df_f)} encontradas)")
        for _, row in df_f.iterrows():
            s = str(row.get("status", ""))
            icon = "🔴" if "Pendente" in s else "🟡" if "andamento" in s.lower() else "🟢"

            classe_cid    = row.get("classe",        "—") or "—"
            classe_gpt    = row.get("classe_ia",     "—") or "—"
            classe_gemini = row.get("classe_gemini", "—") or "—"
            classe_yolo_v = row.get("classe_yolo",   "—") or "—"

            header = (
                f"{icon} #{row['id']} — "
                f"👤 {classe_cid} | GPT: {classe_gpt} | "
                f"Gemini: {classe_gemini} | YOLO: {classe_yolo_v} | "
                f"{row.get('status','')} | {row.get('data','')}"
            )

            with st.expander(header):
                col_info, col_midia = st.columns([2, 1])
                with col_info:
                    st.write(f"**📌 Endereço:** {row.get('endereco','')}")
                    st.write(f"**📝 Descrição:** {row.get('descricao','') or '—'}")
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    with cc1: st.info(f"**👤 Cidadão**\n{classe_cid}")
                    with cc2:
                        fn = st.success if classe_gpt == classe_cid else (st.warning if "Erro" in classe_gpt else st.info)
                        fn(f"**🤖 GPT**\n{classe_gpt}")
                    with cc3:
                        fn = st.success if classe_gemini == classe_cid else (st.warning if "Erro" in classe_gemini else st.info)
                        fn(f"**✨ Gemini**\n{classe_gemini}")
                    with cc4:
                        if classe_yolo_v == "—": st.info(f"**🔍 YOLO**\n{classe_yolo_v}")
                        elif "Buraco" in classe_yolo_v:
                            fn = st.success if classe_cid == "Buraco" else st.warning
                            fn(f"**🔍 YOLO**\n{classe_yolo_v}")
                        else: st.info(f"**🔍 YOLO**\n{classe_yolo_v}")

                with col_midia:
                    url = row.get("url_arquivo"); tipo = str(row.get("tipo_arquivo", ""))
                    if url:
                        if tipo.startswith("image/"): st.image(url)
                        elif tipo.startswith("video/"): st.video(url)
                        elif tipo.startswith("audio/"): st.audio(url)
                        else:
                            try: st.image(url)
                            except: st.markdown(f"[📎 Anexo]({url})")

                st.markdown("---")
                opcoes_status = ["🔴 Pendente", "🟡 Em andamento", "🟢 Resolvido"]
                idx_s = opcoes_status.index(row["status"]) if row["status"] in opcoes_status else 0
                c1, c2 = st.columns([1, 2])
                with c1:
                    novo_status = st.selectbox("Status", opcoes_status, index=idx_s, key=f"st_{row['id']}")
                with c2:
                    nova_resp = st.text_input("Resposta da Prefeitura", value=row.get("resposta", ""), key=f"rp_{row['id']}")

                resp_url_atual  = row.get("resp_url_arquivo")
                resp_tipo_atual = str(row.get("resp_tipo_arquivo", ""))
                if resp_url_atual:
                    st.caption("📎 Mídia já anexada à resposta:")
                    if resp_tipo_atual.startswith("image/"): st.image(resp_url_atual)
                    elif resp_tipo_atual.startswith("video/"): st.video(resp_url_atual)
                    else: st.markdown(f"[📎 Ver anexo da resposta]({resp_url_atual})")

                novo_arquivo_resp = st.file_uploader(
                    "📎 Anexar foto/vídeo à resposta (opcional)",
                    type=["png", "jpg", "jpeg", "webp", "mp4", "mov"],
                    key=f"fu_{row['id']}"
                )

                if st.button("💾 Salvar", key=f"sv_{row['id']}"):
                    update_data = {"status": novo_status, "resposta": nova_resp}
                    if novo_arquivo_resp is not None:
                        ext  = novo_arquivo_resp.name.split(".")[-1]
                        nome = f"resp_{uuid.uuid4()}.{ext}"
                        novo_arquivo_resp.seek(0)
                        supabase.storage.from_("anexos").upload(
                            nome, novo_arquivo_resp.read(), {"content-type": novo_arquivo_resp.type}
                        )
                        update_data["resp_url_arquivo"]  = supabase.storage.from_("anexos").get_public_url(nome)
                        update_data["resp_tipo_arquivo"] = novo_arquivo_resp.type
                    supabase.table("solicitacoes").update(update_data).eq("id", row["id"]).execute()
                    st.success("✅ Atualizado!")
                    st.rerun()

    elif pagina == "📊 Análise":
        st.subheader("📊 Análise Geral")
        g1, g2 = st.columns(2)
        with g1:
            st.write("**Por Tipo**"); st.bar_chart(df["classe"].value_counts())
        with g2:
            st.write("**Por Status**"); st.bar_chart(df["status"].value_counts())
        st.markdown("---")
        st.dataframe(
            df[["id", "data", "classe", "status", "endereco", "descricao"]],
            use_container_width=True
        )
