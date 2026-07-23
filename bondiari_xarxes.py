#!/usr/bin/env python3
"""Publica les bones notícies del dia a Buffer des de GitHub Actions.

La comprovació anti-duplicats viu a Buffer, no al disc del Mac: així una
reexecució del workflow és segura i la publicació no depèn d'un token local.
"""

import argparse
import datetime
import os
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

API_NEWS = "https://bondiari.com/api/live-news"
XARXES = ("twitter", "linkedin", "instagram")
DIR_CARDS = Path(__file__).resolve().parent / "imatges_bondiari"

PAPER = (255, 250, 241)
TINTA = (20, 20, 20)
GRIS = (120, 116, 108)
VERMELL = (231, 42, 48)
MOSAIC = [VERMELL, (255, 224, 0), (30, 80, 160), (0, 0, 0)]

POSITIUS = (
    "recupera", "salva", "premi", "guardó", "rècord", "record", "guanya",
    "campió", "inaugura", "estrena", "torna", "descobreix", "ajuda",
    "solidaritat", "històric", "pacte", "acord", "inversió", "recerca",
    "celebra", "reconeix", "homenatge", "innovació", "projecte", "neix",
    "millora", "avança", "esperança", "protegeix", "restaura", "obre",
)
HARD_NEG = (
    "guerra", "míssil", "bomba", "atac", "atemptat", "violència", "conflicte",
    "invasió", "derrota", "crisi", "jutge", "judici", "detingut", "denúncia",
    "condemna", "presó", "corrup", "frau", "sanció", "acomiada", "incendi",
    "desnonament", "droga", "robatori", "assassin", "mort", "ferit", "víctim",
    "accident", "gaza", "ucraïna", "putin", "hamas", "israel", "trump",
    "suspèn", "suspenen", "fracàs escolar", "mitjana més baixa", "pitjor",
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


def _punt(story):
    titol = (story.get("title") or "").strip().lower()
    if not titol:
        return -100
    punts = 3 if story.get("language") == "ca" else 0
    punts += 2 * sum(1 for paraula in POSITIUS if paraula in titol)
    punts -= 4 if titol.endswith("?") else 0
    punts -= 3 if len(titol) > 95 else 0
    return punts


def es_bona(story):
    titol = (story.get("title") or "").strip().lower()
    return (
        len(titol) >= 25
        and not titol.endswith("?")
        and not any(paraula in titol for paraula in HARD_NEG)
        and _punt(story) > 0
    )


def baixa_noticies():
    resposta = requests.get(
        API_NEWS,
        timeout=30,
        headers={"user-agent": "bondiari-social/2.0"},
    )
    resposta.raise_for_status()
    return resposta.json().get("stories", [])


def reparteix(stories):
    bones = [s for s in sorted(stories, key=_punt, reverse=True) if es_bona(s)]
    lots = {xarxa: [] for xarxa in XARXES}
    for index, story in enumerate(bones):
        lots[XARXES[index % len(XARXES)]].append(story)
    return lots


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
    dibuix.text((marge, 300), "LA BONA NOTÍCIA DEL DIA", font=_font(F_ETIQUETA, 26), fill=VERMELL)

    for mida in (84, 76, 68, 60, 54):
        font_titol = _font(F_TITOL, mida)
        amplada_lletra = max(1, dibuix.textlength("abcdefghij", font=font_titol) / 10)
        linies = textwrap.wrap(titular, width=max(10, int((ample - 2 * marge) / amplada_lletra)))
        if len(linies) <= 5:
            break
    y = 350
    for linia in linies:
        dibuix.text((marge, y), linia, font=font_titol, fill=TINTA)
        y += int(mida * 1.18)
    dibuix.text((marge, alt - marge - 30), "bondiari.com", font=_font(F_ETIQUETA, 32), fill=TINTA)

    cami = DIR_CARDS / "{}_{}.png".format(dia.isoformat(), xarxa)
    imatge.save(cami)
    return cami


def _titulars(lot, limit):
    return [(s.get("title") or "").strip() for s in lot[:limit] if (s.get("title") or "").strip()]


def munta_text(xarxa, lot, dia):
    if xarxa == "twitter":
        titular = (_titulars(lot, 1) or ["Bones notícies, avui"])[0][:200]
        return "Avui a El Bon Diari 🐦\n\n{}\n\n👉 bondiari.com".format(titular)
    if xarxa == "instagram":
        bullets = "\n".join("• " + t for t in _titulars(lot, 3))
        return (
            "🐦 El Bon Diari · {data}\nLes bones notícies d'avui:\n\n{bullets}\n\n"
            "Notícies que reparen el món, no que t'ensorren el dia.\n"
            "👉 bondiari.com\n\n#bonesnotícies #elbondiari #català #optimisme #Catalunya"
        ).format(data=data_llarga(dia), bullets=bullets)
    bullets = "\n".join("• " + t for t in _titulars(lot, 4))
    return (
        "Cada dia, internet ens serveix el pitjor primer. El Bon Diari fa el contrari.\n\n"
        "Avui, per exemple:\n{bullets}\n\n"
        "Sense soroll, sense alarma. Només bones notícies, ben triades.\n"
        "👉 bondiari.com"
    ).format(bullets=bullets)


def publica_xarxa(xarxa, lot, dia, dry_run=False):
    if not lot:
        print("[{}] sense notícies aptes; no es publica.".format(xarxa))
        return False
    titular = (lot[0].get("title") or "Bones notícies, avui").strip()
    targeta = munta_targeta(titular, dia, xarxa)
    text = munta_text(xarxa, lot, dia)
    if dry_run:
        print("[{}] {} · {}".format(xarxa, titular, targeta.name))
        return True

    from publicador import publica_post

    index = XARXES.index(xarxa)
    quan = datetime.datetime.now().astimezone() + datetime.timedelta(minutes=3 + index * 3)
    resultat = publica_post(
        xarxa,
        text,
        imatge=str(targeta),
        data_str=dia.isoformat(),
        quan=quan,
    )
    if resultat.get("ok"):
        prefix = "↷" if resultat.get("skip") else "✓"
        print("[{}] {} {}".format(xarxa, prefix, resultat.get("msg", "preparat")))
        return True
    print("[{}] ✗ {}".format(xarxa, resultat.get("error", "error desconegut")))
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", help="Data YYYY-MM-DD; per defecte, avui")
    args = parser.parse_args()
    dia = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
    lots = reparteix(baixa_noticies())
    if any(not lots[xarxa] for xarxa in XARXES):
        print("[bondiari] No hi ha prou notícies aptes per cobrir les tres xarxes.")
        return 1
    resultats = [publica_xarxa(x, lots[x], dia, args.dry_run) for x in XARXES]
    return 0 if all(resultats) else 1


if __name__ == "__main__":
    raise SystemExit(main())
