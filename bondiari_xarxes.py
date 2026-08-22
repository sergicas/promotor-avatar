#!/usr/bin/env python3
"""Publica la capçalera visible d'El Bon Diari a les tres xarxes.

La notícia es llegeix de l'API que alimenta la portada, es verifica contra
l'article canònic de bondiari.com i es publica a Buffer. Un registre versionat
per URL i plataforma permet reprendre execucions parcials sense duplicar-les.
"""

import argparse
import datetime
import html
import io
import json
import os
import re
import textwrap
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

API_NEWS = "https://bondiari.com/api/live-news"
BASE_URL = "https://bondiari.com"
XARXES = ("twitter", "linkedin", "instagram")
DIR_CARDS = Path(__file__).resolve().parent / "imatges_bondiari"
FITXER_REGISTRE = Path(__file__).resolve().parent / "dades" / "bondiari-publicacions.json"

PAPER = (255, 250, 241)
TINTA = (20, 20, 20)
GRIS = (120, 116, 108)
VERMELL = (231, 42, 48)
MOSAIC = [VERMELL, (255, 224, 0), (30, 80, 160), (0, 0, 0)]
MIDES_XARXA = {
    "instagram": (1080, 1080),
    "twitter": (1600, 900),
    "linkedin": (1200, 900),
}

MARQUES_COMERCIALS = (
    "audi", "bmw", "citroën", "cupra", "fiat", "ford", "honda", "hyundai",
    "kia", "lexus", "mazda", "mercedes", "nissan", "opel", "peugeot",
    "renault", "seat", "skoda", "tesla", "toyota", "volkswagen", "volvo",
)
PRODUCTES_COMERCIALS = (
    "automòbil", "coche", "cotxe", "model", "modelo", "smartphone", "suv",
    "telèfon", "vehicle", "vehículo",
)
RECLAMS_COMERCIALS = (
    "accessible", "autonomía", "autonomia", "combina", "descompte", "descuento",
    "dia a dia", "día a día", "facilita", "gran autonomia", "gran autonomía",
    "llança", "nuevo", "nou", "oferta", "pràctiques", "prácticas", "preu",
    "precio", "presenta", "promoció", "promoción", "solucions", "soluciones",
)
ETIQUETES_PUBLICITARIES = (
    "advertorial", "branded content", "contingut patrocinat", "native advertising",
    "patrocinat", "publicitat", "sponsored",
)


def _primera_font(candidats):
    return next((c for c in candidats if os.path.exists(c)), candidats[-1])


F_TITOL = _primera_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
])
F_ETIQUETA = _primera_font([
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
])


def _font(cami, mida):
    try:
        return ImageFont.truetype(cami, mida)
    except Exception:
        return ImageFont.load_default()


class _ArticleParser(HTMLParser):
    """Extreu el canònic, l'h1 i els paràgrafs del HTML prerenderitzat."""

    def __init__(self):
        super().__init__()
        self.canonical = ""
        self.in_article = False
        self.depth = 0
        self.capturing = None
        self.buffer = []
        self.title = ""
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "")
        if tag == "article":
            self.in_article = True
            self.depth = 1
            return
        if self.in_article:
            self.depth += 1
            if tag in ("h1", "p") and self.capturing is None:
                self.capturing = tag
                self.buffer = []

    def handle_endtag(self, tag):
        if self.in_article and self.capturing == tag:
            text = " ".join("".join(self.buffer).split())
            if tag == "h1":
                self.title = text
            elif text:
                self.paragraphs.append(text)
            self.capturing = None
            self.buffer = []
        if self.in_article:
            self.depth -= 1
            if tag == "article" or self.depth <= 0:
                self.in_article = False
                self.depth = 0

    def handle_data(self, data):
        if self.capturing:
            self.buffer.append(data)


def _normalitza_text(text):
    return " ".join(html.unescape(text or "").split()).strip()


def _id_noticia(story):
    image_url = story.get("imageUrl") or ""
    match = re.search(r"/api/story-image/([^/?#]+)", image_url)
    if not match:
        raise ValueError("La capçalera no porta un identificador de Bondiari vàlid.")
    return match.group(1)


def es_contingut_publicitari(story):
    """Detecta etiquetes explícites i titulars de producte amb to comercial."""
    serialitzat = json.dumps(story, ensure_ascii=False).lower()
    if any(etiqueta in serialitzat for etiqueta in ETIQUETES_PUBLICITARIES):
        return True
    text = " ".join(
        _normalitza_text(story.get(camp)).lower()
        for camp in ("title", "summary", "impact")
    )
    te_marca = any(re.search(r"\b{}\b".format(re.escape(marca)), text) for marca in MARQUES_COMERCIALS)
    te_producte = any(re.search(r"\b{}\b".format(re.escape(producte)), text) for producte in PRODUCTES_COMERCIALS)
    te_reclam = any(reclam in text for reclam in RECLAMS_COMERCIALS)
    return te_marca and te_producte and te_reclam


def selecciona_capcalera(stories):
    """Retorna la primera capçalera editorial i descarta anuncis."""
    if not stories:
        raise ValueError("La portada de Bondiari no conté cap notícia.")
    for candidata in stories:
        story = dict(candidata)
        titular = _normalitza_text(story.get("title"))
        if not titular or es_contingut_publicitari(story):
            continue
        story["title"] = titular
        story["canonical_url"] = "{}/noticia/{}".format(BASE_URL, _id_noticia(story))
        return story
    raise ValueError("La portada només conté anuncis o contingut promocional; no es publica.")


def baixa_capcalera():
    resposta = requests.get(
        API_NEWS,
        timeout=30,
        headers={"user-agent": "bondiari-social/3.0"},
    )
    resposta.raise_for_status()
    return selecciona_capcalera(resposta.json().get("stories", []))


def _frases(paragraphs, limit=3):
    resultat = []
    for paragraph in paragraphs:
        paragraph = _normalitza_text(paragraph)
        if not paragraph or paragraph.lower().startswith("font:"):
            continue
        for frase in re.split(r"(?<=[.!?])\s+", paragraph):
            frase = frase.strip()
            if len(frase) < 20 or frase in resultat:
                continue
            resultat.append(frase)
            if len(resultat) == limit:
                return resultat
    return resultat


def verifica_article(story):
    """Contrasta titular, canònic i 2-3 dades directament a l'article."""
    url = story["canonical_url"]
    resposta = requests.get(
        url,
        timeout=30,
        headers={"user-agent": "bondiari-social/3.0"},
    )
    resposta.raise_for_status()
    parser = _ArticleParser()
    parser.feed(resposta.text)

    if _normalitza_text(parser.title) != story["title"]:
        raise ValueError("El titular de la portada no coincideix amb el de l'article.")
    if parser.canonical.rstrip("/") != url.rstrip("/"):
        raise ValueError("L'enllaç canònic de l'article no coincideix amb la portada.")

    facts = _frases(parser.paragraphs, limit=3)
    if len(facts) < 2:
        raise ValueError("L'article no conté prou dades verificables per publicar-lo.")
    verificat = dict(story)
    verificat["facts"] = facts
    return verificat


def carrega_registre(cami=FITXER_REGISTRE):
    try:
        with open(cami, "r", encoding="utf-8") as fitxer:
            registre = json.load(fitxer)
        if not isinstance(registre.get("urls"), dict):
            raise ValueError("registre invàlid")
        return registre
    except (OSError, ValueError, json.JSONDecodeError):
        return {"version": 1, "urls": {}}


def desa_registre(registre, cami=FITXER_REGISTRE):
    cami.parent.mkdir(parents=True, exist_ok=True)
    temporal = cami.with_suffix(cami.suffix + ".tmp")
    with open(temporal, "w", encoding="utf-8") as fitxer:
        json.dump(registre, fitxer, ensure_ascii=False, indent=2, sort_keys=True)
        fitxer.write("\n")
    temporal.replace(cami)


def ja_publicat(registre, url, xarxa):
    return xarxa in (
        ((registre.get("urls") or {}).get(url) or {}).get("published") or {}
    )


def registra_publicacio(registre, story, xarxa, resultat, ara=None):
    ara = ara or datetime.datetime.now(datetime.timezone.utc)
    entrada = registre.setdefault("urls", {}).setdefault(
        story["canonical_url"],
        {"title": story["title"], "published": {}},
    )
    entrada["title"] = story["title"]
    entrada.setdefault("published", {})[xarxa] = {
        "at": ara.astimezone(datetime.timezone.utc).isoformat(),
        "buffer_id": resultat.get("id", ""),
    }


def data_llarga(dia):
    mesos = [
        "gener", "febrer", "març", "abril", "maig", "juny", "juliol",
        "agost", "setembre", "octubre", "novembre", "desembre",
    ]
    return "{} de {} del {}".format(dia.day, mesos[dia.month - 1], dia.year)


def munta_targeta(titular, dia, xarxa):
    DIR_CARDS.mkdir(exist_ok=True)
    ample = alt = 1080
    marge = 96
    imatge = Image.new("RGB", (ample, alt), PAPER)
    dibuix = ImageDraw.Draw(imatge)
    x = marge
    for color in MOSAIC:
        dibuix.rectangle([x, marge, x + 30, marge + 30], fill=color)
        x += 36
    dibuix.text((marge, marge + 46), "EL BON DIARI", font=_font(F_ETIQUETA, 34), fill=TINTA)
    dibuix.text((marge, marge + 90), data_llarga(dia), font=_font(F_ETIQUETA, 26), fill=GRIS)
    dibuix.line([(marge, marge + 132), (ample - marge, marge + 132)], fill=TINTA, width=3)
    dibuix.text((marge, 300), "LA NOTÍCIA DE CAPÇALERA", font=_font(F_ETIQUETA, 26), fill=VERMELL)

    for mida in (84, 76, 68, 60, 54):
        font_titol = _font(F_TITOL, mida)
        amplada_lletra = max(1, dibuix.textlength("abcdefghij", font=font_titol) / 10)
        linies = textwrap.wrap(titular, width=max(10, int((ample - 2 * marge) / amplada_lletra)))
        if len(linies) <= 5:
            break
    y = 350
    for linia in linies[:5]:
        dibuix.text((marge, y), linia, font=font_titol, fill=TINTA)
        y += int(mida * 1.18)
    dibuix.text((marge, alt - marge - 30), "bondiari.com", font=_font(F_ETIQUETA, 32), fill=TINTA)

    cami = DIR_CARDS / "{}_{}.png".format(dia.isoformat(), xarxa)
    imatge.save(cami, format="PNG")
    return cami


def prepara_imatge_noticia(story, dia, xarxa):
    """Baixa la imatge real de la notícia i l'adapta a cada xarxa.

    Si la font no es pot descarregar, recorre a la mateixa cerca d'imatges
    obertes contextuals que els posts literaris i, finalment, a una
    il·lustració simbòlica sense text. La targeta amb titular ja no forma part
    del flux de publicació.
    """
    DIR_CARDS.mkdir(exist_ok=True)
    cami = DIR_CARDS / "{}_{}_noticia.png".format(dia.isoformat(), xarxa)
    if cami.exists():
        return cami

    image_url = urljoin(BASE_URL + "/", story.get("imageUrl") or "")
    if image_url:
        try:
            resposta = requests.get(
                image_url,
                timeout=40,
                headers={"user-agent": "bondiari-social/4.0"},
            )
            resposta.raise_for_status()
            with Image.open(io.BytesIO(resposta.content)) as original:
                original = ImageOps.exif_transpose(original).convert("RGB")
                final = ImageOps.fit(
                    original,
                    MIDES_XARXA.get(xarxa, MIDES_XARXA["instagram"]),
                    method=Image.Resampling.LANCZOS,
                )
                final.save(cami, "PNG", optimize=True)
            print("[{}] imatge real de la notícia preparada.".format(xarxa))
            return cami
        except Exception as exc:
            print("[{}] no s'ha pogut baixar la imatge de la notícia: {}".format(
                xarxa, exc,
            ))

    descripcio = " ".join(
        [story.get("title") or ""] + list(story.get("facts") or [])[:1]
    ).strip()
    clau_data = "{}-bondiari".format(dia.isoformat())
    try:
        from imatges_obertes import busca_imatge_oberta
        alternativa = busca_imatge_oberta(descripcio, clau_data, xarxa)
        if alternativa:
            return alternativa
    except Exception as exc:
        print("[{}] la cerca d'imatge oberta ha fallat: {}".format(xarxa, exc))

    from illustracions import genera_illustracio
    return genera_illustracio(descripcio, clau_data, xarxa)


def _retalla(text, maxim):
    text = _normalitza_text(text)
    if len(text) <= maxim:
        return text
    return text[: max(1, maxim - 1)].rstrip(" ,.;:") + "…"


def munta_text(xarxa, story, dia):
    titular = story["title"]
    url = story["canonical_url"]
    facts = story["facts"]
    if xarxa == "twitter":
        cua = "\n{}\n#Bondiari #Catalunya".format(url)
        disponible = 280 - len(cua) - 2
        cos = titular
        if len(cos) + 2 + len(facts[0]) <= disponible:
            cos += "\n\n" + facts[0]
        else:
            cos = _retalla(cos, disponible)
        return cos + cua
    if xarxa == "instagram":
        return (
            "{titular}\n\n{fet}\n\nFont: El Bon Diari. Llegeix la notícia completa a "
            "{url}\n\n#Bondiari #ElBonDiari #Catalunya #Notícies #Actualitat"
        ).format(titular=titular, fet=facts[0], url=url)
    return (
        "{titular}\n\n{resum}\n\nFont: El Bon Diari\n{url}\n\n"
        "#Bondiari #Catalunya #Actualitat"
    ).format(titular=titular, resum=" ".join(facts[:3]), url=url)


def publica_xarxa(xarxa, story, dia, registre, dry_run=False):
    url = story["canonical_url"]
    if ja_publicat(registre, url, xarxa):
        print("[{}] ↷ URL ja publicat; no es duplica.".format(xarxa))
        return {"platform": xarxa, "status": "already"}

    imatge = prepara_imatge_noticia(story, dia, xarxa)
    text = munta_text(xarxa, story, dia)
    if dry_run:
        print("[{}] ✓ validat · {} · {} caràcters".format(xarxa, imatge.name, len(text)))
        return {"platform": xarxa, "status": "validated"}

    from publicador import publica_post

    quan = datetime.datetime.now().astimezone() + datetime.timedelta(minutes=2)
    resultat = publica_post(
        xarxa,
        text,
        imatge=str(imatge),
        data_str=dia.isoformat(),
        quan=quan,
        evitar_duplicat_diari=False,
    )
    if resultat.get("ok"):
        registra_publicacio(registre, story, xarxa, resultat)
        desa_registre(registre)
        print("[{}] ✓ {}".format(xarxa, resultat.get("msg", "preparat")))
        return {"platform": xarxa, "status": "published", "id": resultat.get("id", "")}
    error = resultat.get("error", "error desconegut")
    print("[{}] ✗ {}".format(xarxa, error))
    return {"platform": xarxa, "status": "failed", "error": error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", help="Data YYYY-MM-DD; per defecte, avui")
    args = parser.parse_args()
    dia = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()

    try:
        story = verifica_article(baixa_capcalera())
    except Exception as error:
        print("[bondiari] ✗ No s'ha pogut verificar la capçalera: {}".format(error))
        return 1

    print("[bondiari] Capçalera: {}".format(story["title"]))
    print("[bondiari] URL: {}".format(story["canonical_url"]))
    for index, fact in enumerate(story["facts"], 1):
        print("[bondiari] Dada {}: {}".format(index, fact))

    registre = carrega_registre()
    resultats = [publica_xarxa(x, story, dia, registre, args.dry_run) for x in XARXES]
    estats = {r["status"] for r in resultats}
    if args.dry_run:
        return 0 if estats <= {"validated", "already"} else 1
    complet = estats <= {"published", "already"}
    print("[bondiari] ESTAT_EXECUCIO: {}".format("PUBLICAT" if complet else "PARCIAL"))
    return 0 if complet else 1


if __name__ == "__main__":
    raise SystemExit(main())
