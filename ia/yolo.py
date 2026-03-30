import os
import cv2
import tempfile
import requests
import streamlit as st

_FALLBACK_URL = "http://localhost:8000"


def _get_api_url() -> str:
    try:
        return st.secrets["yolo"]["api_url"].rstrip("/")
    except Exception:
        return _FALLBACK_URL


for pos in posicoes:
    cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
    ret, frame = cap.read()
    if not ret:
        st.write(f"Frame {pos}: falhou leitura")
        continue

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_img:
        cv2.imwrite(tmp_img.name, frame)
        frames_tmp.append(tmp_img.name)

    st.write(f"Frame {pos}: extraído, enviando para API...")
    resultado = _detectar_em_imagem(tmp_img.name)
    st.write(f"Frame {pos}: resultado = {resultado}")
    if resultado and resultado.get("detectou_buraco"):
        resultados.append(resultado)

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
            tipo_envio = tipo if tipo.startswith("video/") else "video/mp4"
            r = requests.post(
                endpoint,
                files={"file": (arquivo.name, arquivo.read(), tipo_envio)},
                timeout=60,
            )
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
            # Salva o vídeo em arquivo temporário
            arquivo.seek(0)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(arquivo.read())
                tmp_video = tmp.name
            arquivo.seek(0)

            cap = cv2.VideoCapture(tmp_video)
            if not cap.isOpened():
                return None

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames < 5:
                return None

            # Posições: 10%, 30%, 50%, 70%, 90% do vídeo
            posicoes = [int(total_frames * p) for p in [0.10, 0.30, 0.50, 0.70, 0.90]]

            resultados = []
            for pos in posicoes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Salva frame como JPEG temporário
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_img:
                    cv2.imwrite(tmp_img.name, frame)
                    frames_tmp.append(tmp_img.name)

                resultado = _detectar_em_imagem(tmp_img.name)
                if resultado and resultado.get("detectou_buraco"):
                    resultados.append(resultado)

            cap.release()

            if not resultados:
                # Nenhum frame detectou — retorna "não detectado"
                return {"detectou_buraco": False, "confianca": 0.0, "n_deteccoes": 0,
                        "mensagem": "Nenhum buraco detectado nos frames analisados."}

            # Retorna o resultado com maior confiança
            return max(resultados, key=lambda x: x.get("confianca", 0))

        except Exception as e:
            print(f"⚠️  YOLO API (vídeo): {e}")
            return None
        finally:
            # Limpa arquivos temporários
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
