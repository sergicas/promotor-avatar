import sys
sys.path.insert(0, "/Users/sergicastillo/Documents/Promotor Avatar Sergi")
from publicador import _buffer_graphql

acc = _buffer_graphql("{ account { organizations { id } } }")
org = ((acc.get("data") or {}).get("account") or {}).get("organizations", [{}])[0].get("id")
r = _buffer_graphql(
    "query($i: PostsInput!){ posts(input:$i, first:100){ edges{ node{ id text dueAt channelService } } } }",
    {"i": {"organizationId": org, "filter": {"status": ["scheduled"]}}},
)
edges = (((r.get("data") or {}).get("posts") or {}).get("edges")) or []
print(f"Total scheduled: {len(edges)}")
grup = {}
for e in edges:
    n = e["node"]
    d = (n.get("dueAt") or "")[:10]
    if not d.startswith("2026-07-1"):
        continue
    k = (d, n.get("channelService"))
    grup.setdefault(k, []).append(n)
for (d, c), lst in sorted(grup.items()):
    marca = "  DUPLICAT!" if len(lst) > 1 else ""
    for n in lst:
        preview = (n.get("text") or "").replace("\n"," ")[:80]
        marca_amazon = "amazon.it" if "amazon.it" in n.get("text","") else ("amazon.fr" if "amazon.fr" in n.get("text","") else ("amazon.es" if "amazon.es" in n.get("text","") else "-"))
        print(f"  {d} · {c:9} · {marca_amazon:9} · {n['id'][:12]} · {preview}{marca}")
