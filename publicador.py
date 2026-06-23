"""
publicador.py — Publica posts a les xarxes via l'API GraphQL de Buffer.

FLUX:
  • Els TRES canals (X, LinkedIn, Instagram) van a la CUA de Buffer
    (addToQueue): els posts queden a buffer.com, tots al mateix lloc,
    llestos per revisar-los i publicar-los des d'allà.
  • Instagram porta, a més, una imatge generada amb Imagen 4.

Per què així:
  - Instagram NO admet publicacions sense imatge: cada post d'Instagram
    porta una imatge generada amb Imagen 4 (vegeu imatges.py).
  - Buffer Free NO admet esborranys (drafts) per a Instagram, però la cua
    (queue) sí que funciona per a tots els canals: el post apareix a la
    pestanya Queue de Buffer i es pot publicar des d'allà amb «Share Now»
    (o surt sol a la propera franja horària si n'hi ha de configurades).
    Es fa servir la cua per a tot, i no drafts, perquè així els tres posts
    són visibles al MATEIX lloc de Buffer.
  - L'API antiga de Buffer (api.bufferapp.com/1) ja no accepta els tokens
    actuals («OIDC tokens are not accepted»); per això es fa servir
    l'API GraphQL d'api.buffer.com, la mateixa que usa el web de Buffer.

Les imatges locals es pugen a catbox.moe per obtenir una URL pública,
perquè l'API de Buffer només accepta URLs d'imatge (no binari).
"""

import datetime
import json
import re
from pathlib import Path

import requests

from config import get_key

BUFFER_API_URL = "https://api.buffer.com"
CATBOX_API_URL = "https://catbox.moe/user/api.php"
FITXER_CANALS = Path(__file__).parent / "dades" / "canals.json"

XARXES = ("twitter", "linkedin", "instagram")

# Hora local de sortida dels posts (decisió usuari 2026-06-12: les 7:00)
HORA_SORTIDA = 7

# Cache en memòria durant la vida del procés
_org_id_cache = None


def _get_token():
    """Retorna el token d'accés de Buffer (variable d'entorn o dades/keys.json)."""
    return get_key("BUFFER_ACCESS_TOKEN")


# ---------------------------------------------------------------------------
# Crides GraphQL a Buffer
# ---------------------------------------------------------------------------

def _buffer_graphql(query, variables=None):
    """Crida l'API GraphQL de Buffer. Retorna la resposta JSON sencera."""
    token = _get_token()
    if not token:
        return {"errors": [{"message": (
            "Falta BUFFER_ACCESS_TOKEN. Afegeix-lo a ~/.zshrc: "
            "export BUFFER_ACCESS_TOKEN='el_teu_token'"
        )}]}

    try:
        resp = requests.post(
            BUFFER_API_URL,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"errors": [{"message": "No s'ha pogut connectar a Buffer. Comprova la connexió a internet."}]}
    except requests.exceptions.Timeout:
        return {"errors": [{"message": "Timeout connectant a Buffer (>30s)."}]}
    except Exception as e:
        return {"errors": [{"message": "Error de xarxa amb Buffer: {}".format(e)}]}


def _org_id():
    """Retorna l'organization id del compte Buffer actual (cachejat)."""
    global _org_id_cache
    if _org_id_cache:
        return _org_id_cache
    r = _buffer_graphql("{ account { currentOrganization { id } } }")
    try:
        _org_id_cache = r["data"]["account"]["currentOrganization"]["id"]
        return _org_id_cache
    except (KeyError, TypeError):
        return ""


def get_canals(forcar_refresc=False):
    """
    Obté els IDs dels canals de Buffer (LinkedIn, Twitter, Instagram).

    Guarda la caché a dades/canals.json per evitar crides repetides.

    Args:
        forcar_refresc: Si True, ignora la caché i consulta l'API.

    Returns:
        Dict {"linkedin": "ID", "twitter": "ID", "instagram": "ID"}
        o {"error": "missatge"} si falla.
    """
    token = _get_token()
    if not token:
        return {
            "error": (
                "Falta BUFFER_ACCESS_TOKEN. Afegeix-lo a ~/.zshrc: "
                "export BUFFER_ACCESS_TOKEN='el_teu_token'"
            )
        }

    # Intentar llegir la caché si existeix i no es força refresc
    if not forcar_refresc and FITXER_CANALS.exists():
        try:
            with open(FITXER_CANALS, "r", encoding="utf-8") as f:
                canals = json.load(f)
            if all(k in canals for k in XARXES):
                return canals
        except (json.JSONDecodeError, IOError):
            pass  # Caché corrupte, refrescar

    org_id = _org_id()
    if not org_id:
        return {"error": (
            "Token de Buffer invàlid o caducat (no s'ha pogut obtenir el compte). "
            "Regenera'l a buffer.com/developers/api."
        )}

    resp = _buffer_graphql(
        "query($input: ChannelsInput!) { channels(input: $input) { id service } }",
        {"input": {"organizationId": org_id}},
    )
    if "errors" in resp:
        msgs = "; ".join(e.get("message", "?") for e in resp["errors"])
        return {"error": "Buffer no ha retornat els canals: {}".format(msgs)}

    canals = {}
    try:
        for c in resp["data"]["channels"]:
            servei = (c.get("service") or "").lower()
            if servei in XARXES and servei not in canals and c.get("id"):
                canals[servei] = c["id"]
    except (KeyError, TypeError):
        return {"error": "Resposta inesperada de Buffer consultant els canals: {}".format(resp)}

    if not canals:
        return {"error": "No s'han trobat canals connectats a Buffer. Connecta les xarxes a buffer.com."}

    # Guardar la caché
    try:
        FITXER_CANALS.parent.mkdir(parents=True, exist_ok=True)
        with open(FITXER_CANALS, "w", encoding="utf-8") as f:
            json.dump(canals, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print("Avís: no s'ha pogut guardar la caché de canals: {}".format(e))

    return canals


# ---------------------------------------------------------------------------
# Imatges: cada xarxa porta la SEVA imatge del dia (diferent a cada xarxa)
# ---------------------------------------------------------------------------

def _puja_a_catbox(cami):
    """Puja una imatge a catbox.moe i retorna la URL pública. None si falla."""
    try:
        contingut = cami.read_bytes()
    except OSError as e:
        print("[publicador] No puc llegir la imatge {}: {}".format(cami, e))
        return None
    try:
        resp = requests.post(
            CATBOX_API_URL,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (cami.name, contingut)},
            timeout=60,
        )
        if resp.status_code == 200 and resp.text.startswith("https://"):
            return resp.text.strip()
        print("[publicador] catbox.moe ha respost: {} {}".format(resp.status_code, resp.text[:200]))
        return None
    except Exception as e:
        print("[publicador] Error pujant a catbox.moe: {}".format(e))
        return None


def _descripcio_des_del_text(text):
    """Última xarxa de seguretat: deriva una descripció visual del text del
    post (sense hashtags) perquè Imagen sempre tingui alguna cosa a fer."""
    sense_hashtags = re.sub(r"#\S+", "", text or "")
    sense_url = sense_hashtags.replace("sergicastillo.com", "")
    net = " ".join(sense_url.split())
    return net[:180] if net else "una llibreria antiga amb llum càlida de tarda"


def _imatge_publica(descripcio, text, data_str, xarxa):
    """Aconsegueix la URL pública de la imatge d'aquesta xarxa per a aquest dia:
    genera la imatge amb Imagen 4 (o reutilitza la del dia/xarxa si ja existeix,
    cada xarxa té el seu fitxer i el seu format) i la puja a catbox.moe.

    Returns:
        (url, None) si tot bé · (None, missatge_error) si falla.
    """
    desc = (descripcio or "").strip()
    if not desc:
        desc = _descripcio_des_del_text(text)

    # Si la "descripció" és en realitat un fitxer local existent, usar-lo
    cami = None
    possible = Path(desc).expanduser()
    if possible.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and possible.exists():
        cami = possible
    else:
        try:
            from imatges import genera_imatge, aspect_per_xarxa
            cami = genera_imatge(
                desc, data_iso=data_str, xarxa=xarxa,
                aspect_ratio=aspect_per_xarxa(xarxa),
            )
        except Exception as e:
            return None, "No s'ha pogut generar la imatge per a {}: {}".format(xarxa, e)

    if not cami:
        return None, (
            "No s'ha pogut generar la imatge per a {}. Revisa GEMINI_API_KEY (Imagen 4)."
        ).format(xarxa)

    url = _puja_a_catbox(cami)
    if not url:
        return None, (
            "La imatge s'ha generat ({}) però no s'ha pogut pujar a catbox.moe "
            "per obtenir-ne una URL pública. Torna-ho a provar d'aquí una estona."
        ).format(cami.name)

    return url, None


# ---------------------------------------------------------------------------
# Publicació
# ---------------------------------------------------------------------------

def _ja_programat_aquell_dia(channel_id, data_str):
    """True si Buffer ja té un post (programat o ja enviat) en aquest canal
    amb data de sortida data_str. Fa el sistema a prova de duplicats: si el
    preparador s'executa dues vegades, o si conviuen el portàtil i el núvol,
    no es crea un segon post per al mateix dia i canal."""
    org = _org_id()
    if not org:
        return False
    resp = _buffer_graphql(
        """
        query($input: PostsInput!) {
          posts(input: $input, first: 100) { edges { node { dueAt } } }
        }
        """,
        {"input": {"organizationId": org,
                   "filter": {"status": ["scheduled", "sent"], "channelIds": [channel_id]}}},
    )
    if "errors" in resp:
        return False  # en cas de dubte, no bloquegem
    edges = (((resp.get("data") or {}).get("posts") or {}).get("edges")) or []
    for e in edges:
        due = ((e.get("node") or {}).get("dueAt") or "")[:10]
        if due == data_str:
            return True
    return False


def publica_post(canal, text, imatge=None, data_str=None, quan=None):
    """
    Envia un post a Buffer, programat per a les 7:00 del dia del post
    (customScheduled). Si les 7:00 d'aquell dia ja han passat, va a la cua
    normal (addToQueue). Instagram porta imatge generada. En tots dos casos
    el post queda a buffer.com, on es pot revisar, avançar o esborrar.

    Cada xarxa porta la SEVA imatge del dia (diferent a cada xarxa): així no
    es repeteix la targeta de previsualització del web a X i LinkedIn.

    Args:
        canal: "linkedin", "twitter" o "instagram"
        text: cos del post
        imatge: descripció visual en català (o ruta d'imatge local) per a
                aquesta xarxa; si falta, es deriva del text.
        data_str: data ISO del post (per nomenar/cachejar la imatge del dia)

    Returns:
        {"ok": True, "msg": "...", "id": "..."} si ha anat bé
        {"ok": False, "error": "..."} si ha fallat
    """
    canal_norm = (canal or "").lower()

    canals = get_canals()
    if "error" in canals:
        return {"ok": False, "error": canals["error"]}

    if canal_norm not in canals:
        return {
            "ok": False,
            "error": "Canal '{}' no trobat a Buffer. Canals disponibles: {}".format(
                canal, ", ".join(canals.keys())
            ),
        }

    if not data_str:
        data_str = datetime.date.today().isoformat()

    # Anti-duplicats: si Buffer ja té un post d'aquest canal per a aquest dia,
    # no en creem un altre (evita duplicats si el preparador es repeteix o si
    # conviuen el portàtil i el núvol). Es comprova ABANS de generar la imatge.
    if _ja_programat_aquell_dia(canals[canal_norm], data_str):
        return {"ok": True, "skip": True,
                "msg": "Ja hi ha un post a {} per al {} — no en creo cap altre.".format(canal, data_str)}

    # X (Twitter): límit estricte de 280 caràcters
    text_final = text[:280] if canal_norm == "twitter" else text

    input_data = {
        "channelId": canals[canal_norm],
        "text": text_final,
        "schedulingType": "automatic",
        "saveToDraft": False,
    }

    # Hora de sortida. Si es passa `quan` (un datetime), s'usa directament:
    # serveix per "publicar ja" (programant d'aquí a pocs minuts) i així no
    # quedar enrere a la cua. Si no, hora per defecte: les 7:00 del dia del post;
    # si ja han passat, va a la cua normal de Buffer (propera franja lliure).
    hora_sortida = None
    if quan is not None:
        hora_sortida = quan if quan.tzinfo else quan.astimezone()
    else:
        try:
            dia = datetime.date.fromisoformat(data_str)
            objectiu = datetime.datetime.combine(
                dia, datetime.time(HORA_SORTIDA, 0)
            ).astimezone()  # hora local del Mac
            ara = datetime.datetime.now().astimezone()
            if objectiu > ara + datetime.timedelta(minutes=2):
                hora_sortida = objectiu
        except ValueError:
            pass

    if hora_sortida:
        input_data["mode"] = "customScheduled"
        input_data["dueAt"] = (
            hora_sortida.astimezone(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    else:
        input_data["mode"] = "addToQueue"

    # Imatge pròpia de cada xarxa (diferent a cada una). A Instagram és
    # obligatòria; a X i LinkedIn evita la targeta repetida del web.
    url_imatge, error = _imatge_publica(imatge, text, data_str, canal_norm)
    if error:
        # Instagram NO pot anar sense imatge; X i LinkedIn sí (text net) com a
        # darrer recurs, però avisem perquè es vegi al registre.
        if canal_norm == "instagram":
            return {"ok": False, "error": error}
        print("[publicador] {} sense imatge ({}); s'envia només amb text.".format(canal_norm, error))
    else:
        input_data["assets"] = [{"image": {"url": url_imatge}}]

    if canal_norm == "instagram":
        input_data["metadata"] = {
            "instagram": {"type": "post", "shouldShareToFeed": True}
        }

    mutation = """
    mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id status } }
        ... on MutationError { message }
      }
    }
    """
    result = _buffer_graphql(mutation, {"input": input_data})

    if "errors" in result:
        msgs = "; ".join(e.get("message", "?") for e in result["errors"])
        return {"ok": False, "error": "Buffer ha rebutjat el post: {}".format(msgs)}

    cp = (result.get("data") or {}).get("createPost") or {}
    if cp.get("__typename") == "PostActionSuccess":
        post = cp.get("post") or {}
        amb_imatge = " amb imatge" if input_data.get("assets") else ""
        if hora_sortida:
            msg = "Programat a Buffer{} per al {}.".format(
                amb_imatge, hora_sortida.strftime("%d-%m-%Y a les %H:%M")
            )
        else:
            msg = "A la cua de Buffer{} — revisa'l a buffer.com.".format(amb_imatge)
        return {"ok": True, "msg": msg, "id": post.get("id", "")}

    if cp.get("message"):
        return {"ok": False, "error": "[{}] {}".format(cp.get("__typename", "Error"), cp["message"])}

    return {"ok": False, "error": "Resposta inesperada de Buffer: {}".format(result)}


def esborra_post(post_id):
    """Esborra un post de Buffer (només funciona mentre encara no s'ha
    publicat; un post ja enviat no es pot tocar per API).

    Returns: {"ok": True} o {"ok": False, "error": "..."}
    """
    if not post_id:
        return {"ok": False, "error": "Falta l'identificador del post."}
    result = _buffer_graphql(
        "mutation($input: DeletePostInput!) { deletePost(input: $input) "
        "{ __typename ... on VoidMutationError { message } } }",
        {"input": {"id": post_id}},
    )
    if "errors" in result:
        msgs = "; ".join(e.get("message", "?") for e in result["errors"])
        return {"ok": False, "error": msgs}
    dp = (result.get("data") or {}).get("deletePost") or {}
    if dp.get("__typename") == "DeletePostSuccess":
        return {"ok": True}
    return {"ok": False, "error": dp.get("message", "Resposta inesperada: {}".format(result))}


if __name__ == "__main__":
    # Test ràpid dels canals disponibles (només lectura)
    print("Consultant canals de Buffer...")
    canals = get_canals(forcar_refresc=True)
    print(json.dumps(canals, ensure_ascii=False, indent=2))
