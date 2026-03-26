import base64
import json
import time
import requests
import streamlit as st

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
                json=payload,
                timeout=15,
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
