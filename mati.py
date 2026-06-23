"""
mati.py — Execució automàtica del matí (sense obrir el tauler).

Genera els posts de DEMÀ i els deixa programats a Buffer per a les 7:00
del seu dia: LinkedIn, X i Instagram (amb imatge). Respecta l'anti-
duplicats: si un canal ja s'ha enviat per a aquell dia, se salta.

Per què demà i no avui: la sortida és cada dia a les 7:00 i aquesta
execució corre a les 7:30 — el que es prepara avui surt l'endemà al matí,
amb la data correcta. No cal que el Mac estigui engegat a les 7:00:
Buffer publica sol des del núvol.

S'executa cada matí a les 7:30 via launchd (com.sergi.promotor-avatar),
que obre mati-automatic.command amb Terminal. Es fa així perquè launchd
no té permís per llegir ~/Documents (protecció TCC de macOS), però
Terminal sí.
"""

import datetime
import socket
import sys
import time

from promotor import PLATAFORMES, _ja_publicat, _marcar_publicat, _obtenir_posts_dia
from publicador import publica_post

# Si una passada acaba amb errors (p. ex. una caiguda de xarxa més llarga),
# es torna a provar sencera. Com que els canals ja fets se salten, repetir
# no duplica res. Esperes llargues perquè el matí hi ha marge fins a les 7:00.
REINTENTS_MATI = 3
ESPERA_MATI = (120, 300)  # segons entre passades fallides

# A les 7:30 el Mac es desperta del son per fer la tasca, però el Wi-Fi pot
# trigar a reconnectar-se. Abans de res, esperem que internet sigui realment
# accessible (la causa real dels errors "Gemini no respon" del matí).
SERVIDORS_CLAU = [
    ("generativelanguage.googleapis.com", 443),  # Gemini / Imagen
    ("api.buffer.com", 443),                     # Buffer
]
ESPERA_XARXA_INTENTS = 30      # fins a 30 intents…
ESPERA_XARXA_INTERVAL = 10     # …cada 10s = fins a 5 minuts esperant la xarxa


def espera_xarxa():
    """Espera que els servidors clau siguin accessibles (Wi-Fi reconnectat).
    Retorna True quan hi ha connexió, False si s'esgota el temps."""
    for intent in range(1, ESPERA_XARXA_INTENTS + 1):
        accessibles = True
        for host, port in SERVIDORS_CLAU:
            try:
                socket.create_connection((host, port), timeout=8).close()
            except OSError:
                accessibles = False
                break
        if accessibles:
            if intent > 1:
                print("✓ Internet a punt (després de {} intents).".format(intent))
            return True
        if intent < ESPERA_XARXA_INTENTS:
            print("… esperant internet (intent {}/{}); el Wi-Fi encara no respon, "
                  "torno a provar en {}s".format(intent, ESPERA_XARXA_INTENTS, ESPERA_XARXA_INTERVAL))
            time.sleep(ESPERA_XARXA_INTERVAL)
    print("✗ Internet no disponible després de {} minuts d'espera.".format(
        ESPERA_XARXA_INTENTS * ESPERA_XARXA_INTERVAL // 60))
    return False


def executa():
    dema = datetime.date.today() + datetime.timedelta(days=1)
    data_str = dema.isoformat()
    ara = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    print("── Promotor Avatar · ara: {} · preparant els posts del {} ──".format(ara, data_str))

    posts = _obtenir_posts_dia(data_str)
    if "error" in posts:
        print("✗ No s'han pogut generar els posts: {}".format(posts["error"]))
        return 1

    print("Tema: {}".format(posts.get("tema", "—")))

    errors = 0
    for canal in PLATAFORMES:
        if _ja_publicat(data_str, canal):
            print("• {}: ja enviat per a aquest dia — saltat".format(canal))
            continue

        bloc = posts.get(canal) or {}
        text = bloc.get("text", "")
        if not text:
            print("✗ {}: post sense text".format(canal))
            errors += 1
            continue

        imatge = bloc.get("imatge") or posts.get("tema")  # reserva per a la imatge

        res = publica_post(canal, text, imatge, data_str)
        if res.get("ok"):
            _marcar_publicat(data_str, canal, res.get("id", ""))
            print("✓ {}: {}".format(canal, res.get("msg", "enviat")))
        else:
            errors += 1
            print("✗ {}: {}".format(canal, res.get("error", "error desconegut")))

    if errors:
        print("Acabat amb {} error(s). Revisa els missatges de dalt.".format(errors))
        return 1

    print("Tot programat a Buffer per a demà a les 7:00. Pots revisar-ho a buffer.com.")
    return 0


def executa_amb_reintents():
    """Executa la preparació del matí; si acaba amb errors, ho torna a provar
    sencer fins a REINTENTS_MATI vegades (els canals ja fets se salten)."""
    # Freqüència: un post cada dos dies (reorientació 2026-06). El launchd
    # segueix corrent cada matí, però només es preparen posts quan la data
    # del post (demà) cau en dia parell del calendari. Els altres dies, la
    # passada del matí no fa res (i així no cal ni esperar la xarxa).
    dema = datetime.date.today() + datetime.timedelta(days=1)
    if dema.toordinal() % 2 != 0:
        print("Avui no toca preparar posts: surten cada dos dies. "
              "Proper dia de publicació: {}.".format(
                  (dema + datetime.timedelta(days=1)).isoformat()))
        return 0
    # Esperar que el Wi-Fi estigui realment connectat abans de començar
    # (el Mac s'acaba de despertar i la xarxa pot trigar uns segons/minuts).
    espera_xarxa()
    for intent in range(1, REINTENTS_MATI + 1):
        codi = executa()
        if codi == 0:
            return 0
        if intent < REINTENTS_MATI:
            espera = ESPERA_MATI[min(intent - 1, len(ESPERA_MATI) - 1)]
            print("\n⟳ Passada {}/{} amb errors; reintent complet en {}s…\n".format(
                intent, REINTENTS_MATI, espera))
            time.sleep(espera)
    print("\n✗ No s'ha pogut completar després de {} passades. "
          "Revisa-ho al tauler (app Promotor Avatar del Dock).".format(REINTENTS_MATI))
    return 1


if __name__ == "__main__":
    sys.exit(executa_amb_reintents())
