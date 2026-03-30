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

    # ── VÍDEO ─────────────────────────────────────────────────
    if tipo.startswith("video/"):
        tmp_video = None
        frames_tmp = []
        try:
            # Sufixo correto baseado no nome do arquivo
            ext = os.path.splitext(arquivo.name)[1].lower() if arquivo.name else ".mp4"
            sufixo = ext if ext in TIPOS_VIDEO else ".mp4"

            arquivo.seek(0)
            with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as tmp:
                tmp.write(arquivo.read())
                tmp_video = tmp.name
            arquivo.seek(0)

            cap = cv2.VideoCapture(tmp_video)
            if not cap.isOpened():
                print("⚠️  YOLO API: não foi possível abrir o vídeo")
                return None

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames < 5:
                print(f"⚠️  YOLO API: vídeo muito curto ({total_frames} frames)")
                return None

            # Posições: 10%, 30%, 50%, 70%, 90% do vídeo
            posicoes = [int(total_frames * p) for p in [0.10, 0.30, 0.50, 0.70, 0.90]]

            resultados = []
            for pos in posicoes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if not ret:
                    continue

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_img:
                    cv2.imwrite(tmp_img.name, frame)
                    frames_tmp.append(tmp_img.name)

                resultado = _detectar_em_imagem(tmp_img.name)
                if resultado and resultado.get("detectou_buraco"):
                    resultados.append(resultado)

            cap.release()

            if not resultados:
                return {"detectou_buraco": False, "confianca": 0.0, "n_deteccoes": 0,
                        "mensagem": "Nenhum buraco detectado nos frames analisados."}

            # Retorna o resultado com maior confiança
            return max(resultados, key=lambda x: x.get("confianca", 0))

        except Exception as e:
            print(f"⚠️  YOLO API (vídeo): {e}")
            return None
        finally:
            if tmp_video and os.path.exists(tmp_video):
                os.unlink(tmp_video)
            for f in frames_tmp:
                if os.path.exists(f):
                    os.unlink(f)

    return None  # áudio — sem detecção visual


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
