import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
import uuid
import requests
import time
import base64
import json

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
            "address":  f"{endereco}, Criciúma, SC, Brasil",
            "key":      api_key,
            "language": "pt-BR",
            "region":   "BR",
            "components": "country:BR|administrative_area:SC",
        }
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=10,
        )
        data = r.json()
        status = data.get("status")
        if status != "OK" or not data.get("results"):
            st.error(f"🗺️ Google Maps: status={status} | erro={data.get('error_message','—')}")
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
# RUAS FALLBACK — usadas se a ViaCEP não retornar dados suficientes
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

# ==============================================================
# PRÉ-CARREGA TODAS AS RUAS E BAIRROS DE CRICIÚMA (ViaCEP)
# Executa uma vez e fica em cache por 24h.
# Retorna: (ruas_sorted, bairros_sorted, rua_para_bairros, bairro_para_ruas)
# ==============================================================
@st.cache_data(show_spinner=False, ttl=86400)
def carregar_todas_ruas_e_bairros():
    """
    Varre termos genéricos na ViaCEP e monta:
      - lista de ruas
      - lista de bairros
      - dict rua  → set de bairros (para filtrar bairro ao escolher rua)
      - dict bairro → set de ruas  (para filtrar rua ao escolher bairro)
    """
    import urllib.parse

    termos = [
        "rua", "avenida", "travessa", "estrada", "rodovia",
        "alameda", "linha", "servidão", "vila", "beco",
        "largo", "praça", "loteamento", "parque"
    ]

    ruas_set    = set()
    bairros_set = set()
    rua_p_bairro  = {}   # rua  → {bairro, ...}
    bairro_p_rua  = {}   # bairro → {rua, ...}

    for termo in termos:
        try:
            url = (
                f"https://viacep.com.br/ws/SC/Crici%C3%BAma/"
                f"{urllib.parse.quote(termo)}/json/"
            )
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue
            for item in data:
                logradouro = item.get("logradouro", "").strip()
                bairro     = item.get("bairro", "").strip()
                if logradouro:
                    ruas_set.add(logradouro)
                if bairro:
                    bairros_set.add(bairro)
                # Monta os índices cruzados
                if logradouro and bairro:
                    rua_p_bairro.setdefault(logradouro, set()).add(bairro)
                    bairro_p_rua.setdefault(bairro, set()).add(logradouro)
            time.sleep(0.1)
        except Exception:
            continue

    # Mescla fallback (sem relacionamento cruzado — bairros genéricos)
    ruas_set    |= set(RUAS_FALLBACK)
    bairros_set |= set(BAIRROS_FALLBACK)

    # Converte sets para listas ordenadas nos dicts (para ser serializável pelo cache)
    rua_p_bairro_sorted  = {k: sorted(v) for k, v in rua_p_bairro.items()}
    bairro_p_rua_sorted  = {k: sorted(v) for k, v in bairro_p_rua.items()}

    return sorted(ruas_set), sorted(bairros_set), rua_p_bairro_sorted, bairro_p_rua_sorted


# ==============================================================
# CLASSIFICAÇÃO POR IA — GPT-4o-mini + Gemini (piloto comparativo)
# ==============================================================
CATEGORIAS_SUGERIDAS = ["Buraco", "Lixo", "Barulho", "Lâmpada Apagada", "Outro"]

PROMPT_IA = (
    "Você é um assistente de gestão urbana da prefeitura de Criciúma, SC. "
    "Analise a descrição e/ou imagem enviada pelo cidadão e classifique o problema. "
    "Prefira uma dessas categorias: Buraco, Lixo, Barulho, Lâmpada Apagada. "
    "Se não se encaixar bem em nenhuma, use uma categoria curta e descritiva (ex: Calçada, Esgoto, Pichação). "
    'Responda APENAS com JSON: {"classe": "categoria_aqui"}'
)

def _parse_classe(texto: str) -> str:
    texto = texto.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(texto).get("classe", "Outro") or "Outro"

def classificar_gpt(descricao: str = "", arquivo=None, tipo_arquivo: str = "") -> str:
    try:
        api_key = st.secrets["openai"]["api_key"]
    except Exception:
        return "Erro (sem chave)"

    prompt_full = PROMPT_IA + f" Descrição: {descricao if descricao else '(não fornecida)'}"
    content_parts = [{"type": "text", "text": prompt_full}]
    if arquivo is not None and tipo_arquivo in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        arquivo.seek(0)
        img_b64 = base64.b64encode(arquivo.read()).decode("utf-8")
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{tipo_arquivo};base64,{img_b64}", "detail": "low"}
        })
        arquivo.seek(0)

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": content_parts}],
                "max_tokens": 50,
                "temperature": 0.1,
            },
            timeout=15,
        )
        r.raise_for_status()
        return _parse_classe(r.json()["choices"][0]["message"]["content"])
    except requests.exceptions.Timeout:
        return "Erro GPT: timeout"
    except requests.exceptions.HTTPError as e:
        codigo = e.response.status_code if e.response is not None else "?"
        return f"Erro GPT: HTTP {codigo}"
    except Exception as e:
        return f"Erro GPT: {str(e)[:40]}"

def classificar_gemini(descricao: str = "", arquivo=None, tipo_arquivo: str = "") -> str:
    try:
        api_key = st.secrets["gemini"]["api_key"]
    except Exception:
        return "Erro (sem chave)"

    prompt_full = PROMPT_IA + f" Descrição: {descricao if descricao else '(não fornecida)'}"
    parts = [{"text": prompt_full}]
    if arquivo is not None and tipo_arquivo in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        arquivo.seek(0)
        parts.append({"inline_data": {
            "mime_type": tipo_arquivo,
            "data": base64.b64encode(arquivo.read()).decode("utf-8")
        }})
        arquivo.seek(0)

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 50}
    }

    ultimo_erro = "desconhecido"
    for modelo in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}",
                json=payload, timeout=15
            )
            if r.status_code == 429:
                ultimo_erro = "rate limit (429)"
                time.sleep(2)
                continue
            if not r.ok:
                ultimo_erro = f"HTTP {r.status_code}"
                continue
            return _parse_classe(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except requests.exceptions.Timeout:
            ultimo_erro = "timeout"
            continue
        except Exception as e:
            ultimo_erro = str(e)[:40]
            continue
    return f"Erro Gemini: {ultimo_erro}"

# ==============================================================
# SIDEBAR — SWITCH CIDADÃO / ADMIN
# ==============================================================
st.sidebar.image("https://img.icons8.com/fluency/96/city-buildings.png", width=80)
st.sidebar.title("Reporta Criciúma")
st.sidebar.markdown("---")

modo = st.sidebar.radio("Modo", ["👤 Cidadão", "🔐 Administrador"], index=0)

# ==============================================================
# AUTENTICAÇÃO DO ADMIN — desativada temporariamente
# ==============================================================

# ==============================================================
# NAVEGAÇÃO
# ==============================================================
if modo == "👤 Cidadão":
    st.sidebar.markdown("---")
    pagina = st.sidebar.radio(
        "Navegação",
        ["🆕 Nova Solicitação", "📋 Minhas Solicitações", "📊 Dashboard"]
    )
else:
    st.sidebar.markdown("---")
    pagina = st.sidebar.radio(
        "Painel Admin",
        ["📍 Mapa", "📋 Demandas", "📊 Análise"]
    )

st.sidebar.markdown("---")
st.sidebar.caption("Reporta Criciúma v1.4 — Criciúma, SC")

# ██████████████████████████████████████████████████████████████
#  ÁREA DO CIDADÃO — NOVA SOLICITAÇÃO
# ██████████████████████████████████████████████████████████████

if modo == "👤 Cidadão" and pagina == "🆕 Nova Solicitação":
    st.header("📍 Reportar Problema")
    st.write("Descreva o problema e informe o local. Nossa equipe cuida do resto!")

    # Inicializa session_state
    defaults = {
        "rua_sel": "", "numero": "", "bairro_sel": "",
        "descricao": "", "coord_lat": None, "coord_lon": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ---- Pré-carrega ruas, bairros e índices cruzados ----
    with st.spinner("🔄 Carregando logradouros de Criciúma..."):
        todas_ruas, todos_bairros, rua_p_bairro, bairro_p_rua = carregar_todas_ruas_e_bairros()

    # ---------- Anexo ----------
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
            if tipo.startswith("image/"):
                st.image(arquivo, use_column_width=True); arquivo.seek(0)
            elif tipo.startswith("video/"):
                st.video(arquivo); arquivo.seek(0)
            elif tipo.startswith("audio/"):
                st.audio(arquivo); arquivo.seek(0)

    with aba_camera:
        foto_camera = st.camera_input("Tire uma foto do problema")
        if foto_camera is not None:
            arquivo = foto_camera  # camera_input já retorna um objeto compatível com file_uploader
            st.image(foto_camera, use_column_width=True)

    st.markdown("---")
    st.subheader("📌 Localização do Problema")

    # ---- Monta lista de ruas filtrada pelo bairro já selecionado (e vice-versa) ----
    bairro_ativo = st.session_state.bairro_sel
    rua_ativa    = st.session_state.rua_sel

    if bairro_ativo and bairro_ativo in bairro_p_rua:
        # Bairro escolhido primeiro → mostra só as ruas daquele bairro
        ruas_disponiveis = [""] + sorted(bairro_p_rua[bairro_ativo])
        hint_rua = f"Mostrando {len(ruas_disponiveis)-1} ruas do bairro {bairro_ativo}. Limpe o bairro para ver todas."
    else:
        ruas_disponiveis = [""] + todas_ruas
        hint_rua = f"{len(todas_ruas)} logradouros disponíveis. Escolha o bairro primeiro para filtrar."

    if rua_ativa and rua_ativa in rua_p_bairro:
        # Rua escolhida primeiro → mostra só os bairros daquela rua
        bairros_disponiveis = [""] + sorted(rua_p_bairro[rua_ativa])
        hint_bairro = f"Bairro(s) compatível(is) com a rua selecionada."
    else:
        bairros_disponiveis = [""] + todos_bairros
        hint_bairro = f"{len(todos_bairros)} bairros disponíveis."

    # Garante que o valor atual está na lista (pode vir do CEP)
    if rua_ativa and rua_ativa not in ruas_disponiveis:
        ruas_disponiveis = ["", rua_ativa] + ruas_disponiveis[1:]
    if bairro_ativo and bairro_ativo not in bairros_disponiveis:
        bairros_disponiveis = ["", bairro_ativo] + bairros_disponiveis[1:]

    idx_rua    = ruas_disponiveis.index(rua_ativa)    if rua_ativa    in ruas_disponiveis    else 0
    idx_bairro = bairros_disponiveis.index(bairro_ativo) if bairro_ativo in bairros_disponiveis else 0

    # ---- Rua + Número na mesma linha ----
    col_rua, col_num = st.columns([5, 1])
    with col_rua:
        rua_selecionada = st.selectbox(
            "🏠 Rua / Avenida",
            options=ruas_disponiveis,
            index=idx_rua,
            placeholder="Digite para filtrar...",
            help=hint_rua
        )
        # Atualiza estado e filtra bairro automaticamente
        if rua_selecionada != st.session_state.rua_sel:
            st.session_state.rua_sel = rua_selecionada
            # Se só um bairro possível, preenche automaticamente
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

    # ---- Bairro ----
    bairro_selecionado = st.selectbox(
        "🏘️ Bairro",
        options=bairros_disponiveis,
        index=idx_bairro,
        placeholder="Digite para filtrar...",
        help=hint_bairro
    )
    # Atualiza estado e filtra ruas automaticamente
    if bairro_selecionado != st.session_state.bairro_sel:
        st.session_state.bairro_sel = bairro_selecionado
        if not bairro_selecionado:
            st.session_state.rua_sel = ""
        st.rerun()



    # ---- Verificar no mapa ----
    if st.button("🗺️ Verificar localização no mapa"):
        if not rua_selecionada:
            st.warning("⚠️ Selecione a rua antes de continuar.")
        else:
            # Cascata de tentativas: mais específico → mais genérico
            tentativas = []
            if numero and bairro_selecionado:
                tentativas.append(f"{rua_selecionada}, {numero}, {bairro_selecionado}")
            if bairro_selecionado:
                tentativas.append(f"{rua_selecionada}, {bairro_selecionado}")
            tentativas.append(rua_selecionada)
            if bairro_selecionado:
                tentativas.append(bairro_selecionado)   # fallback: centraliza no bairro
            tentativas.append("Criciúma, SC")            # último recurso

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
                # Avisa o usuário se usou um endereço menos preciso
                if usou == rua_selecionada:
                    st.warning("📍 Localização aproximada — endereço encontrado, mas sem número exato.")
                elif usou == bairro_selecionado:
                    st.warning("📍 Localização aproximada — rua não encontrada, centralizando no bairro.")
                elif usou == "Criciúma, SC":
                    st.warning("📍 Não foi possível localizar o endereço. Pin centralizado em Criciúma.")
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

    # ---- Descrição ----
    st.markdown("---")
    descricao = st.text_area(
        "📝 Descrição (opcional, mas ajuda!)",
        value=st.session_state.descricao,
        placeholder="Ex: Buraco grande na pista próximo à padaria, causando risco para motoristas..."
    )
    st.session_state.descricao = descricao

    # ---- Classificação do cidadão ----
    classe_cidadao = st.selectbox(
        "🏷️ Qual o tipo de problema?",
        options=CATEGORIAS_SUGERIDAS,
        help="Escolha a categoria que melhor descreve o problema."
    )

    # ---- Enviar ----
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
                # 1. Upload do arquivo
                url_do_arquivo = None; tipo_arquivo_salvo = None
                if arquivo is not None:
                    ext  = arquivo.name.split(".")[-1]
                    nome = f"{uuid.uuid4()}.{ext}"
                    arquivo.seek(0)
                    supabase.storage.from_("anexos").upload(nome, arquivo.read(), {"content-type": arquivo.type})
                    url_do_arquivo     = supabase.storage.from_("anexos").get_public_url(nome)
                    tipo_arquivo_salvo = arquivo.type
                    arquivo.seek(0)

                # 2. Ambas as IAs classificam
                with st.spinner("Analisando problema com IA..."):
                    classe_gpt    = classificar_gpt(descricao, arquivo, tipo_arquivo_salvo or "")
                    classe_gemini = classificar_gemini(descricao, arquivo, tipo_arquivo_salvo or "")

                # 3. Salva no Supabase (inclui lat/lon já conhecidos do cidadão)
                supabase.table("solicitacoes").insert({
                    "data":           datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "classe":         classe_cidadao,
                    "classe_ia":      classe_gpt,
                    "classe_gemini":  classe_gemini,
                    "endereco":       endereco_completo,
                    "descricao":      descricao,
                    "status":         "🔴 Pendente",
                    "resposta":       "Aguardando análise técnica",
                    "url_arquivo":    url_do_arquivo,
                    "tipo_arquivo":   tipo_arquivo_salvo,
                    "lat":            st.session_state.coord_lat,
                    "lon":            st.session_state.coord_lon,
                }).execute()

            # Reset
            for k in ["rua_sel", "bairro_sel", "numero", "descricao"]:
                st.session_state[k] = ""
            st.session_state.coord_lat = None
            st.session_state.coord_lon = None
            st.success("✅ Solicitação enviada com sucesso! Acompanhe em 'Minhas Solicitações'.")
            

# ---------------------------------------------------------------
elif modo == "👤 Cidadão" and pagina == "📋 Minhas Solicitações":
    st.header("📋 Acompanhamento de Solicitações")
    with st.spinner("Carregando..."):
        dados = supabase.table("solicitacoes").select("*").order("id", desc=True).execute().data

    if not dados:
        st.info("Nenhuma solicitação ainda. Envie sua primeira demanda!")
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
                    # Mídia anexada pelo admin na resposta
                    resp_url  = item.get("resp_url_arquivo")
                    resp_tipo = str(item.get("resp_tipo_arquivo",""))
                    if resp_url:
                        st.caption("📎 Arquivo enviado pela Prefeitura:")
                        if resp_tipo.startswith("image/"): st.image(resp_url)
                        elif resp_tipo.startswith("video/"): st.video(resp_url)
                        else: st.markdown(f"[📎 Ver arquivo]({resp_url})")
                with col_b:
                    url = item.get("url_arquivo"); tipo = item.get("tipo_arquivo","")
                    if url:
                        if str(tipo).startswith("image/"): st.image(url)
                        elif str(tipo).startswith("video/"): st.video(url)
                        elif str(tipo).startswith("audio/"): st.audio(url)
                        else: st.markdown(f"[📎 Ver anexo]({url})")

# ---------------------------------------------------------------
elif modo == "👤 Cidadão" and pagina == "📊 Dashboard":
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
#  ÁREA DO ADMIN
# ██████████████████████████████████████████████████████████████

elif modo == "🔐 Administrador":
    with st.spinner("Carregando ocorrências..."):
        df_raw = supabase.table("solicitacoes").select("*").order("id", desc=True).execute().data

    if not df_raw:
        st.info("Nenhuma solicitação cadastrada.")
        st.stop()

    df = pd.DataFrame(df_raw)

    st.title("🗺️ Painel de Gestão — Reporta Criciúma")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", len(df))
    m2.metric("Pendentes", len(df[df["status"].str.contains("Pendente", na=False)]))
    m3.metric("Em Andamento", len(df[df["status"].str.contains("andamento", case=False, na=False)]))
    m4.metric("Resolvidas", len(df[df["status"].str.contains("Resolvido", na=False)]))
    st.markdown("---")

    # ---- Filtros inline ----
    TODOS_STATUS = ["Todos", "🔴 Pendente", "🟡 Em andamento", "🟢 Resolvido"]
    filtro_status_radio = st.radio(
        "Status", TODOS_STATUS, horizontal=True, index=0
    )

    with st.expander("🔧 Filtros avançados"):
        filtro_classe = st.multiselect(
            "Tipo de problema",
            options=sorted(df["classe"].unique().tolist()),
            default=sorted(df["classe"].unique().tolist()),
        )

    if filtro_status_radio == "Todos":
        filtro_status = df["status"].unique().tolist()
    else:
        filtro_status = [filtro_status_radio]

    df_f = df[df["classe"].isin(filtro_classe) & df["status"].isin(filtro_status)].copy()

    # Cores por status para o mapa (RGB)
    COR_STATUS = {
        "🔴 Pendente":      [220, 38,  38],   # vermelho
        "🟡 Em andamento":  [234, 179, 8],    # amarelo
        "🟢 Resolvido":     [34,  197, 94],   # verde
    }

    if pagina == "📍 Mapa":
        st.subheader("📍 Mapa de Ocorrências")

        # Legenda de cores
        col_leg = st.columns(3)
        for i, (status, cor) in enumerate(COR_STATUS.items()):
            hex_cor = "#{:02x}{:02x}{:02x}".format(*cor)
            col_leg[i].markdown(
                f"<span style='display:inline-block;width:14px;height:14px;"
                f"border-radius:50%;background:{hex_cor};margin-right:6px;'></span>{status}",
                unsafe_allow_html=True
            )
        st.markdown("")

        # Usa lat/lon salvo no banco; geocodifica só se estiver faltando
        def garantir_coords(row):
            if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
                return row["lat"], row["lon"]
            return geocodificar(row["endereco"])

        if "lat" not in df_f.columns: df_f["lat"] = None
        if "lon" not in df_f.columns: df_f["lon"] = None

        sem_coord = df_f["lat"].isna()
        if sem_coord.any():
            with st.spinner("Geocodificando endereços sem coordenadas..."):
                for idx in df_f[sem_coord].index:
                    lat, lon = geocodificar(df_f.at[idx, "endereco"])
                    df_f.at[idx, "lat"] = lat
                    df_f.at[idx, "lon"] = lon

        df_mapa = df_f.dropna(subset=["lat","lon"]).copy()

        if not df_mapa.empty:
            import pydeck as pdk
            df_mapa["cor"] = df_mapa["status"].map(lambda s: COR_STATUS.get(s, [100, 100, 100]))
            df_mapa["tooltip"] = df_mapa.apply(
                lambda r: r["classe"] + " — " + r["status"] + "\n" + r["endereco"], axis=1
            )
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_mapa,
                get_position=["lon", "lat"],
                get_fill_color="cor",
                get_radius=60,
                pickable=True,
            )
            view = pdk.ViewState(
                latitude=CRICIUMIA_LAT, longitude=CRICIUMIA_LON, zoom=13
            )
            st.pydeck_chart(pdk.Deck(
                layers=[layer],
                initial_view_state=view,
                tooltip={"text": "{tooltip}"},
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            ))
            st.caption(f"✅ {len(df_mapa)} de {len(df_f)} endereços no mapa.")
            st.dataframe(df_mapa[["id","classe","status","endereco","data"]].reset_index(drop=True), use_container_width=True)
        else:
            st.warning("Nenhum endereço geolocalizado para os filtros selecionados.")

    elif pagina == "📋 Demandas":
        st.subheader(f"📋 Demandas ({len(df_f)} encontradas)")
        for _, row in df_f.iterrows():
            icon = "🔴" if "Pendente" in str(row.get("status","")) else "🟡" if "andamento" in str(row.get("status","")).lower() else "🟢"
            classe_cid    = row.get("classe", "—") or "—"
            classe_gpt    = row.get("classe_ia", "—") or "—"
            classe_gemini = row.get("classe_gemini", "—") or "—"
            header = (
                f"{icon} #{row['id']} — "
                f"👤 {classe_cid} | GPT: {classe_gpt} | Gemini: {classe_gemini} | "
                f"{row.get('status','')} | {row.get('data','')}"
            )
            with st.expander(header):
                col_info, col_midia = st.columns([2, 1])
                with col_info:
                    st.write(f"**📌 Endereço:** {row.get('endereco','')}")
                    st.write(f"**📝 Descrição:** {row.get('descricao','') or '—'}")
                    # Classificações comparativas
                    cc1, cc2, cc3 = st.columns(3)
                    with cc1:
                        st.info(f"**👤 Cidadão**\n{classe_cid}")
                    with cc2:
                        fn = st.success if classe_gpt == classe_cid else (st.warning if classe_gpt.startswith("Erro") else st.info)
                        fn(f"**🤖 GPT**\n{classe_gpt}")
                    with cc3:
                        fn = st.success if classe_gemini == classe_cid else (st.warning if classe_gemini.startswith("Erro") else st.info)
                        fn(f"**✨ Gemini**\n{classe_gemini}")
                with col_midia:
                    url = row.get("url_arquivo"); tipo = str(row.get("tipo_arquivo",""))
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
                    nova_resp = st.text_input("Resposta da Prefeitura", value=row.get("resposta",""), key=f"rp_{row['id']}")

                # Anexo já enviado pelo admin
                resp_url_atual  = row.get("resp_url_arquivo")
                resp_tipo_atual = str(row.get("resp_tipo_arquivo",""))
                if resp_url_atual:
                    st.caption("📎 Mídia já anexada à resposta:")
                    if resp_tipo_atual.startswith("image/"): st.image(resp_url_atual)
                    elif resp_tipo_atual.startswith("video/"): st.video(resp_url_atual)
                    else: st.markdown(f"[📎 Ver anexo da resposta]({resp_url_atual})")

                novo_arquivo_resp = st.file_uploader(
                    "📎 Anexar foto/vídeo à resposta (opcional)",
                    type=["png","jpg","jpeg","webp","mp4","mov"],
                    key=f"fu_{row['id']}"
                )

                if st.button("💾 Salvar", key=f"sv_{row['id']}"):
                    update_data = {"status": novo_status, "resposta": nova_resp}
                    if novo_arquivo_resp is not None:
                        ext  = novo_arquivo_resp.name.split(".")[-1]
                        nome = f"resp_{uuid.uuid4()}.{ext}"
                        novo_arquivo_resp.seek(0)
                        supabase.storage.from_("anexos").upload(nome, novo_arquivo_resp.read(), {"content-type": novo_arquivo_resp.type})
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
        st.dataframe(df[["id","data","classe","status","endereco","descricao"]], use_container_width=True)
