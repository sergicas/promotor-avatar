"""
promotor.py — Flask app del Promotor Avatar Sergi (port 5079)
Autor: Avatar Sergi Castillo Lapeira
"""

import json
import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file, abort

from generador import genera_posts_dia, afegeix_web_a_posts
from publicador import publica_post, esborra_post
from config import guardar_key, keys_configurades

# ---------------------------------------------------------------------------
# Configuració de l'app
# ---------------------------------------------------------------------------
app = Flask(__name__)

DIRECTORI_DADES = Path(__file__).parent / "dades"
FITXER_PUBLICATS = DIRECTORI_DADES / "publicats.json"
FITXER_ESBORRANYS = DIRECTORI_DADES / "esborranys.json"
DIRECTORI_IMATGES = Path(__file__).parent / "imatges_generades"

PLATAFORMES = ["linkedin", "twitter", "instagram"]

# Mesos en català per a la UI
MESOS_CAT = [
    "", "gener", "febrer", "març", "abril", "maig", "juny",
    "juliol", "agost", "setembre", "octubre", "novembre", "desembre",
]
DIES_CAT = [
    "dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge",
]


# ---------------------------------------------------------------------------
# Helpers de persistència
# ---------------------------------------------------------------------------

def _llegir_json(fitxer):
    """Llegeix un fitxer JSON de forma segura."""
    try:
        if fitxer.exists():
            with open(fitxer, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _guardar_json(fitxer, dades):
    """Guarda un dict com a JSON de forma segura."""
    fitxer.parent.mkdir(parents=True, exist_ok=True)
    with open(fitxer, "w", encoding="utf-8") as f:
        json.dump(dades, f, ensure_ascii=False, indent=2)


def _data_avui():
    """Retorna la data d'avui en format ISO (YYYY-MM-DD)."""
    return datetime.date.today().isoformat()


def _formatar_data_cat(data_str):
    """Formata una data ISO en català: 'Divendres, 12 de juny de 2026'."""
    try:
        data = datetime.date.fromisoformat(data_str)
        dia_setmana = DIES_CAT[data.weekday()].capitalize()
        mes = MESOS_CAT[data.month]
        return f"{dia_setmana}, {data.day} de {mes} de {data.year}"
    except ValueError:
        return data_str


def _obtenir_posts_dia(data_str, forcar=False):
    """
    Retorna els posts per a una data. Genera si no existeixen o si forcar=True.

    Returns:
        Dict amb els posts o {'error': '...'} si falla la generació.
    """
    esborranys = _llegir_json(FITXER_ESBORRANYS)

    if not forcar and data_str in esborranys:
        posts = esborranys[data_str]
        # Reparació de posts en caché d'abans: garantir la web a tots els textos.
        # Els posts d'Arrel (campanya='arrel') i els de cita de llibre
        # (campanya='cita') NO porten la web ni cap afegit: van nets.
        if posts.get("campanya") not in ("arrel", "cita") and afegeix_web_a_posts(posts):
            _guardar_json(FITXER_ESBORRANYS, esborranys)
        return posts

    # Generar via Gemini
    posts = genera_posts_dia(data_str)

    if "error" in posts:
        return posts  # Propagar l'error

    # Guardar a la caché
    esborranys[data_str] = posts
    _guardar_json(FITXER_ESBORRANYS, esborranys)

    return posts


def _ja_publicat(data_str, canal):
    """Comprova si un canal ja ha estat publicat per a una data."""
    publicats = _llegir_json(FITXER_PUBLICATS)
    return canal in publicats.get(data_str, {})


def _marcar_publicat(data_str, canal, post_id=""):
    """Marca un canal com a publicat per a una data."""
    publicats = _llegir_json(FITXER_PUBLICATS)
    if data_str not in publicats:
        publicats[data_str] = {}
    publicats[data_str][canal] = {
        "hora": datetime.datetime.now().isoformat(),
        "post_id": post_id,
    }
    _guardar_json(FITXER_PUBLICATS, publicats)


def _estat_publicacio(data_str):
    """Retorna l'estat de publicació de cada canal per a una data."""
    publicats = _llegir_json(FITXER_PUBLICATS)
    estat = {}
    for canal in PLATAFORMES:
        estat[canal] = canal in publicats.get(data_str, {})
    return estat


# ---------------------------------------------------------------------------
# Rutes Flask
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Pàgina principal: mostra els posts de DEMÀ, els que encara es poden
    validar o substituir abans no surtin a les 7:00."""
    dema = datetime.date.today() + datetime.timedelta(days=1)
    data_str = dema.isoformat()
    keys = keys_configurades()

    # Si les claus no estan configurades, redirigir a la configuració
    if not keys["GEMINI_API_KEY"]:
        return render_template("index.html",
            data_str=data_str,
            data_cat=_formatar_data_cat(data_str),
            posts={}, estat={}, error=None, imatge_v=None,
            setup_mode=True, keys=keys)

    posts = _obtenir_posts_dia(data_str)
    estat = _estat_publicacio(data_str)
    data_cat = _formatar_data_cat(data_str)

    # Versió (mtime) de la imatge de cada xarxa, si existeix — fa de
    # trenca-caché del navegador quan es regenera
    imatge_v = {}
    for canal in PLATAFORMES:
        cami = DIRECTORI_IMATGES / "{}_{}.png".format(data_str, canal)
        if cami.exists():
            imatge_v[canal] = int(cami.stat().st_mtime)

    return render_template(
        "index.html",
        data_str=data_str,
        data_cat=data_cat,
        posts=posts,
        estat=estat,
        error=posts.get("error"),
        imatge_v=imatge_v,
        setup_mode=False,
        keys=keys,
    )


@app.route("/imatge/<data_str>/<canal>")
def imatge_dia(data_str: str, canal: str):
    """Serveix la imatge generada d'una xarxa per a una data."""
    try:
        datetime.date.fromisoformat(data_str)
    except ValueError:
        abort(404)
    if canal not in PLATAFORMES:
        abort(404)
    cami = DIRECTORI_IMATGES / "{}_{}.png".format(data_str, canal)
    if not cami.exists():
        abort(404)
    return send_file(cami, mimetype="image/png")


@app.route("/api/configurar", methods=["POST"])
def api_configurar():
    """Desa les claus API al fitxer dades/keys.json."""
    dades = request.get_json() or {}
    gemini = dades.get("gemini_key", "").strip()
    buffer = dades.get("buffer_token", "").strip()
    errors = []
    if gemini:
        if not guardar_key("GEMINI_API_KEY", gemini):
            errors.append("No s'ha pogut desar GEMINI_API_KEY")
    if buffer:
        if not guardar_key("BUFFER_ACCESS_TOKEN", buffer):
            errors.append("No s'ha pogut desar BUFFER_ACCESS_TOKEN")
    if errors:
        return jsonify({"ok": False, "msg": " | ".join(errors)}), 500
    return jsonify({"ok": True, "msg": "Claus desades correctament."})


@app.route("/api/publica/<data_str>/<canal>", methods=["POST"])
def api_publica_canal(data_str: str, canal: str):
    """
    Publica un canal concret via Buffer.

    Returns JSON: {"ok": bool, "msg": "...", "ja_publicat": bool}
    """
    canal = canal.lower()

    # Anti-duplicate check
    if _ja_publicat(data_str, canal):
        return jsonify({
            "ok": False,
            "skip": True,
            "msg": "Ja publicat avui — saltat",
        })

    # Obtenir el post
    posts = _obtenir_posts_dia(data_str)
    if "error" in posts:
        return jsonify({"ok": False, "msg": posts["error"]}), 500

    if canal not in posts:
        return jsonify({"ok": False, "msg": f"Canal desconegut: {canal}"}), 400

    text = posts[canal].get("text", "")
    imatge = posts[canal].get("imatge") or posts.get("tema")  # reserva per a la imatge

    if not text:
        return jsonify({"ok": False, "msg": "El post no té text."}), 400

    # Enviar a Buffer amb la imatge pròpia de la xarxa
    resultat = publica_post(canal, text, imatge, data_str)

    if resultat.get("ok"):
        _marcar_publicat(data_str, canal, resultat.get("id", ""))
        return jsonify({
            "ok": True,
            "msg": resultat.get("msg", "Publicat correctament."),
            "id": resultat.get("id", ""),
        })
    else:
        return jsonify({
            "ok": False,
            "msg": resultat.get("error", "Error desconegut publicant."),
        }), 500


@app.route("/api/publica-tot/<data_str>", methods=["POST"])
def api_publica_tot(data_str: str):
    """
    Publica tots els canals que no s'hagin publicat encara.

    Returns JSON: {"resultats": {"linkedin": {...}, "twitter": {...}, "instagram": {...}}}
    """
    posts = _obtenir_posts_dia(data_str)
    if "error" in posts:
        return jsonify({"ok": False, "msg": posts["error"]}), 500

    resultats = {}
    for canal in PLATAFORMES:
        # Saltar si ja publicat
        if _ja_publicat(data_str, canal):
            resultats[canal] = {
                "ok": False,
                "skip": True,
                "msg": "Ja publicat — saltat",
            }
            continue

        if canal not in posts:
            resultats[canal] = {"ok": False, "msg": f"No hi ha post per a '{canal}'"}
            continue

        text = posts[canal].get("text", "")
        imatge = posts[canal].get("imatge") or posts.get("tema")  # reserva per a la imatge

        if not text:
            resultats[canal] = {"ok": False, "msg": "Post sense text."}
            continue

        res = publica_post(canal, text, imatge, data_str)
        if res.get("ok"):
            _marcar_publicat(data_str, canal, res.get("id", ""))
            resultats[canal] = {
                "ok": True,
                "msg": res.get("msg", "Publicat correctament."),
            }
        else:
            resultats[canal] = {
                "ok": False,
                "msg": res.get("error", "Error desconegut."),
            }

    return jsonify({"resultats": resultats})


@app.route("/api/genera/<data_str>", methods=["POST"])
def api_genera(data_str: str):
    """
    Força la regeneració dels posts per a una data (ignora la caché).
    NO toca Buffer — per substituir posts ja programats useu /api/substitueix.

    Returns JSON: els nous posts o {"error": "..."}
    """
    posts = _obtenir_posts_dia(data_str, forcar=True)

    if "error" in posts:
        return jsonify({"ok": False, "msg": posts["error"]}), 500

    return jsonify({"ok": True, "posts": posts})


@app.route("/api/substitueix/<data_str>", methods=["POST"])
def api_substitueix(data_str: str):
    """
    Descarta els posts d'una data: els esborra de Buffer (si encara no
    s'han publicat), en genera de nous (textos i imatge) i els torna a
    programar per a les 7:00 del seu dia.
    """
    try:
        dia = datetime.date.fromisoformat(data_str)
    except ValueError:
        return jsonify({"ok": False, "msg": "Data invàlida."}), 400

    # Només mentre encara no s'han publicat (abans de les 7:00 del seu dia)
    limit = datetime.datetime.combine(dia, datetime.time(7, 0)).astimezone()
    if datetime.datetime.now().astimezone() >= limit:
        return jsonify({
            "ok": False,
            "msg": "Aquests posts ja s'han publicat — no es poden substituir.",
        }), 400

    # 1) Esborrar de Buffer els que hi havia programats
    publicats = _llegir_json(FITXER_PUBLICATS)
    errors = []
    for canal, info in (publicats.get(data_str) or {}).items():
        pid = info.get("post_id", "")
        if pid:
            res = esborra_post(pid)
            if not res.get("ok"):
                errors.append("{}: {}".format(canal, res.get("error", "?")))
    if errors:
        return jsonify({
            "ok": False,
            "msg": "No s'ha pogut esborrar de Buffer — " + " | ".join(errors),
        }), 500
    publicats.pop(data_str, None)
    _guardar_json(FITXER_PUBLICATS, publicats)

    # 2) Esborrar les imatges del dia (una per xarxa) perquè se'n generin de noves
    for canal in PLATAFORMES:
        cami_imatge = DIRECTORI_IMATGES / "{}_{}.png".format(data_str, canal)
        if cami_imatge.exists():
            cami_imatge.unlink()

    # 3) Regenerar els textos
    posts = _obtenir_posts_dia(data_str, forcar=True)
    if "error" in posts:
        return jsonify({"ok": False, "msg": posts["error"]}), 500

    # 4) Tornar-los a programar a Buffer (7:00 del seu dia)
    fallats = []
    for canal in PLATAFORMES:
        bloc = posts.get(canal) or {}
        text = bloc.get("text", "")
        imatge = bloc.get("imatge") or posts.get("tema")
        if not text:
            fallats.append("{}: post sense text".format(canal))
            continue
        res = publica_post(canal, text, imatge, data_str)
        if res.get("ok"):
            _marcar_publicat(data_str, canal, res.get("id", ""))
        else:
            fallats.append("{}: {}".format(canal, res.get("error", "?")))

    if fallats:
        return jsonify({
            "ok": False,
            "msg": "Posts nous generats però amb errors reprogramant — " + " | ".join(fallats),
        }), 500

    return jsonify({"ok": True, "msg": "Posts nous programats per a les 7:00."})


# ---------------------------------------------------------------------------
# Arrencada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("  Promotor Avatar Sergi — arrencant...")
    print(f"  Accedeix a: http://127.0.0.1:5079")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5079, debug=False)
