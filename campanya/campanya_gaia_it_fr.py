"""campanya_gaia_it_fr.py — Un sol ús (2026-07-13).

Programa a Buffer els posts de presentació de les edicions ITALIANA i
FRANCESA d'«Acadèmia Gaia», amb la portada de cada edició:

  - Italià  → 2026-07-15 a les 7:00 · X + LinkedIn + Instagram
  - Francès → 2026-07-16 a les 7:00 · X + LinkedIn + Instagram

Aquests dies l'anti-duplicats del preparador diari veurà que ja hi ha post
i no en crearà cap altre: la campanya ocupa la franja del post diari.
"""

import sys
from pathlib import Path

ARREL = Path(__file__).parent.parent
sys.path.insert(0, str(ARREL))

from publicador import publica_post

WEB = "sergicastillo.com"
COMPRAR_IT = "amazon.es/dp/B0H8K9XRDB"
COMPRAR_FR = "amazon.es/dp/B0H8L5QQFD"

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
            f"{COMPRAR_IT} · {WEB}"
        ),
        "linkedin": (
            "«Accademia Gaia», il mio romanzo, è ora disponibile anche in italiano.\n\n"
            "Barcellona, 2050. Anastasia entra nell'Accademia Gaia dopo la scomparsa del suo "
            "fratello gemello. Con l'aiuto di un'umana sintetica, un robot imprevedibile e un "
            "gruppo di studenti eccentrici, comincia a decifrare un messaggio che conduce a una "
            "conoscenza proibita.\n\n"
            "Fantascienza, mistero e umorismo sull'identità, l'amicizia e i pericoli di voler "
            "sapere troppo.\n\n"
            f"Disponibile su Amazon: {COMPRAR_IT}\n"
            f"Maggiori informazioni: {WEB}\n\n"
            "#AccademiaGaia #fantascienza #romanzo"
        ),
        "instagram": (
            "«Accademia Gaia» — il mio romanzo, ora anche in italiano.\n\n"
            "Barcellona, 2050. Un'accademia, un fratello scomparso e un messaggio che conduce "
            "a una conoscenza proibita.\n\n"
            "Fantascienza, mistero e umorismo: cosa succede quando la conoscenza ci porta oltre "
            "ciò che la mente umana è preparata a comprendere?\n\n"
            f"Disponibile su Amazon: {COMPRAR_IT}\n"
            f"{WEB}\n\n"
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
            f"{COMPRAR_FR} · {WEB}"
        ),
        "linkedin": (
            "« Académie Gaïa », mon roman, est désormais disponible en français.\n\n"
            "Barcelone, 2050. Anastasia entre à l'Académie Gaïa après la disparition de son "
            "frère jumeau. Avec l'aide d'une humaine synthétique, d'un robot imprévisible et "
            "d'un groupe d'étudiants excentriques, elle commence à déchiffrer un message qui "
            "mène à une connaissance interdite.\n\n"
            "Science-fiction, mystère et humour sur l'identité, l'amitié et les dangers de "
            "vouloir trop savoir.\n\n"
            f"Disponible sur Amazon : {COMPRAR_FR}\n"
            f"Plus d'informations : {WEB}\n\n"
            "#AcadémieGaïa #sciencefiction #roman"
        ),
        "instagram": (
            "« Académie Gaïa » — mon roman, désormais disponible en français.\n\n"
            "Barcelone, 2050. Une académie, un frère disparu et un message qui mène à une "
            "connaissance interdite.\n\n"
            "Science-fiction, mystère et humour : que se passe-t-il quand la connaissance nous "
            "mène au-delà de ce que l'esprit humain est préparé à comprendre ?\n\n"
            f"Disponible sur Amazon : {COMPRAR_FR}\n"
            f"{WEB}\n\n"
            "#AcadémieGaïa #sciencefiction #roman #livres #lecture #BookTok"
        ),
    },
]


def main():
    errors = 0
    for post in POSTS:
        print(f"\n── {post['nom']} · {post['data']} ──", flush=True)
        for canal in ("twitter", "linkedin", "instagram"):
            text = post[canal]
            if canal == "twitter" and len(text) > 280:
                print(f"  ✗ Text de X massa llarg ({len(text)} caràcters) — no s'envia.")
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
