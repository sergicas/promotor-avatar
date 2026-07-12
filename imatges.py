"""
imatges.py — Generació d'imatges amb Gemini (Nano Banana 2).

Donada una descripció catalana (la que genera Gemini al camp `imatge`
del post d'Instagram), genera una imatge fotorealista i la desa al disc
sota `imatges_generades/<data>_<xarxa>.png`. Retorna el Path local.

Requereix:
  - GEMINI_API_KEY amb facturació activa (la generació d'imatges és de pagament)
  - Cost aproximat: ~$0.02/imatge (1 imatge/dia ≈ 0.60€/mes)

Estil base de les imatges (perquè el feed tingui coherència visual):
  fotorealista, llum natural, tons càlids, composició literària/sòbria.
"""

import base64
import os
import re
import time
from pathlib import Path

import requests

from config import get_key

# Reintents: Imagen falla de tant en tant (resposta buida {}, blip de xarxa).
# Ho tornem a provar unes quantes vegades abans de rendir-nos.
REINTENTS_IMATGE = 3
ESPERA_ENTRE_INTENTS = (5, 15, 30)  # segons, creixent

ARREL = Path(__file__).resolve().parent
DIR_IMATGES = ARREL / "imatges_generades"

# Imagen 4 va ser retirat per Google el juny-juliol de 2026. El substitut és
# la família d'imatge de Gemini ("Nano Banana"). Es fa servir Nano Banana 2
# (gemini-3.1-flash-image, estable, ràpid i pensat per a alt volum), via
# l'endpoint generateContent (l'antic :predict era exclusiu d'Imagen).
# Es pot canviar sense tocar codi amb la variable d'entorn GEMINI_IMAGE_MODEL.
MODEL_IMATGE = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
ENDPOINT_IMATGE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + MODEL_IMATGE + ":generateContent"
)

# Model petit per a la traducció del prompt (una frase): el flash-lite estable.
MODEL_TRADUCCIO = os.environ.get("GEMINI_LITE_MODEL", "gemini-3.1-flash-lite")

# Estil visual comú perquè el feed tingui coherència de marca.
# Sense persones (les figures humanes provoquen censura o imatges genèriques),
# però pintant FIDELMENT l'escena descrita (objectes, natura, llocs).
ESTIL_BASE = (
    "photorealistic, soft natural lighting, warm tones, literary mood, "
    "no people, no humans, no human figures, no faces, no hands, no text overlay"
)


def _tradueix_a_prompt(descripcio_ca):
    # type: (str) -> str
    """Converteix la descripció catalana a un prompt anglès per al model d'imatge.
    Fa servir Gemini text per a una traducció ràpida i creativa."""
    desc = descripcio_ca.strip().lstrip("[").rstrip("]")
    api_key = get_key("GEMINI_API_KEY")
    if not api_key:
        return desc

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + MODEL_TRADUCCIO + ":generateContent?key=" + api_key
        )
        prompt = (
            "Converteix aquesta descripció catalana en un prompt en anglès per a "
            "un generador d'imatges. Pinta FIDELMENT l'escena descrita "
            "(els objectes, la natura, el lloc i l'atmosfera). REGLA ABSOLUTA: "
            "l'escena NO pot contenir cap persona, ni mans, ni cares, ni siluetes "
            "ni figures humanes. Si la descripció menciona una persona o una part "
            "del cos, substitueix-la per l'OBJECTE simbòlic central de l'escena "
            "(p. ex. 'una noia amb ales de papallona' → 'unes ales de papallona "
            "iridescents'; 'una mà robòtica' → 'un braç mecànic de metall'). "
            "Conserva la resta de l'escena tal com es descriu. Format: una frase "
            "descriptiva de 15-25 paraules, sense puntuació final, sense 'a photo of'. "
            "Retorna NOMÉS la frase.\n\n"
            "Descripció: " + desc
        )
        r = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.5,
                    # thinkingBudget era un paràmetre de l'era Gemini 2.5; els
                    # models 3.x el rebutgen. Límit ampli perquè el raonament
                    # intern no trunqui la frase de sortida.
                    "maxOutputTokens": 1000,
                },
            },
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
            txt = (parts[0].get("text") or "").strip()
            txt = re.sub(r"^[\"'`*-]+|[\"'`*-]+$", "", txt).strip()
            if txt and len(txt) < 200:
                return txt
    except Exception:
        pass
    return desc


def genera_imatge(descripcio_ca, data_iso, xarxa="instagram", aspect_ratio="1:1"):
    # type: (str, str, str, str) -> Path | None
    """Genera una imatge per a la xarxa donada i la desa al disc.

    Args:
        descripcio_ca: descripció catalana de l'escena.
        data_iso: data ISO 'YYYY-MM-DD' (per nomenar el fitxer i cachejar).
        xarxa: 'instagram', 'twitter', 'linkedin'.
        aspect_ratio: "1:1", "16:9", "9:16", "3:4", "4:3".

    Returns:
        Path del fitxer generat, o None si ha fallat.
    """
    api_key = get_key("GEMINI_API_KEY")
    if not api_key:
        print("[imatges] Falta GEMINI_API_KEY; no es pot generar la imatge.")
        return None

    DIR_IMATGES.mkdir(exist_ok=True)
    cami = DIR_IMATGES / "{}_{}.png".format(data_iso, xarxa)
    if cami.exists():
        return cami  # ja generada (caché)

    prompt_en = _tradueix_a_prompt(descripcio_ca)
    prompt_complet = "{}, {}".format(prompt_en, ESTIL_BASE)

    for intent in range(1, REINTENTS_IMATGE + 1):
        motiu = None  # per què ha fallat aquest intent (None = èxit)
        try:
            r = requests.post(
                ENDPOINT_IMATGE + "?key=" + api_key,
                json={
                    "contents": [{"parts": [{"text": prompt_complet}]}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"],
                        "imageConfig": {"aspectRatio": aspect_ratio},
                    },
                },
                timeout=120,
            )
            if r.status_code != 200:
                motiu = "Error API ({}): {}".format(r.status_code, r.text[:150])
            else:
                data = r.json()
                parts = (data.get("candidates", [{}])[0]
                             .get("content", {}).get("parts", []))
                b64 = next((p["inlineData"]["data"] for p in parts
                            if isinstance(p.get("inlineData"), dict)
                            and p["inlineData"].get("data")), None)
                if not b64:
                    motiu = "resposta sense imatge: {}".format(str(data)[:150])
                else:
                    cami.write_bytes(base64.b64decode(b64))
                    return cami
        except Exception as e:
            motiu = "excepció: {}".format(e)

        # Ha fallat aquest intent: esperar i tornar-ho a provar (si en queden)
        if intent < REINTENTS_IMATGE:
            espera = ESPERA_ENTRE_INTENTS[min(intent - 1, len(ESPERA_ENTRE_INTENTS) - 1)]
            print("[imatges] {} (intent {}/{}); reintent en {}s".format(
                motiu, intent, REINTENTS_IMATGE, espera))
            time.sleep(espera)
        else:
            print("[imatges] {} (intent {}/{}); em rendeixo.".format(
                motiu, intent, REINTENTS_IMATGE))

    return None


def aspect_per_xarxa(xarxa):
    # type: (str) -> str
    """Format d'imatge recomanat per cada xarxa (perquè cada xarxa en tingui
    una de pròpia i ben enquadrada)."""
    return {
        "twitter": "16:9",   # horitzontal, com es veu a la línia de temps d'X
        "linkedin": "4:3",   # lleugerament horitzontal, sòbria
        "instagram": "1:1",  # quadrada, format clàssic d'IG
    }.get(xarxa, "1:1")


if __name__ == "__main__":
    import sys
    desc = sys.argv[1] if len(sys.argv) > 1 else "una llibreria antiga amb llum de tarda"
    import datetime
    p = genera_imatge(desc, datetime.date.today().isoformat())
    print("Imatge generada: {}".format(p))