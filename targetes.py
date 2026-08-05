"""
targetes.py — Targeta literària local quan Gemini no pot generar imatge.

Pla B 100% gratuït: si l'API d'imatges falla (clau sense facturació, quota,
model retirat…), es dibuixa amb PIL una targeta sòbria amb el text del post
—la frase del llibre els dies de cita— a l'estil de les d'El Bon Diari.
No fa cap crida a cap API; només necessita les fonts del sistema.

El publicador la fa servir com a reserva (vegeu _imatge_publica): primer
prova Gemini i, només si es rendeix, munta la targeta. Així, el dia que la
clau torni a tenir facturació, el sistema recupera sol les imatges generades.
"""

import os
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ARREL = Path(__file__).resolve().parent
DIR_IMATGES = ARREL / "imatges_generades"

# Paleta pròpia del promotor (diferent de la d'El Bon Diari): paper càlid,
# tinta fosca i un ocre discret per als filets i l'ornament.
PAPER = (247, 242, 233)
TINTA = (32, 30, 27)
OCRE = (176, 108, 57)
GRIS = (128, 122, 112)

WEB = "sergicastillo.com"

# Mides per xarxa (mateixos formats que aspect_per_xarxa d'imatges.py)
MIDES = {
    "instagram": (1080, 1080),
    "twitter": (1600, 900),
    "linkedin": (1200, 900),
}

# Línies màximes del cos segons el format (perquè no quedi atapeït)
LINIES_MAX = {"instagram": 7, "twitter": 5, "linkedin": 6}


def _primera_font(candidats):
    return next((c for c in candidats if os.path.exists(c)), candidats[-1])


F_COS = _primera_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
])
F_CITA = _primera_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
])
F_PEU = _primera_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
])


def _font(cami, mida):
    try:
        return ImageFont.truetype(cami, mida)
    except OSError:
        return ImageFont.load_default()


def _neteja(text):
    # type: (str) -> str
    """Treu hashtags, URLs i espais sobrers del text del post."""
    t = re.sub(r"#\S+", "", text or "")
    t = re.sub(r"https?://\S+", "", t)
    t = t.replace(WEB, "")
    return "\n".join(l.strip() for l in t.splitlines()).strip()


def _cos_i_autoria(text):
    # type: (str) -> tuple
    """Separa el cos de la línia d'autoria («frase»\\n\\n— Títol) si hi és."""
    net = _neteja(text)
    m = re.search(r"\n\s*[—–-]\s*(.+?)\s*$", net)
    autoria = None
    if m:
        autoria = m.group(1)
        net = net[: m.start()].strip()
    cos = " ".join(net.split())
    cos = cos.strip().strip('«»"“”').strip()
    if len(cos) > 300:
        cos = cos[:299].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    return cos, autoria


def _ajusta(dibuix, cos, ample_util, linies_max, alcada_max):
    # type: (ImageDraw.ImageDraw, str, int, int, int) -> tuple
    """Tria la mida de lletra més gran amb què el cos cap en linies_max
    i dins de l'alçada disponible (cometa ornamental inclosa)."""
    for mida in (76, 68, 60, 54, 48, 42):
        font = _font(F_CITA, mida)
        amplada_lletra = max(1, dibuix.textlength("abcdefghij", font=font) / 10)
        linies = textwrap.wrap(cos, width=max(10, int(ample_util / amplada_lletra)))
        alcada = int(mida * 1.6) + len(linies) * int(mida * 1.32)
        if len(linies) <= linies_max and alcada <= alcada_max:
            return font, mida, linies
    return font, mida, linies[:linies_max]


def munta_targeta(text, data_iso, xarxa="instagram"):
    # type: (str, str, str) -> Path
    """Dibuixa la targeta del post i la desa al disc. Retorna el Path."""
    ample, alt = MIDES.get(xarxa, MIDES["instagram"])
    marge = ample // 11
    imatge = Image.new("RGB", (ample, alt), PAPER)
    dibuix = ImageDraw.Draw(imatge)

    cos, autoria = _cos_i_autoria(text)
    if not cos:
        cos = autoria or WEB
        autoria = None

    # Filets superior i inferior, discrets
    dibuix.line([(marge, marge), (ample - marge, marge)], fill=OCRE, width=4)
    dibuix.line([(marge, alt - marge), (ample - marge, alt - marge)], fill=OCRE, width=4)

    # Espai vertical útil: entre el filet superior i el peu (web + filet)
    peu_mida = max(24, ample // 45)
    sostre = marge + 30
    terra = alt - marge - int(peu_mida * 2.2)

    font_cos, mida, linies = _ajusta(
        dibuix, cos, ample - 2 * marge, LINIES_MAX.get(xarxa, 6),
        terra - sostre - int(76 * 1.1))  # reserva per a l'autoria
    interlinia = int(mida * 1.32)
    font_autoria = _font(F_COS, max(30, int(mida * 0.55)))
    font_ornament = _font(F_CITA, int(mida * 1.9))
    alcada_ornament = int(mida * 1.3)

    alcada_bloc = alcada_ornament + len(linies) * interlinia
    if autoria:
        alcada_bloc += int(interlinia * 0.35) + int(mida * 0.75)

    # Ornament: cometa d'obertura gran, en ocre, sobre el bloc de text.
    # Ancorada pel descendent ("md"): tota la tinta queda per sobre del punt,
    # així mai no trepitja la primera línia del cos.
    y = sostre + max(0, (terra - sostre - alcada_bloc) // 2)
    y += alcada_ornament
    dibuix.text((ample / 2, y - int(mida * 0.1)), "«",
                font=font_ornament, fill=OCRE, anchor="md")

    for linia in linies:
        dibuix.text((ample / 2, y), linia, font=font_cos, fill=TINTA, anchor="ma")
        y += interlinia
    if autoria:
        y += int(interlinia * 0.35)
        dibuix.text((ample / 2, y), "— " + autoria, font=font_autoria,
                    fill=GRIS, anchor="ma")

    # Peu: la web, petita i centrada, just sobre el filet inferior
    dibuix.text((ample / 2, alt - marge - 22), WEB,
                font=_font(F_PEU, peu_mida), fill=GRIS, anchor="ms")

    DIR_IMATGES.mkdir(exist_ok=True)
    cami = DIR_IMATGES / "{}_{}_targeta.png".format(data_iso, xarxa)
    imatge.save(cami, format="PNG")
    return cami


if __name__ == "__main__":
    import sys
    import datetime
    text = sys.argv[1] if len(sys.argv) > 1 else (
        "«Tot el que la ment pot imaginar, la matèria ho pot recordar.»\n\n"
        "— Acadèmia Gaia")
    for x in MIDES:
        p = munta_targeta(text, datetime.date.today().isoformat(), x)
        print("Targeta generada: {}".format(p))
