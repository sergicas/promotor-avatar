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
from tiktok import publica_tiktok

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


def executa(data_override=None):
    if data_override:
        data_str = data_override
    else:
        data_str = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    ara = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    print("── Promotor Avatar · ara: {} · preparant els posts del {} ──".format(ara, data_str))

    posts = _obtenir_posts_dia(data_str)
    if "error" in posts:
        print("✗ No s'han pogut generar els posts: {}".format(posts["error"]))
        return 1, [], data_str

    print("Tema: {}".format(posts.get("tema", "—")))

    # Anti-duplicats: NO es fa servir cap estat local (es desincronitza). La
    # comprovació real la fa publica_post contra Buffer (_ja_programat_aquell_dia):
    # si un canal ja té un post aquell dia, torna {ok, skip} i no en crea cap altre.
    errors = 0
    items = []  # per al resum per correu
    for canal in PLATAFORMES:
        bloc = posts.get(canal) or {}
        text = bloc.get("text", "")
        if not text:
            print("✗ {}: post sense text".format(canal))
            errors += 1
            items.append({"canal": canal, "text": "", "ok": False, "msg": "post sense text"})
            continue

        imatge = bloc.get("imatge") or posts.get("tema")  # reserva per a la imatge

        res = publica_post(canal, text, imatge, data_str)
        if res.get("ok"):
            print("✓ {}: {}".format(canal, res.get("msg", "enviat")))
        else:
            errors += 1
            print("✗ {}: {}".format(canal, res.get("error", "error desconegut")))
        items.append({
            "canal": canal,
            "text": text,
            "imatge_url": res.get("imatge_url"),
            "ok": bool(res.get("ok")),
            "msg": res.get("error") or res.get("msg", ""),
        })

    # TikTok: publica directament (DIRECT_POST) ara mateix, amb el vídeo de Veo 2.
    # Usa el text d'Instagram (el més visual) com a peu de vídeo.
    ig_bloc = posts.get("instagram") or {}
    ig_text = ig_bloc.get("text", "")
    imatge_ig = ig_bloc.get("imatge") or posts.get("tema") or ""
    if ig_text:
        print("── TikTok ──")
        res_tt = publica_tiktok(ig_text, imatge_ig, data_str)
        if res_tt.get("ok"):
            print("✓ tiktok: {}".format(res_tt.get("msg", "publicat")))
        else:
            print("✗ tiktok: {}".format(res_tt.get("error", "error desconegut")))
        items.append({
            "canal": "tiktok",
            "text": ig_text,
            "ok": bool(res_tt.get("ok")),
            "msg": res_tt.get("error") or res_tt.get("msg", ""),
        })
    else:
        print("✗ tiktok: sense text d'Instagram per generar el vídeo")

    if errors:
        print("Acabat amb {} error(s). Revisa els missatges de dalt.".format(errors))
        return 1, items, data_str

    print("Tot programat a Buffer per a demà a les 7:00. Pots revisar-ho a buffer.com.")
    return 0, items, data_str


def executa_amb_reintents(data_override=None):
    """Executa la preparació del matí; si acaba amb errors, ho torna a provar
    sencer fins a REINTENTS_MATI vegades (els canals ja fets se salten).

    data_override: si es passa una data ('YYYY-MM-DD'), es preparen els posts
    d'aquell dia concret i se salta la comprovació de cadència (per provar o
    rescatar un dia a mà)."""
    if not data_override:
        # Freqüència: un post cada dos dies (reorientació 2026-06). Només es
        # preparen posts quan la data del post (demà) cau en dia parell del
        # calendari. Els altres dies, la passada no fa res.
        dema = datetime.date.today() + datetime.timedelta(days=1)
        if dema.toordinal() % 2 != 0:
            print("Avui no toca preparar posts: surten cada dos dies. "
                  "Proper dia de publicació: {}.".format(
                      (dema + datetime.timedelta(days=1)).isoformat()))
            return 0
    # Esperar que el Wi-Fi estigui realment connectat abans de començar
    # (el Mac s'acaba de despertar i la xarxa pot trigar uns segons/minuts).
    espera_xarxa()
    codi, items, data_str = 1, [], data_override or ""
    for intent in range(1, REINTENTS_MATI + 1):
        codi, items, data_str = executa(data_override)
        if codi == 0:
            break
        if intent < REINTENTS_MATI:
            espera = ESPERA_MATI[min(intent - 1, len(ESPERA_MATI) - 1)]
            print("\n⟳ Passada {}/{} amb errors; reintent complet en {}s…\n".format(
                intent, REINTENTS_MATI, espera))
            time.sleep(espera)

    # Resum per correu UNA sola vegada, amb l'estat final (que en Sergi vegi
    # els posts de demà abans de les 7:00).
    try:
        from correu import envia_resum
        envia_resum(data_str, items)
    except Exception as e:
        print("[mati] no s'ha pogut enviar el resum per correu: {}".format(e))

    if codi != 0:
        print("\n✗ No s'ha pogut completar del tot després de {} passades.".format(REINTENTS_MATI))
    return codi


if __name__ == "__main__":
    # Argument opcional: una data 'YYYY-MM-DD' per forçar la preparació
    # d'aquell dia (salta la cadència). Sense argument, comportament normal.
    forcat = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else None
    sys.exit(executa_amb_reintents(forcat))
