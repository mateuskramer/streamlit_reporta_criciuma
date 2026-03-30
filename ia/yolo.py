import os
import cv2
import tempfile
import requests
import streamlit as st

_FALLBACK_URL = "http://localhost:8000"

TIPOS_VIDEO = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
}


def _get_api_url() -> str:
    try:
        return st.secrets["yolo"]["api_url"].rstrip("/")
    except Exception:
        return _FALLBACK_URL


def _detectar_em_imagem(caminho_imagem: str) -> dict | None:
    """Envia um arquivo de imagem local para o endpoint /detect/image."""
    try:
        with open(caminho_imagem, "rb") as f:
            r = requests.post(
                f"{_get_api_url()}/detect/image",
                files={"file": ("frame.jpg", f, "image/jpeg")},
                timeout=30,
            )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  YOLO API (frame): {e}")
        return None


def detectar_buraco_yolo(arquivo=None, tipo_arquivo: str = "") -> dict | None:
    """
    Para imagem: envia direto para /detect/image.
    Para vídeo: extrai 5 frames distribuídos (10%, 30%, 50%, 70%, 90%)
                e retorna o resultado com maior confiança.
    Retorna None se arquivo for None, tipo for áudio, ou API indisponível.
    """
    if arquivo is None:
        return None

    tipo = tipo_arquivo or ""

    # ── IMAGEM ────────────────────────────────────────────────
    if tipo.startswith("image/"):
        try:
            arquivo.seek(0)
            r = requests.post(
                f"{_get_api_url()}/detect/image",
                files={"file": (arquivo.name, arquivo.read(), tipo)},
                timeout=30,
            )
            arquivo.seek(0)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            print("⚠️  YOLO API: timeout (imagem)")
            return None
        except requests.exceptions.ConnectionError:
            print("⚠️  YOLO API: sem conexão")
            return None
        except Exception as e:
            print(f"⚠️  YOLO API: {e}")
            return None

    if tipo.startswith("video/"):
        try:
            arquivo.seek(0)
            ext = os.path.splitext(arquivo.name)[1].lower() if arquivo.name else ".mp4"
            tipo_envio = TIPOS_VIDEO.get(ext, "video/mp4")
            r = requests.post(
                f"{_get_api_url()}/detect/video",
                files={"file": (arquivo.name, arquivo.read(), tipo_envio)},
                timeout=120,  # vídeo precisa de mais tempo
            )
            arquivo.seek(0)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            print("⚠️  YOLO API: timeout (vídeo)")
            return None
        except requests.exceptions.ConnectionError:
            print("⚠️  YOLO API: sem conexão")
            return None
        except Exception as e:
            print(f"⚠️  YOLO API: {e}")
            return None

def classe_yolo(resultado: dict | None) -> str:
    """
    Converte o resultado da YOLO API em string de classe,
    no mesmo formato que classificar_gpt() e classificar_gemini().
    """
    if resultado is None:
        return "—"
    if resultado.get("detectou_buraco"):
        conf = int(resultado.get("confianca", 0) * 100)
        return f"Buraco ({conf}%)"
    return "Não detectado"
