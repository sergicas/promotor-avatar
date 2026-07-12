"""
generador.py — Genera els posts diaris via Gemini 2.0 Flash
Usa el nou SDK: google-genai (from google import genai)
Compatible amb Python 3.9+
"""

import json
import os
import re
import time
import datetime

import requests
from google import genai
from google.genai import types as genai_types

from config import get_key

# Reintents per a blips de xarxa (DNS, timeouts) en cridar Gemini o l'Avatar
REINTENTS_XARXA = 3
ESPERA_XARXA = (10, 30, 60)  # segons, creixent


def _es_error_transitori(e):
    """Heurística: l'error sembla un problema de xarxa puntual (val la pena
    reintentar) i no un error de configuració (clau dolenta, etc.)."""
    text = str(e).lower()
    senyals = (
        "nodename nor servname", "name or service not known", "temporary failure",
        "timed out", "timeout", "connection", "getaddrinfo", "ssl",
        "503", "502", "500", "unavailable", "deadline", "reset by peer",
    )
    return any(s in text for s in senyals)

# ---------------------------------------------------------------------------
# Configuració del model
# ---------------------------------------------------------------------------
# Model de text. Google retira models cada pocs mesos (gemini-2.5-flash va
# morir el juliol de 2026 abans de la data anunciada), així que el nom es pot
# canviar via variable d'entorn sense tocar el codi: GEMINI_TEXT_MODEL.
GEMINI_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")

# Catàleg complet de llibres per incloure al context del model
CATALEG_LLIBRES = """
CATÀLEG DE LLIBRES DE SERGI CASTILLO LAPEIRA:

- Nara (novel·la fantasia/CF): La Nara té setze anys i, sota pressió, li broten ales de papallona.
  Trauma, identitat, amistat, redempció.
  CAT: amazon.es/dp/B0FD3DKZLD · ES: amazon.es/dp/8409738740 · EN: amazon.es/dp/8409744317

- La vida d'en George (novel·la CF): En George és un humà sintètic que ens fa de mirall.
  CAT: amazon.es/dp/B0CKZMKFZX

- Inspector Montoliu (policíaca): Un policia a punt de jubilar-se, cadàvers, bessó desconegut.
  CAT: amazon.es/dp/B0CRJPJ98P

- Una Història Sentimental (dramàtica): Cinc joves Generació Z al llarg d'una dècada.
  CAT: amazon.es/dp/B0CZRQFCNZ

- Contes a la vora del gel (contes): 20 contes sobre natura i societat.
  CAT: amazon.es/dp/B0D2ZCXZ8M

- Ànima Material (poesia): 47 poemes des de l'espai íntim.
  CAT: amazon.es/dp/B0CQYZPZGC

- Ètica i estètica de l'instant (assaig): L'ara etern i efímer.
  CAT: amazon.es/dp/B0DP62B81G

PROJECTES ACTIUS:
- El Bon Diari (bondiari.com) — periodisme constructiu
- Curs Filosofia i IA (filoia.netlify.app)
- Màster UB, TFM "El Logos Intraduïble"
- Avatar conversacional (sergicastillo.com)
"""

# 7 temes que roten per dia (índex = dia_de_l_any % 7). Referencien els
# llibres de Sergi en to planer i proper, SENSE "jo" autobiogràfic.
MODES = [
    "Presenta una idea o un tema d'un dels llibres de Sergi, explicat de manera planera i propera",
    "Explica un personatge o una situació d'una de les novel·les com una història que enganxa",
    "Connecta una cosa del dia a dia amb el que es viu en un dels llibres",
    "Una curiositat o una pregunta amable que porti cap a un dels llibres",
    "Recomana un dels llibres dient, en to d'amic, què hi trobarà qui el llegeixi",
    "Un tast d'una escena o una imatge d'un llibre que faci venir ganes de llegir-lo",
    "Una mirada senzilla sobre un tema dels llibres (el temps, la memòria, la identitat), sense tecnicismes",
]

# Indicació de quin llibre usar en mode 1 (rota per dia de l'any)
# NOTA: "Diálogos filosóficos con mi amigo Pi" està EN PAUSA (decisió usuari
# 2026-07-01). Per tornar-lo a promocionar, afegeix-lo de nou aquí i al
# CATALEG_LLIBRES de dalt.
LLIBRES_ROTATIU = [
    "Nara",
    "La vida d'en George",
    "Inspector Montoliu",
    "Una Història Sentimental",
    "Contes a la vora del gel",
    "Ànima Material",
    "Ètica i estètica de l'instant",
    "Acadèmia Gaia",
]

# Llibre a prioritzar (la novetat): surt 1 de cada 2 dies de llibre; la resta
# de llibres es reparteixen els altres dies. Posa'l a None per tornar a la
# rotació equitativa entre tots.
LLIBRE_PRIORITARI = "Acadèmia Gaia"


def _ordre_llibres():
    """Ordre de rotació dels llibres pels dies de llibre. Si hi ha un llibre
    prioritari, s'intercala entre cada un dels altres, de manera que hi surt 1
    de cada 2 dies de llibre i els altres van rotant en els dies restants."""
    if LLIBRE_PRIORITARI and LLIBRE_PRIORITARI in LLIBRES_ROTATIU:
        altres = [b for b in LLIBRES_ROTATIU if b != LLIBRE_PRIORITARI]
        ordre = []
        for b in altres:
            ordre.append(LLIBRE_PRIORITARI)
            ordre.append(b)
        return ordre
    return list(LLIBRES_ROTATIU)


# X i LinkedIn: amb https:// perquè surti com a enllaç CLICABLE
# (el domini nu "sergicastillo.com" sovint no s'enllaça sol).
WEB = "https://sergicastillo.com"
WEB_DOMINI = "sergicastillo.com"
# Instagram: els enllaços del text NO són clicables; per això es menciona la
# bio (on sí hi ha l'enllaç actiu) i no es posa https:// (quedaria lleig i inert).
WEB_IG = "sergicastillo.com · enllaç a la bio"

# Es manté el peu amb la web al final de cada post (decisió Sergi 2026-06-20).
# Posa-ho a False si algun dia no vols el peu sergicastillo.com.
INCLOURE_WEB = True


def _normalitza_web(t):
    """Converteix qualsevol 'sergicastillo.com' (nu o amb http) en
    'https://sergicastillo.com', perquè surti com a enllaç clicable."""
    t = re.sub(r"https?://sergicastillo\.com", WEB_DOMINI, t, flags=re.I)
    t = re.sub(r"sergicastillo\.com", WEB, t, flags=re.I)
    return t


def _text_amb_web(text, plataforma):
    """Retorna el text garantint que inclou la web. A X i LinkedIn, com a
    enllaç clicable (https://). A Instagram, com a "sergicastillo.com · enllaç
    a la bio" (perquè a IG els enllaços del text no són clicables)."""
    t = (text or "").rstrip()

    if plataforma == "instagram":
        # Separar el bloc final d'hashtags
        linies = t.split("\n")
        i = len(linies)
        while i > 0 and (not linies[i - 1].strip() or linies[i - 1].lstrip().startswith("#")):
            i -= 1
        cos = "\n".join(linies[:i])
        hashtags = "\n".join(linies[i:]).strip()
        # Treure qualsevol forma de web/coletilla ja present, per no duplicar
        cos = re.sub(r"https?://sergicastillo\.com", "", cos, flags=re.I)
        cos = re.sub(r"\(?\s*enllaç a la bio\s*\)?", "", cos, flags=re.I)
        cos = re.sub(r"sergicastillo\.com", "", cos, flags=re.I)
        cos = "\n".join(l.rstrip(" ·—-:\t") for l in cos.split("\n")).rstrip()
        bloc = cos + "\n\n" + WEB_IG
        return bloc + ("\n\n" + hashtags if hashtags else "")

    # X i LinkedIn: enllaç clicable amb https://
    t = _normalitza_web(t)
    if WEB_DOMINI in t.lower():
        return t  # ja hi és (i ara amb https://)
    return (t + " " + WEB) if plataforma == "twitter" else (t + "\n\n" + WEB)


def afegeix_web_a_posts(posts):
    """Assegura que els 3 posts inclouen la web sergicastillo.com.
    Modifica el dict al lloc. Retorna True si ha canviat res."""
    canviat = False
    for plataforma in ["linkedin", "twitter", "instagram"]:
        bloc = posts.get(plataforma)
        if isinstance(bloc, dict) and bloc.get("text"):
            nou = _text_amb_web(bloc["text"], plataforma)
            if nou != bloc["text"]:
                bloc["text"] = nou
                canviat = True
    return canviat


def _get_mode_del_dia(data):
    """Retorna (índex_mode, nom_mode) per a una data donada."""
    idx = data.timetuple().tm_yday % 7
    return idx, MODES[idx]


def _get_llibre_del_dia(data):
    """Retorna el títol del llibre que toca avui, rotant un llibre per cada dia
    de llibre. Els dies de llibre tenen la data ordinal múltiple de 4 (dia de
    publicació parell i no-Arrel), així que //4 avança d'un en un dins de
    l'ordre de rotació (que dona prioritat al llibre prioritari si n'hi ha)."""
    ordre = _ordre_llibres()
    return ordre[(data.toordinal() // 4) % len(ordre)]


# ---------------------------------------------------------------------------
# FRAGMENTS REALS DELS LLIBRES (banc de dades de l'Avatar, en local)
# ---------------------------------------------------------------------------
# En els modes de llibre (1 i 3), la font de veritat són fragments LITERALS
# de l'obra, llegits directament de l'índex de l'Avatar (embeddings.npz).
# Així cap intermediari pot inventar res: el text és el del llibre.

CORPUS_NPZ = "/Users/sergicastillo/Desktop/ARXIUS/APPS/Avatar - Sergi/avatar-rag/embeddings.npz"

MODES_DE_LLIBRE = (1, 3)

FONTS_LLIBRES = {
    "Nara": ["Literatura - Nara"],
    "La vida d'en George": ["Literatura - La Vida d'en George"],
    "Inspector Montoliu": ["Literatura - Inspector Montoliu"],
    "Una Història Sentimental": ["Literatura - Una Història Sentimental"],
    "Contes a la vora del gel": ["Literatura - Contes a la vora del gel"],
    "Ànima Material": ["Literatura - Ànima material"],
    "Ètica i estètica de l'instant": ["Filosofia - Ètica i Estètica de l'instant"],
    "Acadèmia Gaia": ["Literatura - Acadèmia Gaia"],
    "Diálogos filosóficos con mi amigo Pi": [
        "Filosofia - Converses amb Pi",
        "Filosofia - Diálogos con mi amigo Pi",
    ],
}


def fragments_reals_del_llibre(titol, n=4):
    """Retorna n fragments literals del llibre, repartits al llarg de l'obra,
    llegits de l'índex local de l'Avatar. Llista buida si no es pot."""
    fonts = FONTS_LLIBRES.get(titol)
    if not fonts:
        return []
    try:
        import numpy as np
        data = np.load(CORPUS_NPZ, allow_pickle=True)
        docs = data["documents"].tolist()
        metas = [json.loads(m) for m in data["metadatas"].tolist()]
        idxs = [i for i, m in enumerate(metas) if m.get("source") in fonts]
        if not idxs:
            return []
        pas = max(1, len(idxs) // n)
        return [docs[i] for i in idxs[::pas][:n]]
    except Exception as e:
        print("[generador] No s'han pogut llegir els fragments reals: {}".format(e))
        return []


# ---------------------------------------------------------------------------
# BANC DE CITES DELS LLIBRES (frases triades per Sergi)
# ---------------------------------------------------------------------------
# Els dies de llibre, el post és SENZILL: una FRASE LITERAL d'un llibre, la
# cita que diu de quin llibre és, i una imatge evocadora. Sense discurs, sense
# web, sense hashtags (decisió Sergi 2026-07-03). Les frases les tria Sergi i
# viuen a dades/cites_llibres.json ({ "Títol del llibre": ["frase", ...] }).
from pathlib import Path

FITXER_CITES = Path(__file__).parent / "dades" / "cites_llibres.json"

# Motiu visual per llibre: NOMÉS símbols, objectes o natura (MAI persones,
# cares o mans; MAI text dins la imatge — els generadors els censuren). Cada
# llibre té la seva identitat visual, coherent entre les seves frases.
MOTIUS_IMATGE = {
    "Nara":
        "unes ales de papallona iridescents entre fulles d'un bosc, "
        "amb llum tènue i daurada de matí",
    "La vida d'en George":
        "un engranatge de rellotgeria antic entrellaçat amb una branca amb "
        "fulles verdes, llum suau i neta",
    "Inspector Montoliu":
        "la llum d'un fanal solitari en un carrer moll de nit, amb ombres "
        "allargades i reflexos a l'asfalt",
    "Una Història Sentimental":
        "unes fotografies antigues escampades sobre una taula de fusta, amb "
        "llum càlida de tarda",
    "Contes a la vora del gel":
        "un llac glaçat amb branques nues i una boira lleugera, amb llum "
        "freda i neta de matí d'hivern",
    "Ànima Material":
        "una ploma reposant sobre un full de paper en blanc vora una finestra, "
        "amb llum tènue",
    "Ètica i estètica de l'instant":
        "un rellotge de sorra amb la llum travessant els grans de sorra, "
        "amb un fons net i càlid",
    "Acadèmia Gaia":
        "una nebulosa estelada damunt un paisatge de muntanya al capvespre, "
        "amb una llum serena i misteriosa",
}
MOTIU_IMATGE_PER_DEFECTE = (
    "un llibre obert reposant vora una finestra, amb llum càlida i suau"
)


def _carrega_cites():
    """Llegeix el banc de frases triades per Sergi.
    Retorna {títol: [frases no buides]}; {} si el fitxer no existeix o és buit."""
    try:
        with open(FITXER_CITES, "r", encoding="utf-8") as f:
            dades = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    net = {}
    for titol, llista in (dades.items() if isinstance(dades, dict) else []):
        if isinstance(llista, list):
            frases = [c.strip() for c in llista if isinstance(c, str) and c.strip()]
            if frases:
                net[titol] = frases
    return net


def _cita_del_dia(data):
    """Retorna (frase, títol_del_llibre) per al dia, rotant lentament dins de
    les frases del llibre del dia. (None, títol) si el llibre no té cap frase."""
    ordre = _ordre_llibres()
    n = len(ordre)
    comptador = data.toordinal() // 4      # nº de dia de llibre
    pos = comptador % n
    titol = ordre[pos]
    frases = _carrega_cites().get(titol) or []
    if not frases:
        return None, titol
    # Quantes vegades ha sortit AQUEST llibre fins avui (comptant les seves
    # aparicions dins de l'ordre de rotació, que pot ser més d'una per cicle si
    # és el prioritari). Així la frase avança a cada aparició i passen totes.
    aparicio = (comptador // n) * ordre.count(titol) + ordre[:pos].count(titol)
    return frases[aparicio % len(frases)], titol


def _post_cita(frase, titol):
    """El text del post: la frase entre cometes i la cita del llibre a sota.
    Res més (ni web, ni hashtags, ni enllaços)."""
    neta = frase.strip().strip('«»"“”').strip()
    return "«{}»\n\n— {}".format(neta, titol)


def _genera_posts_cita(data):
    """Dia de llibre amb el format nou: la mateixa FRASE del llibre als tres
    canals, amb la cita del títol i una imatge evocadora del llibre. No fa cap
    crida a cap model: el text és literal i triat per Sergi.
    Si el llibre del dia encara no té cap frase al banc, retorna
    {'sense_cita': True, 'llibre': títol} perquè qui crida decideixi el pla B."""
    frase, titol = _cita_del_dia(data)
    if not frase:
        return {"sense_cita": True, "llibre": titol}
    bloc = {"text": _post_cita(frase, titol),
            "imatge": MOTIUS_IMATGE.get(titol, MOTIU_IMATGE_PER_DEFECTE)}
    if len(bloc["text"]) > 270:
        print("[generador] AVÍS: la frase de «{}» passa de 270 caràcters ({}); "
              "a X pot no cabre.".format(titol, len(bloc["text"])))
    return {
        "linkedin": dict(bloc),
        "twitter": dict(bloc),
        "instagram": dict(bloc),
        "mode": "cita de llibre",
        "tema": "Una frase de «{}»".format(titol),
        "campanya": "cita",
    }


# ---------------------------------------------------------------------------
# L'AVATAR: la font de veritat
# ---------------------------------------------------------------------------
# L'Avatar d'en Sergi (RAG a Cloud Run, entrenat amb el seu corpus real) és
# qui aporta les idees i els fets de cada dia. Gemini només dona FORMA de
# post al que l'Avatar ha dit. Si l'Avatar no respon, es treballa només amb
# el catàleg, en règim estricte de no-invenció.

AVATAR_URL = "https://avatar-sergi-481669294174.europe-west1.run.app/chat"
AVATAR_TIMEOUT = 90

# Títols reservats (inèdits/concursos): no poden aparèixer MAI en cap post
TITOLS_EXCLOSOS = [
    "Poètica carnal", "Poemes de la Carn", "Poemes carnals", "Poètica de la carn",
]

# Frases que delaten que l'Avatar ha declinat la pregunta (guard anti-invenció)
MARCADORS_REBUIG = [
    "em sap greu", "no puc atendre", "no forma part de la meva biblioteca",
    "no tinc documentat", "no tinc documentada", "prefereixo no improvisar",
]

# Una pregunta per a cada mode del dia (mateix índex que MODES)
PREGUNTES_AVATAR = [
    "Diga'm UNA tesi breu i discutible sobre el temps, la memòria, l'instant "
    "o la realitat — una afirmació amb què algú podria no estar d'acord i "
    "voldria rebatre't. En primera persona, amb un exemple o una referència "
    "concreta. 3-5 frases. Pren partit: res de reflexions vagues que tothom "
    "signaria.",

    "Parla'm del teu llibre «{llibre}»: per què l'hauria de llegir algú avui? "
    "Què hi trobarà que no trobi enlloc? 4-6 frases, sense fer sinopsi. "
    "Sigues concret: digues alguna cosa que només qui l'ha escrit pot dir "
    "(en tens el text al corpus). Si aquest títol no és a la teva biblioteca, "
    "tria una ALTRA obra teva, digues-ne el títol, i fes el mateix.",

    "Quina és la teva posició avui sobre la relació entre literatura i "
    "intel·ligència artificial? Una idea concreta i discutible, en primera "
    "persona, 4-6 frases. Pren partit clarament: res de «d'una banda… de "
    "l'altra».",

    "Tria una idea central de la teva obra «{llibre}» i defensa-la en 4-6 "
    "frases, amb un exemple concret del llibre (en tens el text al corpus). "
    "La idea ha de ser discutible: algú ha de poder pensar que t'equivoques. "
    "Si aquest títol no és a la teva biblioteca, tria una ALTRA obra teva, "
    "digues-ne el títol, i fes el mateix.",

    "Per què fa falta un periodisme constructiu com el d'El Bon Diari "
    "(bondiari.com)? Diga'm la teva raó de fons, en primera persona, 4-6 "
    "frases, sense propaganda. Pren partit contra alguna cosa concreta del "
    "periodisme actual.",

    "Què significa per a tu que la gent pugui conversar amb una versió digital "
    "teva a sergicastillo.com? Una posició honesta i discutible, amb llums i "
    "ombres, 4-6 frases. Digues alguna cosa que sorprengui.",

    "Diga'm UNA tesi breu amb força que contradigui un lloc comú del món "
    "editorial o literari — una afirmació que algú voldria discutir-te. "
    "2-4 frases en primera persona, amb un exemple concret.",
]

PREGUNTA_RESERVA = (
    "Diga'm UNA tesi breu, amb força, que sostinguis avui — una afirmació que "
    "algú podria voler discutir-te, sobre la literatura, el temps, la memòria "
    "o l'època. 2-4 frases en primera persona, amb un exemple o una referència "
    "concreta. Pren partit: res de reflexions vagues."
)


def _instruccio_exclusions():
    llistat = ", ".join("«{}»".format(t) for t in TITOLS_EXCLOSOS)
    return ("\n\nIMPORTANT: no mencionis mai aquests títols, ni hi facis cap "
            "referència: {}. Són reservats.".format(llistat))


def _crida_avatar(pregunta):
    """Una crida HTTP a l'Avatar, amb reintents si la xarxa falla.
    Retorna el text de resposta o ''."""
    for intent in range(1, REINTENTS_XARXA + 1):
        try:
            r = requests.post(
                AVATAR_URL,
                json={"message": pregunta, "session_id": None},
                timeout=AVATAR_TIMEOUT,
            )
            r.raise_for_status()
            return (r.json().get("response") or "").strip()
        except Exception as e:
            if intent < REINTENTS_XARXA and _es_error_transitori(e):
                espera = ESPERA_XARXA[min(intent - 1, len(ESPERA_XARXA) - 1)]
                print("[generador] L'Avatar no respon ({}); reintent {}/{} en {}s".format(
                    e, intent, REINTENTS_XARXA, espera))
                time.sleep(espera)
                continue
            print("[generador] L'Avatar no ha respost ({}).".format(e))
            return ""
    return ""


def _ha_declinat(resposta):
    baix = resposta.lower()
    return any(m in baix for m in MARCADORS_REBUIG)


def consulta_avatar_del_dia(data):
    """Fa a l'Avatar la pregunta del mode del dia. Si declina (tema fora del
    seu corpus), prova una pregunta genèrica de reserva. Retorna el material
    ('' si l'Avatar no està disponible)."""
    idx, _ = _get_mode_del_dia(data)
    pregunta = PREGUNTES_AVATAR[idx].format(llibre=_get_llibre_del_dia(data))
    resposta = _crida_avatar(pregunta + _instruccio_exclusions())
    if resposta and not _ha_declinat(resposta):
        return resposta
    if resposta:
        print("[generador] L'Avatar ha declinat la pregunta del dia; provo la de reserva.")
        resposta = _crida_avatar(PREGUNTA_RESERVA + _instruccio_exclusions())
        if resposta and not _ha_declinat(resposta):
            return resposta
    return ""


def _construir_prompt(data, material="", tipus_material="cap"):
    """Construeix el prompt complet per a Gemini segons la font del dia:
    'fragments' (text literal del llibre), 'avatar' (resposta de l'Avatar)
    o 'cap' (règim estricte de només-catàleg)."""
    idx_mode, nom_mode = _get_mode_del_dia(data)
    llibre_del_dia = _get_llibre_del_dia(data)
    data_fmt = data.strftime("%A %d de %B de %Y")

    if tipus_material == "fragments":
        bloc_avatar = (
            "FRAGMENTS REALS DEL LLIBRE «" + llibre_del_dia + "» — text literal "
            "de l'obra, la teva ÚNICA font de veritat d'avui:\n"
            "Tota idea, escena o detall del post ha de ser PRESENT en aquests "
            "fragments o deduir-se'n directament. Pots citar-ne frases literals "
            "curtes (són reals). PROHIBIT atribuir al llibre res que no es vegi "
            "aquí: si els fragments no donen per a una gran tesi, fes un post "
            "petit i cert sobre el que SÍ que s'hi veu.\n"
            "-----\n" + material.strip() + "\n-----"
        )
    elif tipus_material == "avatar":
        bloc_avatar = (
            "MATERIAL DE L'AVATAR (la teva font de veritat d'avui):\n"
            "El text següent és la resposta d'avui de l'Avatar d'en Sergi, "
            "entrenat amb el seu corpus real. D'AQUÍ han de sortir les idees, "
            "els fets i les eventuals cites dels 3 posts. Pots reformular, "
            "retallar i adaptar el to a cada xarxa, però NO afegir-hi fets nous.\n"
            "Si aquest material parla d'una obra concreta, aquella és l'obra "
            "del dia (mana per sobre del llibre de referència de sota).\n"
            "-----\n" + material.strip() + "\n-----"
        )
    else:
        bloc_avatar = (
            "(Avui no hi ha material extern: treballa NOMÉS amb el catàleg "
            "de dalt, sense cap fet, cita ni anècdota que no hi sigui.)"
        )

    prompt = """Ets el creador de contingut de Sergi Castillo Lapeira per a xarxes socials (LinkedIn, X i Instagram).
Escrius de manera càlida i propera, com un amic que recomana una bona història. Mai com un professor ni com un anunci.

OBJECTIU: que la gent tingui ganes de llegir els llibres de Sergi, explicant-los de manera senzilla i atractiva.

{cataleg}

TEMA D'AVUI (mode {idx}): {mode}
LLIBRE DE REFERÈNCIA D'AVUI: {llibre}

TO I LLENGUATGE (la part més important):
- Llenguatge planer i de cada dia. Frases curtes. Paraules de tota la vida.
- RES de registre acadèmic ni intel·lectual. RES de tecnicismes ni paraules rebuscades.
- RES de vulgaritats ni paraulotes: amable i educat sempre.
- Gens solemne. Ni autoajuda de manual ni frase de calendari.
- Pots parlar dels llibres, dels personatges i de les seves idees. Fes-ho com qui explica una història que enganxa.
- VEU IMPERSONAL — REGLA CABDAL: CAP primera persona, ni biogràfica ni de pensament. PROHIBIT "jo", i els verbs en primera persona "crec", "penso", "opino", "defenso", "sento", "escric", "vaig escriure", "em sembla", "m'interessa"... i els possessius de l'autor "el meu", "la meva", "els meus", "les meves".
- Les idees s'afirmen DIRECTAMENT, com a veritats sobre el món: no "crec que la literatura és resistència", sinó "la literatura és resistència". Les obres es mencionen en TERCERA PERSONA: no "el meu llibre Nara" ni "a Nara, exploro...", sinó "Nara explica..." o "A Contes a la vora del gel, la natura és...". L'autor mai apareix com a protagonista.
- Pots adreçar-te al lector de "tu". Res d'anècdotes ni vida de l'autor (ni estudis, ni quan/on/com va escriure res).

ESTIL — NORMES DURES (un post que en violi una és un mal post):
- Una idea per post. A la PRIMERA frase ja s'ha de saber de què parles.
- Màxim UNA metàfora per post, i senzilla.
- Màxim UNA pregunta per post, només al final i només si és de veritat. Cap pregunta retòrica.
- No facis enumeracions de tres ("la llum, el temps i la memòria"). No comencis amb gerundi ("Pensant...", "Mirant...").
- La fórmula "no és X, sinó Y": màxim UNA per post, i només si diu alguna cosa de debò.
- PROHIBIT usar: "mirall", "essència", "ànima", "fibra", "vertigen", "implacable", "efímer", "etern", "ens travessa", "es desplega", "es difumina", "es dilueix", "teló de fons".
- No inventis detalls dels llibres que no siguin al catàleg de dalt (personatges, escenes o cites falses). Si no n'estàs segur, queda't en general.
- Millor una observació petita i certa que una gran frase buida.
- TEST DEL MÒBIL: si un desconegut ho llegís al metro, ho hauria d'entendre de seguida i pensar "sí, és veritat" o "no hi havia caigut".

FINAL:
- A X i LinkedIn: acaba amb "https://sergicastillo.com" (AMB https://, perquè surti com a enllaç clicable; sense punt final).
- A Instagram: acaba amb "sergicastillo.com · enllaç a la bio" en línia pròpia just ABANS del bloc d'hashtags (a Instagram els enllaços del text no són clicables, per això s'envia a la bio).

DATA: {data}

Genera 3 posts per a avui. LONGITUDS (límits ESTRICTES — passar-se'n és invalidar el post):
- twitter: màx 240 caràcters, sense hashtags, una sola idea clara i propera
- linkedin: 40-70 paraules, càlid i proper, gens corporatiu
- instagram: 30-60 paraules + 5-8 hashtags propers i quotidians al final (gens acadèmics), en línia nova

IMATGES: cada post (linkedin, twitter, instagram) porta el seu camp "imatge": una
descripció visual concreta en català (15-25 paraules) de l'escena per a la imatge.
REGLA CABDAL: descriu NOMÉS objectes, símbols, llocs o elements de la natura
relacionats amb el contingut del post (un llibre obert, unes ales de papallona, una
finestra amb pluja, un rellotge antic, un riu, una ploma, un mapa…). MAI persones,
ni siluetes humanes, ni cares, ni mans, ni personatges — els generadors d'imatge els
censuren o els fan genèrics, i la imatge acaba sense relació amb el text. SENSE text
dins la imatge. La imatge ha d'evocar DE QUÈ VA el post (si parla d'un llibre, un
objecte simbòlic d'aquell llibre). MOLT IMPORTANT: les TRES descripcions han de ser
ESCENES DIFERENTS entre elles (objectes i enquadraments distints), però totes lligades
al tema del dia.
Mai descriguis la mateixa escena dues vegades.

Respon ÚNICAMENT amb JSON vàlid, sense cap text addicional, en aquest format exacte:
{{
  "linkedin": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "twitter": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "instagram": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "mode": "nom curt del tema (1-5 paraules)",
  "tema": "resum breu del tema d'avui (1 frase)"
}}""".format(
        cataleg=CATALEG_LLIBRES,
        data=data_fmt,
        idx=idx_mode,
        mode=nom_mode,
        llibre=llibre_del_dia,
    )

    # El material de l'Avatar s'insereix al final (fora del .format, perquè
    # pot contenir claus {} que el trencarien)
    return prompt.replace("__MATERIAL_AVATAR__", bloc_avatar)


# Control de qualitat per codi: el prompt prohibeix aquestes paraules i
# fórmules, però Gemini de tant en tant les ignora. Si el text generat en
# conté, es regenera (fins a 3 intents) i es queda l'intent més net.
PARAULES_PROHIBIDES = [
    "mirall", "essència", "ànima", "fibra", "vertigen", "implacable",
    "efímer", "etern", "ens travessa", "es desplega", "es difumina",
    "es dilueix", "teló de fons", "frontera porosa",
]

# Veu impersonal: cap "jo" (ni biogràfic ni de pensament). Marcadors de
# primera persona de l'autor que NO poden aparèixer als posts.
PRIMERA_PERSONA = [
    r"\bjo\b", r"\bmeu\b", r"\bmeva\b", r"\bmeus\b", r"\bmeves\b", r"\bvaig\b",
    r"\bcrec\b", r"\bpenso\b", r"\bopino\b", r"\bdefenso\b", r"\bsostinc\b",
    r"\bafirmo\b", r"\bconsidero\b", r"\bescric\b", r"\bescrivia\b",
    r"\bexploro\b", r"\bexplico\b", r"\bnarro\b", r"\bmostro\b", r"\bplantejo\b",
    r"\bproposo\b", r"\breflexiono\b", r"\bem sembla\b", r"m'interessa",
    r"m'agrada", r"m'apassiona",
]


def _violacions_estil(posts):
    """Retorna la llista de violacions d'estil (buida si tot és correcte)."""
    v = []
    for plataforma in ["linkedin", "twitter", "instagram"]:
        text = (posts.get(plataforma) or {}).get("text", "")
        baix = text.lower()
        for paraula in PARAULES_PROHIBIDES:
            if paraula in baix:
                v.append("{}: paraula prohibida '{}'".format(plataforma, paraula))
        for patro in PRIMERA_PERSONA:
            m = re.search(patro, baix)
            if m:
                v.append("{}: primera persona '{}'".format(plataforma, m.group(0)))
                break  # un marcador ja és prou per regenerar
        for titol in TITOLS_EXCLOSOS:
            if titol.lower() in baix:
                v.append("{}: títol reservat '{}'".format(plataforma, titol))
        # La fórmula "no és X, sinó Y" és legítima si porta contingut;
        # el que delata el tic retòric és repetir-la dins del mateix post
        formules = re.findall(r"no (?:és|són) [^.;:!?\n]{0,60}, sinó", baix)
        if len(formules) > 1:
            v.append("{}: fórmula 'no és X, sinó Y' repetida ({}x)".format(
                plataforma, len(formules)))

    li = (posts.get("linkedin") or {}).get("text", "")
    if len(li.split()) > 75:
        v.append("linkedin: massa llarg ({} paraules)".format(len(li.split())))

    tw = (posts.get("twitter") or {}).get("text", "")
    if len(tw) > 270:
        v.append("twitter: massa llarg ({} caràcters)".format(len(tw)))

    ig = (posts.get("instagram") or {}).get("text", "")
    cos_ig = " ".join(l for l in ig.split("\n") if not l.strip().startswith("#"))
    if len(cos_ig.split()) > 65:
        v.append("instagram: massa llarg ({} paraules)".format(len(cos_ig.split())))

    return v


# ===========================================================================
# CARRIL ARREL — promoció de l'app Arrel (longevitat) en dies alterns
# ===========================================================================
# Arrel NO és un llibre ni surt de l'Avatar: és un producte propi (app gratuïta
# de longevitat). En els dies de publicació alterns, els 3 posts parlen d'Arrel
# amb la seva veu (anti-soroll) i el seu enllaç (App Store), no de la web dels
# llibres. Decisió usuari 2026-07-01: 1 de cada 2 publicacions és d'Arrel; CTA =
# App Store (baixada directa).

# Enllaç curt i universal a la fitxa de l'App Store (sense codi de país).
ARREL_URL = "https://apps.apple.com/app/id6758808269"

# A Instagram els enllaços del text no són clicables i la bio és de
# sergicastillo.com; per això a IG es diu com trobar l'app (és cercable).
ARREL_CTA_IG = "Arrel · gratis a l'App Store (cerca «Arrel»)"

# Hashtags propis d'Arrel (longevitat/salut), NO els de llibres.
ARREL_HASHTAGS = "#Arrel #longevitat #envellirbé #salut #hàbits #benestar #vitalitat"

ARREL_BRIEF = """QUÈ ÉS ARREL (el producte que promocionem avui):
Arrel és una app gratuïta (sense pagaments) amb un únic objectiu: frenar l'envelliment al màxim.
NO és una app de fitness, ni de motivació, ni de «benestar» superficial.
Premissa: l'envelliment s'accelera allà on hi ha rigidesa, evitació i repetició.
Arrel intervé en les cinc àrees on el desgast és més evident:
  1. Deteriorament funcional del cos.
  2. Rigidesa cognitiva.
  3. Estrès crònic.
  4. Aïllament relacional.
  5. Estancament identitari.
Com funciona: cicles curts d'observació i acció. Detecta on t'estanques, redueix el soroll i
aplica la fricció mínima necessària per recuperar flexibilitat i moviment. Sense notificacions
buides, sense tecnicismes, sense promeses falses de felicitat. Només criteri i acció.
Idea força: «Envellir és inevitable, oxidar-se és opcional.»
"""

# Angles que roten per dia d'Arrel (perquè no repeteixi sempre el mateix).
ARREL_MODES = [
    "La idea central d'Arrel: envellir és inevitable, oxidar-se és opcional. Per què cap app de benestar ho mira així.",
    "UNA de les cinc àrees on Arrel actua (el cos, la rigidesa cognitiva, l'estrès, l'aïllament o l'estancament): què és i per què importa.",
    "El contrast amb el soroll del benestar de moda i el biohacking: res de notificacions buides, només criteri i acció.",
    "Com treballa Arrel per dins: cicles curts d'observació i acció, la fricció mínima per tornar a moure't.",
    "Una observació certa sobre com la rigidesa i la repetició envelleixen, i com Arrel hi intervé.",
]


def _es_dia_arrel(data):
    """En els dies de publicació (la màquina publica en ordinal parell), la
    meitat es dediquen a Arrel, alternant literatura / Arrel. True = dia Arrel."""
    return (data.toordinal() // 2) % 2 == 1


def _get_mode_arrel(data):
    """Angle d'Arrel per a la data (rota per dia de publicació)."""
    idx = (data.toordinal() // 2) % len(ARREL_MODES)
    return idx, ARREL_MODES[idx]


def _construir_prompt_arrel(data):
    """Prompt per als posts d'Arrel: mateixa veu sòbria i impersonal que la
    resta, però promocionant l'app (no els llibres), amb CTA a l'App Store."""
    idx_mode, nom_mode = _get_mode_arrel(data)
    data_fmt = data.strftime("%A %d de %B de %Y")

    prompt = """Ets el creador de contingut de l'app ARREL per a xarxes socials (LinkedIn, X i Instagram).
Escrius de manera clara, sòbria i directa. Mai com un anunci cridaner ni com un gurú del benestar.

OBJECTIU: que la gent tingui ganes de baixar Arrel, explicant amb honestedat què fa i per què és diferent.

{brief}

ANGLE D'AVUI (mode {idx}): {mode}

TO I LLENGUATGE (la part més important):
- Llenguatge planer i de cada dia. Frases curtes. Paraules de tota la vida.
- RES de registre acadèmic ni de màrqueting inflat. RES de tecnicismes ni paraules rebuscades.
- Gens solemne. Ni autoajuda de manual ni frase de calendari. Res de promeses de felicitat.
- To d'Arrel: anti-soroll, honest, amb criteri. Ven sense enganyar ni exagerar.
- VEU IMPERSONAL — REGLA CABDAL: CAP primera persona, ni biogràfica ni de pensament. PROHIBIT "jo", i els verbs en primera persona "crec", "penso", "opino", "defenso", "sento"..., i els possessius "el meu", "la meva", "els meus", "les meves". Les idees s'afirmen DIRECTAMENT. Pots adreçar-te al lector de "tu".

ESTIL — NORMES DURES (un post que en violi una és un mal post):
- Una idea per post. A la PRIMERA frase ja s'ha de saber de què parles.
- Màxim UNA metàfora per post, i senzilla.
- Màxim UNA pregunta per post, només al final i només si és de veritat. Cap pregunta retòrica.
- No facis enumeracions de tres. No comencis amb gerundi ("Pensant...", "Mirant...").
- La fórmula "no és X, sinó Y": màxim UNA per post, i només si diu alguna cosa de debò.
- PROHIBIT usar: "mirall", "essència", "ànima", "fibra", "vertigen", "implacable", "efímer", "etern", "ens travessa", "es desplega", "es difumina", "es dilueix", "teló de fons".
- No prometis resultats mèdics ni curacions. Arrel ajuda a mantenir flexibilitat i moviment; no cura ni allarga la vida de forma garantida.
- Millor una observació petita i certa que una gran frase buida.
- TEST DEL MÒBIL: si un desconegut ho llegís al metro, ho hauria d'entendre de seguida i pensar "sí, és veritat" o "no hi havia caigut".

FINAL (crida a l'acció cap a l'App Store):
- A X i LinkedIn: acaba amb "{url}" (l'enllaç de l'App Store, sense punt final).
- A Instagram: acaba amb "{cta_ig}" en línia pròpia just ABANS del bloc d'hashtags (a Instagram els enllaços del text no són clicables).

DATA: {data}

Genera 3 posts per a avui. LONGITUDS (límits ESTRICTES — passar-se'n és invalidar el post):
- twitter: màx 240 caràcters, sense hashtags, una sola idea clara
- linkedin: 40-70 paraules, sobri i directe, gens corporatiu
- instagram: 30-60 paraules + aquests hashtags EXACTES al final, en línia nova: {hashtags}

IMATGES: cada post (linkedin, twitter, instagram) porta el seu camp "imatge": una
descripció visual concreta en català (15-25 paraules) de l'escena per a la imatge.
REGLA CABDAL: descriu NOMÉS objectes, símbols, llocs o elements de la natura que evoquin
vitalitat, arrels, moviment, calma o el pas del temps (una arrel forta a la terra, un arbre
vell i sa, aigua que corre, una pedra polida pel riu, llum del matí en un bosc, un camí
obert…). MAI persones, ni siluetes humanes, ni cares, ni mans — els generadors d'imatge els
censuren o els fan genèrics. SENSE text dins la imatge. Les TRES descripcions han de ser
ESCENES DIFERENTS entre elles, però totes lligades a l'angle d'avui.

Respon ÚNICAMENT amb JSON vàlid, sense cap text addicional, en aquest format exacte:
{{
  "linkedin": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "twitter": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "instagram": {{
    "text": "...",
    "imatge": "descripció visual de l'escena (diferent de les altres dues)"
  }},
  "mode": "nom curt de l'angle (1-5 paraules)",
  "tema": "resum breu de l'angle d'avui (1 frase)"
}}""".format(
        brief=ARREL_BRIEF,
        data=data_fmt,
        idx=idx_mode,
        mode=nom_mode,
        url=ARREL_URL,
        cta_ig=ARREL_CTA_IG,
        hashtags=ARREL_HASHTAGS,
    )
    return prompt


def _finalitza_arrel(posts):
    """Xarxa de seguretat: garanteix l'enllaç de l'App Store a X/LinkedIn i el
    CTA + hashtags d'Arrel a Instagram, per si el model se'ls deixa."""
    for plataforma in ["linkedin", "twitter"]:
        bloc = posts.get(plataforma)
        if isinstance(bloc, dict) and bloc.get("text"):
            t = bloc["text"].rstrip()
            if "apps.apple.com" not in t.lower():
                sep = " " if plataforma == "twitter" else "\n\n"
                bloc["text"] = t + sep + ARREL_URL

    ig = posts.get("instagram")
    if isinstance(ig, dict) and ig.get("text"):
        t = ig["text"].rstrip()
        if "#" not in t:
            t = t + "\n\n" + ARREL_HASHTAGS
        if "app store" not in t.lower():
            # Inserir el CTA just abans del primer hashtag
            linies = t.split("\n")
            i = len(linies)
            while i > 0 and (not linies[i - 1].strip() or linies[i - 1].lstrip().startswith("#")):
                i -= 1
            cos = "\n".join(linies[:i]).rstrip()
            hashtags = "\n".join(linies[i:]).strip()
            t = cos + "\n\n" + ARREL_CTA_IG + ("\n\n" + hashtags if hashtags else "")
        ig["text"] = t


def _genera_posts_arrel(client, data):
    """Genera els 3 posts d'Arrel amb el mateix control de qualitat que els
    literaris (fins a 3 intents, es queda el més net), però NO afegeix la web
    dels llibres ni els hashtags de llibres."""
    prompt = _construir_prompt_arrel(data)
    millor = None
    millor_violacions = None
    for intent in range(3):
        resultat = _intent_generacio(client, prompt)
        if "error" in resultat:
            millor = resultat
            break
        violacions = _violacions_estil(resultat)
        if not violacions:
            millor, millor_violacions = resultat, []
            break
        print("[generador][arrel] Intent {}: {} violacions — {}".format(
            intent + 1, len(violacions), "; ".join(violacions)))
        if millor is None or "error" in millor or len(violacions) < len(millor_violacions):
            millor, millor_violacions = resultat, violacions

    if millor is None:
        return {"error": "Gemini no ha retornat res (Arrel) en cap dels 3 intents."}
    if "error" in millor:
        return millor
    _finalitza_arrel(millor)
    # Marca perquè la resta del sistema no hi afegeixi la web dels llibres.
    millor["campanya"] = "arrel"
    return millor


def genera_posts_dia(data_str=None):
    """
    Genera els 3 posts del dia via Gemini, amb control de qualitat:
    si el resultat viola les normes d'estil (paraules prohibides,
    llargades), es regenera fins a 3 vegades i es queda el millor intent.

    Args:
        data_str: Data en format 'YYYY-MM-DD'. Si és None, usa avui.

    Returns:
        Dict amb claus: linkedin, twitter, instagram, mode, tema
        En cas d'error retorna dict amb clau 'error'.
    """
    # Obtenir la clau d'API (variable d'entorn o dades/keys.json)
    api_key = get_key("GEMINI_API_KEY")
    if not api_key:
        return {
            "error": (
                "Falta GEMINI_API_KEY. Afegeix-la a dades/keys.json "
                "o a ~/.zshrc: export GEMINI_API_KEY='la_teva_clau'"
            )
        }

    # Parsejar la data
    try:
        if data_str:
            data = datetime.date.fromisoformat(data_str)
        else:
            data = datetime.date.today()
    except ValueError:
        return {"error": "Format de data invàlid: '{}'. Usa YYYY-MM-DD.".format(data_str)}

    # Configurar client Gemini (nou SDK google-genai)
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        return {"error": "Error configurant Gemini: {}".format(e)}

    # CARRIL ARREL: en els dies alterns, els posts promocionen l'app Arrel
    # (longevitat), no els llibres. Té veu, brief i enllaç (App Store) propis.
    if _es_dia_arrel(data):
        return _genera_posts_arrel(client, data)

    # DIES DE LLIBRE (format nou, decisió Sergi 2026-07-03): el post és una
    # FRASE literal del llibre + la cita del títol + una imatge evocadora.
    # No hi ha discurs ni model pel mig; la frase la tria Sergi.
    posts_cita = _genera_posts_cita(data)
    if not posts_cita.get("sense_cita"):
        return posts_cita
    print("[generador] El llibre «{}» encara no té cap frase al banc "
          "(dades/cites_llibres.json); recorro al generador de discurs com a "
          "xarxa de seguretat.".format(posts_cita.get("llibre")))

    # 1) Contingut general: els posts ja no surten del corpus personal ni del
    #    catàleg de llibres. Es generen directament a partir del tema del dia.
    idx_mode, _ = _get_mode_del_dia(data)
    material, tipus_material = "", "cap"

    # 2) Generar amb control de qualitat: fins a 3 intents, quedant-se el més net
    prompt = _construir_prompt(data, material, tipus_material)
    millor = None
    millor_violacions = None
    for intent in range(3):
        resultat = _intent_generacio(client, prompt)
        if "error" in resultat:
            # _intent_generacio ja ha reintentat la xarxa per dins; no té sentit
            # repetir-ho aquí (el bucle és per a l'estil, no per a la connexió).
            millor = resultat
            break
        violacions = _violacions_estil(resultat)
        if not violacions:
            millor, millor_violacions = resultat, []
            break
        print("[generador] Intent {}: {} violacions d'estil — {}".format(
            intent + 1, len(violacions), "; ".join(violacions)))
        if millor is None or "error" in millor or len(violacions) < len(millor_violacions):
            millor, millor_violacions = resultat, violacions

    if millor is None:
        return {"error": "Gemini no ha retornat res en cap dels 3 intents."}
    if "error" in millor:
        return millor
    if millor_violacions:
        print("[generador] AVÍS: cap intent perfecte; es publica el millor "
              "({} violacions).".format(len(millor_violacions)))

    # Xarxa de seguretat: Instagram sempre amb hashtags
    ig = millor.get("instagram") or {}
    if isinstance(ig, dict) and ig.get("text") and "#" not in ig["text"]:
        ig["text"] = ig["text"].rstrip() + (
            "\n\n#llibres #lectura #novel·la #llegir #LlibresEnCatalà"
        )

    # Garantia final: només afegim la web si està activat. Per defecte, no:
    # els posts diaris ja no són promocionals (vegeu INCLOURE_WEB a dalt).
    if INCLOURE_WEB:
        afegeix_web_a_posts(millor)

    return millor


def _intent_generacio(client, prompt):
    """Una crida a Gemini + parseig robust. Retorna el dict de posts
    normalitzat o {'error': ...}. Reintenta si la xarxa falla."""
    resposta = None
    for intent in range(1, REINTENTS_XARXA + 1):
        try:
            resposta = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.7,
                    # Els models Gemini 3.x ja no accepten thinking_budget (el
                    # paràmetre de l'era 2.5); es deixa el thinking per defecte
                    # i s'amplia el límit perquè els tokens de raonament no
                    # escurcin el JSON de sortida.
                    max_output_tokens=8192,
                ),
            )
            break
        except Exception as e:
            if intent < REINTENTS_XARXA and _es_error_transitori(e):
                espera = ESPERA_XARXA[min(intent - 1, len(ESPERA_XARXA) - 1)]
                print("[generador] Gemini no respon ({}); reintent {}/{} en {}s".format(
                    e, intent, REINTENTS_XARXA, espera))
                time.sleep(espera)
                continue
            return {"error": "Error cridant Gemini: {}".format(e)}
    if resposta is None:
        return {"error": "Gemini no ha respost després de {} intents.".format(REINTENTS_XARXA)}

    # Parsejar la resposta JSON — extracció robusta
    text_resposta = resposta.text.strip()

    # Estratègia 1: eliminar blocs de codi markdown (```json ... ```)
    text_net = re.sub(r'^```(?:json)?\s*', '', text_resposta, flags=re.MULTILINE)
    text_net = re.sub(r'\s*```\s*$', '', text_net, flags=re.MULTILINE).strip()

    # Estratègia 2: extreure el primer objecte JSON {…} de la resposta
    # (útil si Gemini afegeix text explicatiu al voltant)
    match = re.search(r'\{[\s\S]*\}', text_net)
    if match:
        text_net = match.group(0)

    try:
        resultat = json.loads(text_net)
    except json.JSONDecodeError as e:
        # Estratègia 3: intentar parsejar el text original sense netejar
        try:
            match2 = re.search(r'\{[\s\S]*\}', text_resposta)
            if match2:
                resultat = json.loads(match2.group(0))
            else:
                raise ValueError("no s'ha trobat cap objecte JSON")
        except Exception:
            return {
                "error": "Gemini ha retornat JSON invàlid: {}".format(e),
                "text_cru": text_resposta[:600],
            }

    # Validar estructura mínima
    camps_requerits = ["linkedin", "twitter", "instagram", "mode", "tema"]
    for camp in camps_requerits:
        if camp not in resultat:
            return {"error": "Resposta incompleta de Gemini: falta el camp '{}'".format(camp)}

    # Assegurar que cada plataforma té el camp 'text' i 'imatge'
    # (la descripció d'imatge només la genera Instagram; les altres van sense)
    for plataforma in ["linkedin", "twitter", "instagram"]:
        if isinstance(resultat[plataforma], dict):
            if "text" not in resultat[plataforma]:
                resultat[plataforma]["text"] = str(resultat[plataforma])
        else:
            resultat[plataforma] = {"text": str(resultat[plataforma])}
        imatge = resultat[plataforma].get("imatge")
        if isinstance(imatge, str) and imatge.strip():
            resultat[plataforma]["imatge"] = imatge.strip()
        else:
            resultat[plataforma]["imatge"] = None

    return resultat


if __name__ == "__main__":
    import sys
    data_test = sys.argv[1] if len(sys.argv) > 1 else None
    print("Generant posts per a: {}...".format(data_test or "avui"))
    posts = genera_posts_dia(data_test)
    print(json.dumps(posts, ensure_ascii=False, indent=2))