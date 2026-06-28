"""
tiktok.py — Genera vídeo amb Google Veo 2 i el publica a TikTok.

SETUP PREVI (una sola vegada):
  1. Crea una app a developers.tiktok.com amb permisos:
       video.upload  i  video.publish
  2. Executa: python oauth_tiktok.py  (captura el refresh_token)
  3. Afegeix 3 secrets a GitHub Actions (repo Settings > Secrets):
       TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  4. NOTA: TikTok requereix revisió de l'app per al permís video.publish.
     Fins que no aproven l'app, usa el Sandbox (mode de proves) que creen
     automàticament. La sol·licitud d'aprovació es fa des del portal.

FLUX en producció:
  - Agafa la descripció de la imatge (camp `imatge` del post)
  - La tradueix a anglès i genera un vídeo 9:16 de ~8s amb Veo 2
  - Puja el vídeo a TikTok i el publica directament (DIRECT_POST)
  - Usa el text d'Instagram com a peu de vídeo (el més visual dels 3)
"""

import os
import time
from pathlib import Path

import requests

from config import get_key

TIKTOK_API = "https://open.tiktokapis.com/v2"
VEO_MODEL = "veo-2.0-generate-001"

ARREL = Path(__file__).resolve().parent
DIR_VIDEOS = ARREL / "videos_tiktok"

# Màxim temps d'espera per a la generació del vídeo (Veo pot trigar 3-8 min)
ESPERA_VEO_INTENTS = 60   # 60 × 10s = 10 minuts
ESPERA_VEO_INTERVAL = 10  # segons entre polls


# ---------------------------------------------------------------------------
# OAuth: access token des del refresh token
# ---------------------------------------------------------------------------

def _get_access_token():
    """Obté un access token fresc des del refresh token emmagatzemat."""
    client_key = get_key("TIKTOK_CLIENT_KEY")
    client_secret = get_key("TIKTOK_CLIENT_SECRET")
    refresh_token = get_key("TIKTOK_REFRESH_TOKEN")

    if not all([client_key, client_secret, refresh_token]):
        return None, (
            "Falten TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET o TIKTOK_REFRESH_TOKEN. "
            "Executa oauth_tiktok.py per fer el setup inicial."
        )
    try:
        r = requests.post(
            "{}/oauth/token/".format(TIKTOK_API),
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        data = r.json()
    except Exception as e:
        return None, "Error de xarxa obtenint token de TikTok: {}".format(e)

    if data.get("error"):
        return None, "TikTok OAuth: {} — {}".format(
            data.get("error"), data.get("error_description", ""))

    token = data.get("access_token")
    if not token:
        return None, "TikTok no ha retornat access_token: {}".format(data)
    return token, None


# ---------------------------------------------------------------------------
# Generació de vídeo amb Veo 2
# ---------------------------------------------------------------------------

def _tradueix_a_prompt_video(descripcio_ca):
    """Converteix la descripció catalana a un prompt de vídeo anglès per a Veo 2."""
    api_key = get_key("GEMINI_API_KEY")
    if not api_key:
        return descripcio_ca
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + api_key
        )
        payload = {
            "contents": [{"parts": [{"text": (
                "Translate this Catalan visual description into a short, cinematic "
                "video prompt for an AI video generator (Veo 2). Style: warm natural "
                "lighting, literary mood, dynamic subtle motion, no people, no text. "
                "Under 80 words. Output ONLY the English prompt.\n\n" + descripcio_ca
            )}]}],
            "generationConfig": {
                "maxOutputTokens": 150,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        r = requests.post(url, json=payload, timeout=20)
        text = (
            r.json()["candidates"][0]["content"]["parts"][0]["text"]
            .strip()
            .strip('"')
        )
        return text
    except Exception as e:
        print("[tiktok] No s'ha pogut traduir el prompt: {}; s'usa l'original.".format(e))
        return descripcio_ca


def genera_video(descripcio_ca, data_iso):
    """
    Genera un vídeo 9:16 de ~8s amb Google Veo 2.
    Desa el resultat a videos_tiktok/<data_iso>_tiktok.mp4.
    Retorna el Path local o None si falla.
    """
    DIR_VIDEOS.mkdir(exist_ok=True)
    fitxer = DIR_VIDEOS / "{}_tiktok.mp4".format(data_iso)
    if fitxer.exists():
        print("[tiktok] Vídeo ja generat: {}".format(fitxer.name))
        return fitxer

    api_key = get_key("GEMINI_API_KEY")
    if not api_key:
        print("[tiktok] Falta GEMINI_API_KEY.")
        return None

    prompt = _tradueix_a_prompt_video(descripcio_ca)
    print("[tiktok] Generant vídeo Veo 2 (pot trigar 3-8 min)...")
    print("[tiktok] Prompt: {}".format(prompt[:120]))

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)
        operation = client.models.generate_video(
            model=VEO_MODEL,
            prompt=prompt,
            config=genai_types.GenerateVideoConfig(
                aspect_ratio="9:16",
                number_of_videos=1,
            ),
        )

        for i in range(ESPERA_VEO_INTENTS):
            if operation.done:
                break
            if i > 0 and i % 6 == 0:
                print("[tiktok] ...esperant Veo 2 ({}/{}min)...".format(
                    i * ESPERA_VEO_INTERVAL // 60,
                    ESPERA_VEO_INTENTS * ESPERA_VEO_INTERVAL // 60,
                ))
            time.sleep(ESPERA_VEO_INTERVAL)
            operation = client.operations.get(operation)

        if not operation.done:
            print("[tiktok] Veo 2 ha trigat massa (>{}min); es rendeix.".format(
                ESPERA_VEO_INTENTS * ESPERA_VEO_INTERVAL // 60))
            return None

        video = operation.response.generated_videos[0].video
        video_bytes = client.files.download(file=video)
        fitxer.write_bytes(video_bytes)
        print("[tiktok] Vídeo generat: {} ({:.1f} MB)".format(
            fitxer.name, len(video_bytes) / 1_000_000))
        return fitxer

    except Exception as e:
        print("[tiktok] Error generant vídeo amb Veo 2: {}".format(e))
        return None


# ---------------------------------------------------------------------------
# Publicació a TikTok
# ---------------------------------------------------------------------------

def publica_tiktok(text, descripcio_imatge, data_str):
    """
    Genera el vídeo i el publica a TikTok via l'API Content Posting v2.

    Args:
        text: text del post (s'usa com a peu de vídeo; fins a 2200 cars)
        descripcio_imatge: descripció visual en català per a Veo 2
        data_str: data ISO del post (per cachejar el vídeo)

    Returns:
        {"ok": True, "msg": "...", "publish_id": "..."} o {"ok": False, "error": "..."}
    """
    # 1. Access token
    token, err = _get_access_token()
    if err:
        return {"ok": False, "error": err}

    # 2. Generar vídeo
    video_path = genera_video(descripcio_imatge or "", data_str)
    if not video_path:
        return {"ok": False, "error": "No s'ha pogut generar el vídeo amb Veo 2."}

    video_bytes = video_path.read_bytes()
    mida = len(video_bytes)

    headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type": "application/json; charset=UTF-8",
    }

    # 3. Init upload
    init_data = {
        "post_info": {
            "title": text[:2200],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": mida,
            "chunk_size": mida,
            "total_chunk_count": 1,
        },
        "post_mode": "DIRECT_POST",
        "media_type": "VIDEO",
    }
    try:
        r = requests.post(
            "{}/post/publish/video/init/".format(TIKTOK_API),
            json=init_data,
            headers=headers,
            timeout=30,
        )
        resp = r.json()
    except Exception as e:
        return {"ok": False, "error": "Error de xarxa iniciant upload a TikTok: {}".format(e)}

    err_info = resp.get("error", {})
    if err_info.get("code", "ok") != "ok":
        return {"ok": False, "error": "TikTok init: {} — {}".format(
            err_info.get("code"), err_info.get("message", ""))}

    upload_url = resp["data"]["upload_url"]
    publish_id = resp["data"]["publish_id"]

    # 4. Pujar el vídeo (una sola peça)
    try:
        r2 = requests.put(
            upload_url,
            data=video_bytes,
            headers={
                "Content-Range": "bytes 0-{}/{}".format(mida - 1, mida),
                "Content-Length": str(mida),
                "Content-Type": "video/mp4",
            },
            timeout=120,
        )
    except Exception as e:
        return {"ok": False, "error": "Error pujant vídeo a TikTok: {}".format(e)}

    if r2.status_code not in (200, 201, 204):
        return {"ok": False, "error": "TikTok upload HTTP {}: {}".format(
            r2.status_code, r2.text[:200])}

    print("[tiktok] Publicat a TikTok (publish_id: {})".format(publish_id))
    return {"ok": True, "msg": "Publicat a TikTok.", "publish_id": publish_id}
