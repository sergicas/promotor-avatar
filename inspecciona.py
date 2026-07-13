"""Inspecciona el text real dels posts programats a Buffer per als dies 15 i 16 de juliol."""
import sys
from pathlib import Path
sys.path.insert(0, "/Users/sergicastillo/Documents/Promotor Avatar Sergi")
from publicador import _buffer_graphql, _org_id

DIES = {"2026-07-15", "2026-07-16"}

org = _org_id()
r = _buffer_graphql(
    "query($i: PostsInput!){ posts(input:$i, first:100){ edges{ node{ "
    "id text dueAt channelService assets{... on ImageAsset{ source }} } } } }",
    {"i": {"organizationId": org, "filter": {"status": ["scheduled"]}}},
)
edges = (((r.get("data") or {}).get("posts") or {}).get("edges")) or []
for e in edges:
    n = e["node"]
    dia = (n.get("dueAt") or "")[:10]
    if dia not in DIES:
        continue
    print(f"═══ {dia} · {n.get('channelService')} ═══")
    print(n.get("text"))
    print()
