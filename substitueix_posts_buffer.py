"""Substitueix de manera segura una campanya programada a Buffer.

Prepara primer els textos i les imatges nous, crea els tres substituts i només
després elimina els originals. Està pensat per a una execució manual i exigeix
una paraula que hagi d'aparèixer als tres posts antics, per no tocar mai una
data equivocada.
"""

import argparse
import datetime

from generador import genera_posts_dia
from mati import _desa_historial
from promotor import PLATAFORMES
from publicador import (
    _buffer_graphql,
    _imatge_publica,
    _org_id,
    esborra_post,
    get_canals,
)


def _programats_del_dia(data_str, canals):
    resposta = _buffer_graphql(
        """
        query($input: PostsInput!) {
          posts(input: $input, first: 100) {
            edges { node { id dueAt text channelId status } }
          }
        }
        """,
        {"input": {
            "organizationId": _org_id(),
            "filter": {
                "status": ["scheduled"],
                "channelIds": list(canals.values()),
            },
        }},
    )
    if resposta.get("errors"):
        raise RuntimeError("Buffer: {}".format(resposta["errors"]))
    return [
        edge.get("node") or {}
        for edge in (((resposta.get("data") or {}).get("posts") or {})
                     .get("edges") or [])
        if ((edge.get("node") or {}).get("dueAt") or "")[:10] == data_str
    ]


def _crea_post(canal, channel_id, text, due_at, imatge_url):
    entrada = {
        "channelId": channel_id,
        "text": text[:280] if canal == "twitter" else text,
        "schedulingType": "automatic",
        "saveToDraft": False,
        "mode": "customScheduled",
        "dueAt": due_at,
        "assets": [{"image": {"url": imatge_url}}],
    }
    if canal == "instagram":
        entrada["metadata"] = {
            "instagram": {"type": "post", "shouldShareToFeed": True}
        }
    resposta = _buffer_graphql(
        """
        mutation($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess { post { id status dueAt } }
            ... on MutationError { message }
          }
        }
        """,
        {"input": entrada},
    )
    if resposta.get("errors"):
        raise RuntimeError("{}: {}".format(canal, resposta["errors"]))
    resultat = (resposta.get("data") or {}).get("createPost") or {}
    if resultat.get("__typename") != "PostActionSuccess":
        raise RuntimeError("{}: {}".format(canal, resultat))
    return (resultat.get("post") or {}).get("id")


def substitueix(data_str, text_antic):
    datetime.date.fromisoformat(data_str)
    agulla = text_antic.strip().lower()
    if len(agulla) < 4:
        raise ValueError("La comprovació del text antic és massa curta.")

    canals = get_canals(forcar_refresc=True)
    if "error" in canals:
        raise RuntimeError(canals["error"])
    invers = {identificador: nom for nom, identificador in canals.items()}
    programats = _programats_del_dia(data_str, canals)
    antics = [
        post for post in programats
        if agulla in (post.get("text") or "").lower()
    ]
    if len(antics) != len(PLATAFORMES):
        raise RuntimeError(
            "Operació aturada: s'esperaven {} posts amb {!r} i se n'han "
            "trobat {}.".format(len(PLATAFORMES), text_antic, len(antics))
        )
    antics_per_canal = {invers.get(p.get("channelId")): p for p in antics}
    if set(antics_per_canal) != set(PLATAFORMES):
        raise RuntimeError("Els posts antics no cobreixen exactament els tres canals.")

    posts = genera_posts_dia(data_str)
    if posts.get("error"):
        raise RuntimeError(posts["error"])
    if posts.get("campanya") == agulla:
        raise RuntimeError("El generador ha tornat a triar la campanya antiga.")
    print("Campanya substituta: {} · {}".format(
        posts.get("campanya"), posts.get("tema", "")))

    # Preparar i publicar les imatges abans de tocar cap post existent.
    urls = {}
    for canal in PLATAFORMES:
        bloc = posts.get(canal) or {}
        if not bloc.get("text"):
            raise RuntimeError("El substitut de {} no té text.".format(canal))
        url, error = _imatge_publica(
            bloc.get("imatge"), bloc["text"], data_str, canal,
        )
        if error:
            raise RuntimeError(error)
        urls[canal] = url
        print("✓ {}: substitut i imatge preparats".format(canal))

    # Crear primer tots els nous. Si una creació falla, els antics segueixen
    # intactes i es pot retirar manualment qualsevol substitut parcial.
    nous = {}
    for canal in PLATAFORMES:
        antic = antics_per_canal[canal]
        nous[canal] = _crea_post(
            canal, antic["channelId"], posts[canal]["text"], antic["dueAt"],
            urls[canal],
        )
        print("✓ {}: post substitut creat".format(canal))

    # Retirar els originals només quan els tres substituts ja existeixen.
    for canal in PLATAFORMES:
        resultat = esborra_post(antics_per_canal[canal]["id"])
        if not resultat.get("ok"):
            raise RuntimeError(
                "No s'ha pogut retirar l'original de {}: {}".format(
                    canal, resultat.get("error", "error desconegut"))
            )
        print("✓ {}: post antic retirat".format(canal))

    finals = _programats_del_dia(data_str, canals)
    encara_antics = [
        post for post in finals
        if agulla in (post.get("text") or "").lower()
    ]
    ids_finals = {post.get("id") for post in finals}
    if encara_antics or not set(nous.values()) <= ids_finals:
        raise RuntimeError("La verificació final de Buffer no ha quadrat.")

    items = [{
        "canal": canal,
        "text": posts[canal]["text"],
        "imatge_url": urls[canal],
        "ok": True,
        "skip": False,
        "msg": "Campanya substituïda a Buffer.",
    } for canal in PLATAFORMES]
    _desa_historial(data_str, posts, items)
    print("✓ Substitució completa i memòria antirepetició actualitzada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data", help="Data programada, YYYY-MM-DD")
    parser.add_argument(
        "--si-conte", required=True,
        help="Text que han de contenir exactament els tres posts antics",
    )
    arguments = parser.parse_args()
    substitueix(arguments.data, arguments.si_conte)
