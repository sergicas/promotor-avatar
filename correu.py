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


def envia_resum(data_str, items):
    """Envia el resum. `items` és una llista de dicts:
    {canal, text, imatge_url, ok, msg}. Retorna True si s'ha enviat."""
    pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    pw = "".join(c for c in pw if not c.isspace() and c != "\xa0")
    if not pw:
        print("[correu] sense GMAIL_APP_PASSWORD; no s'envia el resum.")
        return False
    if not items:
        return False

    linies = [
        "Els posts del {} ja són programats a Buffer per a les 7:00 del matí.".format(data_str),
        "",
        "Si vols revisar-los, retocar-los o aturar-ne algun, entra a Buffer:",
        BUFFER_WEB,
        "",
        "─────────────────────────────",
        "",
    ]
    for it in items:
        estat = "✓ programat" if it.get("ok") else "✗ NO programat ({})".format(it.get("msg", "error"))
        linies.append("【 {} 】 {}".format(it["canal"].upper(), estat))
        if it.get("text"):
            linies.append(it["text"])
        if it.get("imatge_url"):
            linies.append("Imatge: {}".format(it["imatge_url"]))
        linies.append("")
        linies.append("─────────────────────────────")
        linies.append("")

    msg = EmailMessage()
    msg["From"] = "Promotor Avatar <{}>".format(ADRECA)
    msg["To"] = ADRECA
    msg["Subject"] = "Posts del {} — revisa'ls abans de les 7:00".format(data_str)
    msg.set_content("\n".join(linies))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(ADRECA, pw)
            s.send_message(msg)
        print("[correu] resum enviat a {}.".format(ADRECA))
        return True
    except Exception as e:
        print("[correu] no s'ha pogut enviar el resum: {}".format(e))
        return False
