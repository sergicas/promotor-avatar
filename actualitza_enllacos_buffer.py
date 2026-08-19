"""Actualitza web/Amazon als posts ja programats d'un dia, sense recrear-los."""

import datetime
import sys

from generador import finalitza_enllacos_posts
from publicador import _buffer_graphql, _org_id, edita_text_post, get_canals


def actualitza(data_str):
    try:
        datetime.date.fromisoformat(data_str)
    except ValueError:
        print("Data invàlida: {}. Usa YYYY-MM-DD.".format(data_str))
        return 1

    canals = get_canals(forcar_refresc=True)
    if "error" in canals:
        print("✗ {}".format(canals["error"]))
        return 1
    org_id = _org_id()
    resposta = _buffer_graphql(
        """
        query($input: PostsInput!) {
          posts(input: $input, first: 100) {
            edges { node { id dueAt text channelId status } }
          }
        }
        """,
        {"input": {
            "organizationId": org_id,
            "filter": {"status": ["scheduled"], "channelIds": list(canals.values())},
        }},
    )
    if resposta.get("errors"):
        print("✗ Buffer: {}".format(resposta["errors"]))
        return 1

    invers = {identificador: nom for nom, identificador in canals.items()}
    trobats = 0
    actualitzats = 0
    errors = 0
    arestes = ((resposta.get("data") or {}).get("posts") or {}).get("edges", [])
    for aresta in arestes:
        post = aresta.get("node") or {}
        if (post.get("dueAt") or "")[:10] != data_str:
            continue
        plataforma = invers.get(post.get("channelId"))
        if not plataforma:
            continue
        trobats += 1
        bloc = {plataforma: {"text": post.get("text", "")}}
        finalitza_enllacos_posts(bloc)
        text_nou = bloc[plataforma]["text"]
        if text_nou == post.get("text", ""):
            print("✓ {}: ja tenia tots els enllaços".format(plataforma))
            continue
        resultat = edita_text_post(post.get("id"), text_nou)
        if resultat.get("ok"):
            actualitzats += 1
            print("✓ {}: text actualitzat; data i imatge preservades".format(plataforma))
        else:
            errors += 1
            print("✗ {}: {}".format(plataforma, resultat.get("error", "error desconegut")))

    print("Posts trobats: {} · actualitzats: {} · errors: {}".format(
        trobats, actualitzats, errors))
    if trobats == 0:
        print("✗ No hi ha posts programats per al {}.".format(data_str))
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        raise SystemExit("Cal indicar la data: YYYY-MM-DD")
    raise SystemExit(actualitza(sys.argv[1].strip()))
