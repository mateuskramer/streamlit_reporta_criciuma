import requests
import streamlit as st

# URL da API YOLO — configure em st.secrets["yolo"]["api_url"]
# ou defina diretamente aqui para testes locais.
_FALLBACK_URL = "http://localhost:8000"


def _get_api_url() -> str:
    try:
        return st.secrets["yolo"]["api_url"].rstrip("/")
    except Exception:
        return _FALLBACK_URL


def detectar_buraco_yolo(arquivo=None, tipo_arquivo: str = "") -> dict | None:
    """
    Envia imagem ou vídeo para a YOLO API e retorna o resultado bruto.

    Retorno em caso de sucesso (imagem):
        {
            "detectou_buraco": bool,
            "confianca": float,       # 0.0 – 1.0
            "n_deteccoes": int,
            "mensagem": str
        }

    Retorno em caso de sucesso (vídeo):
        {
            "detectou_buraco": bool,
            "confianca": float,
            "n_frames_analisados": int,
            "n_frames_com_buraco": int,
            "mensagem": str
        }

    Retorna None se:
      - arquivo for None
      - tipo_arquivo for áudio (sem detecção visual)
      - API estiver indisponível (falha silenciosa — não quebra o fluxo)
    """
    if arquivo is None:
        return None

    tipo = tipo_arquivo or ""

    if tipo.startswith("image/"):
        endpoint = f"{_get_api_url()}/detect/image"
    elif tipo.startswith("video/"):
        endpoint = f"{_get_api_url()}/detect/video"
    else:
        return None  # áudio não tem detecção visual

    try:
        arquivo.seek(0)
        r = requests.post(
            endpoint,
            files={"file": (arquivo.name, arquivo.read(), tipo)},
            timeout=60,  # vídeo pode levar mais tempo
        )
        arquivo.seek(0)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        print("⚠️  YOLO API: timeout")
        return None
    except requests.exceptions.ConnectionError:
        print("⚠️  YOLO API: sem conexão")
        return None
    except Exception as e:
        print(f"⚠️  YOLO API: {e}")
        return None


def classe_yolo(resultado: dict | None) -> str:
    """
    Converte o resultado bruto da YOLO API em uma string de classe,
    no mesmo formato que classificar_gpt() e classificar_gemini().

    Exemplos de retorno:
      "Buraco (87%)"   — detectou com confiança
      "Não detectado"  — API respondeu mas não achou buraco
      "—"              — API indisponível ou arquivo não suportado
    """
    if resultado is None:
        return "—"
    if resultado.get("detectou_buraco"):
        conf = int(resultado.get("confianca", 0) * 100)
        return f"Buraco ({conf}%)"
    return "Não detectado"
