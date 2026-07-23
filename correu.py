"""
correu.py — Envia un resum diari per correu dels posts ja programats.

Després de preparar els posts de demà, s'envia a en Sergi un correu amb els
tres textos i les imatges, perquè els pugui revisar (o aturar a Buffer) abans
de les 7:00. Recupera la validació diària sense dependre del Mac.

Fa servir Gmail SMTP amb GMAIL_APP_PASSWORD (el mateix mètode que el Promotor
original). Si no hi ha la clau, no envia res (i no falla).
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

ADRECA = os.environ.get("CORREU_DESTINATARI", "sergicas@gmail.com")
BUFFER_WEB = "https://publish.buffer.com"


def _contrasenya_gmail():
    pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    return "".join(c for c in pw if not c.isspace() and c != "\xa0")


def _envia(msg):
    pw = _contrasenya_gmail()
    if not pw:
        print("[correu] sense GMAIL_APP_PASSWORD; no s'envia el correu.")
        return False
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(ADRECA, pw)
            s.send_message(msg)
        print("[correu] correu enviat a {}.".format(ADRECA))
        return True
    except Exception as e:
        print("[correu] no s'ha pogut enviar el correu: {}".format(e))
        return False


def envia_estat_cadencia(data_str, proper_dia):
    """Confirma que l'execució diària és viva encara que aquell dia no publiqui."""
    msg = EmailMessage()
    msg["From"] = "Promotor Avatar <{}>".format(ADRECA)
    msg["To"] = ADRECA
    msg["Subject"] = "Posts del {} — no toca publicar; promotor actiu".format(data_str)
    msg.set_content(
        "El promotor s'ha executat correctament.\n\n"
        "No toca preparar posts per al {} perquè la cadència és d'un post "
        "cada tres dies.\n"
        "Proper dia de publicació: {}.\n".format(data_str, proper_dia)
    )
    return _envia(msg)


def envia_resum(data_str, items):
    """Envia el resum. `items` és una llista de dicts:
    {canal, text, imatge_url, ok, msg}. Retorna True si s'ha enviat."""
    if not items:
        return False

    items_buffer = [it for it in items if it.get("canal") != "tiktok"]
    item_tiktok = next((it for it in items if it.get("canal") == "tiktok"), None)

    linies = ["Els posts del {} ja estan preparats.".format(data_str), ""]

    if items_buffer:
        linies += [
            "── Buffer (X · LinkedIn · Instagram) ──",
            "Programats per a les 7:00 del matí. Revisa'ls o atura'ls:",
            BUFFER_WEB,
            "",
        ]
        for it in items_buffer:
            if it.get("skip"):
                estat = "↷ ja existia a Buffer; duplicat omès"
            else:
                estat = "✓ programat" if it.get("ok") else "✗ NO programat ({})".format(it.get("msg", "error"))
            linies.append("【 {} 】 {}".format(it["canal"].upper(), estat))
            if it.get("text"):
                linies.append(it["text"])
            if it.get("imatge_url"):
                linies.append("Imatge: {}".format(it["imatge_url"]))
            linies += ["", "─────────────────────────────", ""]

    if item_tiktok:
        if item_tiktok.get("skip"):
            estat_tt = "↷ duplicat omès"
        else:
            estat_tt = (
                "✓ publicat (vídeo Veo 2, directe)" if item_tiktok.get("ok")
                else "✗ NO publicat — {}".format(item_tiktok.get("msg", "error"))
            )
        linies += ["── TikTok ──", estat_tt]
        if item_tiktok.get("text"):
            linies.append(item_tiktok["text"])
        linies += ["", "─────────────────────────────", ""]

    msg = EmailMessage()
    msg["From"] = "Promotor Avatar <{}>".format(ADRECA)
    msg["To"] = ADRECA
    msg["Subject"] = "Posts del {} — revisa'ls abans de les 7:00".format(data_str)
    msg.set_content("\n".join(linies))

    return _envia(msg)
