"""campanya_gaia_it_fr.py — Un sol ús (2026-07-13).

Programa a Buffer els posts de presentació de les edicions ITALIANA i
FRANCESA d'«Acadèmia Gaia», amb la portada de cada edició:

  - Italià  → 2026-07-15 a les 7:00 · X + LinkedIn + Instagram
  - Francès → 2026-07-16 a les 7:00 · X + LinkedIn + Instagram

Aquests dies l'anti-duplicats del preparador diari veurà que ja hi ha post
i no en crearà cap altre: la campanya ocupa la franja del post diari.

Enllaços ben posats: X/LinkedIn duen https:// (clicables); Instagram porta
«enllaç a la bio» perquè IG no fa clicables els enllaços del text.
"""

import datetime
import sys
from pathlib import Path

ARREL = Path(__file__).parent.parent
sys.path.insert(0, str(ARREL))

from publicador import (
    _buffer_graphql,
    _org_id,
    esborra_post,
    publica_post,
)

WEB_URL = "https://sergicastillo.com"
WEB_IG = "sergicastillo.com · enllaç a la bio"

AMAZON_IT = "https://www.amazon.es/dp/B0H8K9XRDB"
AMAZON_FR = "https://www.amazon.es/dp/B0H8L5QQFD"
AMAZON_IT_IG = "amazon.es/dp/B0H8K9XRDB"
AMAZON_FR_IG = "amazon.es/dp/B0H8L5QQFD"

POSTS = [
    {
        "nom": "Italià",
        "data": "2026-07-15",
        "img_cover": ARREL / "campanya" / "gaia_it_cover.png",
        "img_ig": ARREL / "campanya" / "gaia_it_ig.png",
        "twitter": (
            "«Accademia Gaia» è ora disponibile anche in italiano.\n\n"
            "Fantascienza, mistero e umorismo nella Barcellona del 2050, "
            "con una domanda inquietante sui limiti della conoscenza.\n\n"
            f"Disponibile su Amazon: {AMAZON_IT}\n"
            f"{WEB_URL}"
        ),
        "linkedin": (
            "«Accademia Gaia», il mio romanzo, è ora disponibile anche in italiano.\n\n"
            "Barcellona, 2050. Anastasia entra nell'Accademia Gaia dopo la scomparsa del suo "
            "fratello gemello. Con l'aiuto di un'umana sintetica, un robot imprevedibile e un "
            "gruppo di studenti eccentrici, comincia a decifrare un messaggio che conduce a una "
            "conoscenza proibita.\n\n"
            "Fantascienza, mistero e umorismo sull'identità, l'amicizia e i pericoli di voler "
            "sapere troppo.\n\n"
            f"Disponibile su Amazon: {AMAZON_IT}\n"
            f"Maggiori informazioni: {WEB_URL}\n\n"
            "#AccademiaGaia #fantascienza #romanzo"
        ),
        "instagram": (
            "«Accademia Gaia» — il mio romanzo, ora anche in italiano.\n\n"
            "Barcellona, 2050. Un'accademia, un fratello scomparso e un messaggio che conduce "
            "a una conoscenza proibita.\n\n"
            "Fantascienza, mistero e umorismo: cosa succede quando la conoscenza ci porta oltre "
            "ciò che la mente umana è preparata a comprendere?\n\n"
            f"Disponibile su Amazon: {AMAZON_IT_IG}\n"
            f"{WEB_IG}\n\n"
            "#AccademiaGaia #fantascienza #romanzo #libri #lettura #BookTok"
        ),
    },
    {
        "nom": "Francès",
        "data": "2026-07-16",
        "img_cover": ARREL / "campanya" / "gaia_fr_cover.png",
        "img_ig": ARREL / "campanya" / "gaia_fr_ig.png",
        "twitter": (
            "« Académie Gaïa » est désormais disponible en français.\n\n"
            "Science-fiction, mystère et humour dans la Barcelone de 2050, "
            "avec une question troublante sur les limites de la connaissance.\n\n"
            f"Sur Amazon : {AMAZON_FR}\n"
            f"{WEB_URL}"
        ),
        "linkedin": (
            "« Académie Gaïa », mon roman, est désormais disponible en français.\n\n"
            "Barcelone, 2050. Anastasia entre à l'Académie Gaïa après la disparition de son "
            "frère jumeau. Avec l'aide d'une humaine synthétique, d'un robot imprévisible et "
            "d'un groupe d'étudiants excentriques, elle commence à déchiffrer un message qui "
            "mène à une connaissance interdite.\n\n"
            "Science-fiction, mystère et humour sur l'identité, l'amitié et les dangers de "
            "vouloir trop savoir.\n\n"
            f"Disponible sur Amazon : {AMAZON_FR}\n"
            f"Plus d'informations : {WEB_URL}\n\n"
            "#AcadémieGaïa #sciencefiction #roman"
        ),
        "instagram": (
            "« Académie Gaïa » — mon roman, désormais disponible en français.\n\n"
            "Barcelone, 2050. Une académie, un frère disparu et un message qui mène à une "
            "connaissance interdite.\n\n"
            "Science-fiction, mystère et humour : que se passe-t-il quand la connaissance nous "
            "mène au-delà de ce que l'esprit humain est préparé à comprendre ?\n\n"
            f"Sur Amazon : {AMAZON_FR_IG}\n"
            f"{WEB_IG}\n\n"
            "#AcadémieGaïa #sciencefiction #roman #livres #lecture #BookTok"
        ),
    },
]

DATES = {p["data"] for p in POSTS}


def esborra_posts_dels_dies():
    """Esborra tots els posts programats a Buffer per als dies de la campanya."""
    org = _org_id()
    if not org:
        print("  ✗ No puc obtenir l'org id de Buffer.")
        return 0
    resp = _buffer_graphql(
        """
        query($i: PostsInput!) {
          posts(input: $i, first: 100) {
            edges { node { id dueAt channelService } }
          }
        }
        """,
        {"i": {"organizationId": org, "filter": {"status": ["scheduled"]}}},
    )
    edges = (((resp.get("data") or {}).get("posts") or {}).get("edges")) or []
    esborrats = 0
    for e in edges:
        n = e["node"]
        due = (n.get("dueAt") or "")[:10]
        if due in DATES:
            r = esborra_post(n["id"])
            estat = "✓" if r.get("ok") else "✗"
            print(f"  {estat} esborrat post de {n.get('channelService')} del {due} ({r})")
            if r.get("ok"):
                esborrats += 1
    return esborrats


def main():
    print("── Netejant els posts vells d'aquests dies ──", flush=True)
    esborra_posts_dels_dies()

    errors = 0
    for post in POSTS:
        print(f"\n── {post['nom']} · {post['data']} ──", flush=True)
        for canal in ("twitter", "linkedin", "instagram"):
            text = post[canal]
            if canal == "twitter" and len(text) > 280:
                print(f"  ✗ Text de X massa llarg ({len(text)} caràcters).")
                errors += 1
                continue
            imatge = post["img_ig"] if canal == "instagram" else post["img_cover"]
            print(f"  → {canal}... ", end="", flush=True)
            res = publica_post(canal, text, str(imatge), post["data"])
            if res.get("ok") and res.get("skip"):
                print(f"↷ {res.get('msg')}")
            elif res.get("ok"):
                print(f"✓ {res.get('msg')}")
            else:
                print(f"✗ {res.get('error')}")
                errors += 1
    print(f"\n=== Fet. Errors: {errors} ===")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
