import base64
import json
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
