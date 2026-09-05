"""Retira de Buffer els posts d'un dia creats pel Promotor Avatar.

La seleccio es fa amb els textos exactes desats a l'historial del generador.
Si la cua no conte exactament un post coincident per canal, no s'esborra res.
"""

import argparse
import datetime
import json
from pathlib import Path

from promotor import PLATAFORMES
from publicador import _buffer_graphql, _org_id, esborra_post, get_canals


HISTORIAL = Path(__file__).parent / "dades" / "historial_posts.json"


def _posts_programats(canals):
    resposta = _buffer_graphql(
        """
        query($input: PostsInput!) {
          posts(input: $input, first: 100) {
            edges { node { id dueAt text channelId status } }
          }
        }
        """,
        {
            "input": {
                "organizationId": _org_id(),
                "filter": {
                    "status": ["scheduled"],
                    "channelIds": list(canals.values()),
                },
            }
        },
    )
    if resposta.get("errors"):
        raise RuntimeError("Buffer: {}".format(resposta["errors"]))
    return [
        edge.get("node") or {}
        for edge in (((resposta.get("data") or {}).get("posts") or {}).get("edges") or [])
    ]


def retira(dia, executar=False):
    datetime.date.fromisoformat(dia)
    historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
    entrada = historial.get(dia) or {}
    esperats = {
        canal: ((entrada.get("posts") or {}).get(canal) or {}).get("text", "")
        for canal in PLATAFORMES
    }
    if any(not text for text in esperats.values()):
        raise RuntimeError("L'historial no conte els tres textos del {}.".format(dia))

    canals = get_canals(forcar_refresc=True)
    if "error" in canals:
        raise RuntimeError(canals["error"])
    invers = {identificador: canal for canal, identificador in canals.items()}

    coincidencies = {}
    for post in _posts_programats(canals):
        if not (post.get("dueAt") or "").startswith(dia):
            continue
        canal = invers.get(post.get("channelId"))
        if canal in esperats and (post.get("text") or "") == esperats[canal]:
            if canal in coincidencies:
                raise RuntimeError("Hi ha mes d'un post coincident a {}.".format(canal))
            coincidencies[canal] = post

    if set(coincidencies) != set(PLATAFORMES):
        raise RuntimeError(
            "Operacio aturada: coincidencies exactes trobades {} de {}.".format(
                sorted(coincidencies), sorted(PLATAFORMES)
            )
        )

    for canal in PLATAFORMES:
        print("{}: post verificat per a {}".format(canal, coincidencies[canal]["dueAt"]))
    if not executar:
        print("Verificacio completada; no s'ha esborrat res.")
        return

    errors = []
    for canal in PLATAFORMES:
        resultat = esborra_post(coincidencies[canal]["id"])
        if resultat.get("ok"):
            print("{}: post retirat".format(canal))
        else:
            errors.append("{}: {}".format(canal, resultat.get("error", "error desconegut")))
    if errors:
        raise RuntimeError("; ".join(errors))

    restants = _posts_programats(canals)
    ids_retirats = {post["id"] for post in coincidencies.values()}
    encara_presents = [post["id"] for post in restants if post.get("id") in ids_retirats]
    if encara_presents:
        raise RuntimeError("Buffer encara retorna algun post retirat: {}".format(encara_presents))
    print("Verificacio final correcta: els tres posts ja no son a la cua.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dia", help="Data dels posts, en format YYYY-MM-DD")
    parser.add_argument("--executar", action="store_true")
    args = parser.parse_args()
    retira(args.dia, executar=args.executar)
