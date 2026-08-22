"""Fotografies contextuals de reserva mitjançant Openverse.

Quan Gemini no pot crear una imatge (quota, facturació o incidència), aquest
mòdul cerca una fotografia CC0 o de domini públic relacionada amb la
descripció visual del post. La retalla al format de cada xarxa i la desa al
mateix directori que les imatges generades.

No s'utilitzen llicències que exigeixin atribució: només ``cc0`` i ``pdm``.
"""

import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageOps


ARREL = Path(__file__).resolve().parent
DIR_IMATGES = ARREL / "imatges_generades"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "PromotorAvatar/1.0 (https://sergicastillo.com)"

MIDES = {
    "instagram": (1080, 1080),
    "twitter": (1600, 900),
    "linkedin": (1200, 900),
}
ORDRE_XARXES = ("linkedin", "twitter", "instagram")

# Conceptes que apareixen sovint als prompts. Incloem català i anglès perquè
# la cerca continuï funcionant encara que la traducció de Gemini falli.
VOCABULARI = (
    (("arrel", "arrels", "root", "roots"), "roots"),
    (("arbre", "arbres", "tree", "trees"), "tree"),
    (("branca", "branques", "branch", "branches"), "tree branch"),
    (("tronc", "trunks", "trunk"), "tree trunk"),
    (("molsa", "molsos", "moss", "mossy"), "moss"),
    (("bosc", "forest"), "forest"),
    (("pi", "pins", "pine", "pines"), "pine trees"),
    (("llibre", "llibres", "book", "books"), "book"),
    (("biblioteca", "llibreria", "library", "bookshop"), "library"),
    (("papallona", "papallones", "butterfly", "butterflies"), "butterfly"),
    (("ala", "ales", "wing", "wings"), "wings"),
    (("rellotge", "clock", "watch"), "clock"),
    (("temps", "time"), "time"),
    (("riu", "river"), "river"),
    (("rierol", "rierols", "stream", "creek"), "mountain stream"),
    (("aigua", "water"), "water"),
    (("mar", "sea", "ocean"), "sea"),
    (("finestra", "window"), "window"),
    (("pluja", "rain"), "rain"),
    (("fanal", "lamp", "streetlamp", "lantern"), "streetlamp"),
    (("carrer", "street"), "street"),
    (("nit", "night"), "night"),
    (("mapa", "map"), "map"),
    (("cami", "path", "road"), "path"),
    (("pedra", "stone", "rock"), "stone"),
    (("gel", "ice"), "ice"),
    (("neu", "snow"), "snow"),
    (("ploma", "feather", "quill"), "quill"),
    (("clau", "key"), "key"),
    (("porta", "door"), "door"),
    (("balanca", "balance", "scales"), "scales"),
    (("cervell", "brain"), "brain"),
    (("neurona", "neurones", "neuron", "neurons"), "neurons"),
    (("robot", "robotic"), "robot"),
    (("metall", "metal"), "metal"),
    (("flor", "flors", "flower", "flowers"), "flowers"),
    (("llum", "light"), "light"),
    (("ombra", "ombres", "shadow", "shadows"), "shadows"),
)

PARAULES_BUIDES = {
    "about", "above", "across", "against", "along", "amid", "among",
    "around", "atmosphere", "background", "beneath", "beside", "between",
    "cinematic", "close", "dawn", "detail", "evening", "gentle", "golden",
    "into", "light", "lighting", "morning", "natural", "near", "old",
    "over", "photorealistic", "scene", "soft", "still", "sunlight", "the",
    "through", "under", "warm", "with", "without",
}


def _sense_accents(text):
    normalitzat = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in normalitzat if unicodedata.category(c) != "Mn")


def termes_cerca(descripcio, prompt_en=""):
    """Retorna 1-4 termes visuals concrets en anglès."""
    conjunt = _sense_accents("{} {}".format(descripcio or "", prompt_en or ""))
    paraules = set(re.findall(r"[a-z]+", conjunt))
    termes = []
    for variants, terme in VOCABULARI:
        if any(_sense_accents(v) in paraules for v in variants) and terme not in termes:
            termes.append(terme)
        if len(termes) == 4:
            return termes

    # Si el vocabulari no és suficient, aprofitem els primers substantius
    # probables del prompt anglès. Les cerques es faran progressivament més
    # curtes, de manera que un terme massa específic no bloqueja el resultat.
    for paraula in re.findall(r"[a-z]+", _sense_accents(prompt_en)):
        if len(paraula) < 4 or paraula in PARAULES_BUIDES or paraula in termes:
            continue
        termes.append(paraula)
        if len(termes) == 4:
            break
    return termes or ["book"]


def _consultes_progressives(termes):
    consultes = []
    for n in range(min(4, len(termes)), 0, -1):
        consulta = " ".join(termes[:n])
        if consulta not in consultes:
            consultes.append(consulta)
    return consultes


def _identificadors_resultat(resultat):
    """Identificadors estables per reconèixer una mateixa fotografia.

    Openverse pot retornar la mateixa obra amb URLs de fitxer diferents. La
    pàgina d'origen i els identificadors del proveïdor permeten excloure-la
    igualment dels altres canals del mateix dia.
    """
    camps = (
        "id", "foreign_identifier", "foreign_landing_url", "url",
    )
    return {
        str(resultat.get(camp)).strip()
        for camp in camps
        if resultat.get(camp)
    }


def _xarxa_assignada(resultat):
    """Partició estable: una foto d'Openverse pertany a una sola xarxa.

    Això continua impedint repeticions fins i tot en un reintent executat en
    un procés nou, quan les metadades locals de la passada anterior ja no hi
    són. Si una cerca molt pobra no té cap foto del grup de la xarxa, encara
    es permet el conjunt complet i l'exclusió per metadades fa de segona xarxa.
    """
    identificadors = sorted(_identificadors_resultat(resultat))
    clau = identificadors[0] if identificadors else ""
    bucket = int(hashlib.sha256(clau.encode("utf-8")).hexdigest()[:8], 16)
    return ORDRE_XARXES[bucket % len(ORDRE_XARXES)]


def _origens_usats(data_iso, xarxa_actual=None):
    """Fotos ja assignades a altres xarxes de la mateixa data."""
    usats = set()
    patro = "{}_{}_oberta.json".format(data_iso, "*")
    for cami in DIR_IMATGES.glob(patro):
        if xarxa_actual and cami.name == "{}_{}_oberta.json".format(
                data_iso, xarxa_actual):
            continue
        try:
            metadades = json.loads(cami.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        for camp in ("identificador", "origen", "url"):
            if metadades.get(camp):
                usats.add(str(metadades[camp]).strip())
    return usats


def _tria_resultat(resultats, data_iso, xarxa, exclosos=None):
    exclosos = set(exclosos or ())
    valids = [
        r for r in resultats
        if r.get("url") and r.get("license") in ("cc0", "pdm")
        and not r.get("mature")
        and not (_identificadors_resultat(r) & exclosos)
    ]
    if not valids:
        return None

    assignats = [r for r in valids if _xarxa_assignada(r) == xarxa]
    if assignats:
        valids = assignats

    ample_desti, alt_desti = MIDES.get(xarxa, MIDES["instagram"])
    ratio_desti = ample_desti / alt_desti

    def puntuacio(r):
        ample = r.get("width") or 0
        alt = r.get("height") or 0
        ratio = ample / alt if ample and alt else ratio_desti
        prou_gran = 1 if ample >= 900 and alt >= 700 else 0
        return (prou_gran, -abs(ratio - ratio_desti), ample * alt)

    valids.sort(key=puntuacio, reverse=True)
    candidats = valids[: min(5, len(valids))]
    llavor = "{}:{}".format(data_iso, xarxa).encode("utf-8")
    index = int(hashlib.sha256(llavor).hexdigest()[:8], 16) % len(candidats)
    return candidats[index]


def _descarrega_i_retalla(resultat, cami, xarxa):
    urls = [resultat.get("url"), resultat.get("thumbnail")]
    for url in urls:
        if not url:
            continue
        try:
            resposta = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=40,
            )
            resposta.raise_for_status()
            if len(resposta.content) > 20 * 1024 * 1024:
                continue
            with Image.open(io.BytesIO(resposta.content)) as original:
                original = ImageOps.exif_transpose(original).convert("RGB")
                final = ImageOps.fit(
                    original, MIDES.get(xarxa, MIDES["instagram"]),
                    method=Image.Resampling.LANCZOS,
                )
                final.save(cami, "PNG", optimize=True)
            return True
        except Exception:
            continue
    return False


def busca_imatge_oberta(descripcio, data_iso, xarxa="instagram"):
    """Cerca i prepara una fotografia CC0/PDM relacionada amb el post."""
    DIR_IMATGES.mkdir(exist_ok=True)
    cami = DIR_IMATGES / "{}_{}_oberta.png".format(data_iso, xarxa)
    if cami.exists():
        return cami

    # Una fotografia només pot aparèixer en una de les tres xarxes del dia.
    # Les metadades persisteixen entre crides, de manera que també funciona si
    # cada canal necessita una consulta progressiva diferent.
    exclosos = _origens_usats(data_iso, xarxa)

    try:
        # La traducció ja està preparada per crear una escena fidel; també ens
        # dona vocabulari anglès de qualitat per buscar la fotografia.
        from imatges import _tradueix_a_prompt
        prompt_en = _tradueix_a_prompt(descripcio)
    except Exception:
        prompt_en = ""

    termes = termes_cerca(descripcio, prompt_en)
    for consulta in _consultes_progressives(termes):
        try:
            resposta = requests.get(
                OPENVERSE_API,
                params={
                    "q": consulta,
                    "license": "cc0,pdm",
                    "page_size": 20,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=25,
            )
            resposta.raise_for_status()
            resultat = _tria_resultat(
                resposta.json().get("results", []), data_iso, xarxa, exclosos,
            )
        except Exception as exc:
            print("[imatges-obertes] cerca fallida per '{}': {}".format(consulta, exc))
            continue

        if resultat and _descarrega_i_retalla(resultat, cami, xarxa):
            metadades = {
                "consulta": consulta,
                "titol": resultat.get("title"),
                "autor": resultat.get("creator"),
                "llicencia": resultat.get("license"),
                "identificador": (
                    resultat.get("id") or resultat.get("foreign_identifier")
                ),
                "origen": resultat.get("foreign_landing_url"),
                "url": resultat.get("url"),
            }
            cami.with_suffix(".json").write_text(
                json.dumps(metadades, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("[imatges-obertes] {}: fotografia '{}' ({})".format(
                xarxa, resultat.get("title") or consulta,
                (resultat.get("license") or "").upper(),
            ))
            return cami

    return None
