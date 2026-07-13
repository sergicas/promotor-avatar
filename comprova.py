import sys
sys.path.insert(0, "/Users/sergicastillo/Documents/Promotor Avatar Sergi")
from publicador import _buffer_graphql, _org_id
org = _org_id()
r = _buffer_graphql(
    "query($i: PostsInput!){ posts(input:$i, first:200){ edges{ node{ "
    "id text dueAt channelService } } } }",
    {"i": {"organizationId": org, "filter": {"status": ["scheduled"]}}},
)
edges = (((r.get("data") or {}).get("posts") or {}).get("edges")) or []
print(f"Total scheduled: {len(edges)}")
per_dia = {}
for e in edges:
    n = e["node"]
    d = (n.get("dueAt") or "")[:10]
    c = n.get("channelService")
    per_dia.setdefault((d, c), []).append(n)
for (d, c), lst in sorted(per_dia.items()):
    for n in lst:
        preview = (n.get("text") or "").replace("\n"," ")[:70]
        print(f"  {d} · {c} · {n['id'][:8]} · {preview}")
