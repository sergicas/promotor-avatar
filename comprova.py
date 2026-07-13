import sys
sys.path.insert(0, "/Users/sergicastillo/Documents/Promotor Avatar Sergi")
from publicador import _buffer_graphql

# Sense _org_id (que està cachejat i pot ser buit al procés nou)
acc = _buffer_graphql("{ account { currentOrganization { id } organizations { id } } }")
print("ACCOUNT:", acc)

a = (acc.get("data") or {}).get("account") or {}
org = (a.get("currentOrganization") or {}).get("id") or (a.get("organizations",[{}])[0].get("id"))
print("ORG:", org)

for status in [["scheduled"], ["sent"], ["draft"], ["scheduled","sent","draft"]]:
    r = _buffer_graphql(
        "query($i: PostsInput!){ posts(input:$i, first:200){ edges{ node{ id text dueAt channelService status } } } }",
        {"i": {"organizationId": org, "filter": {"status": status}}},
    )
    if "errors" in r:
        print(f"STATUS {status}: ERRORS", r["errors"])
        continue
    edges = (((r.get("data") or {}).get("posts") or {}).get("edges")) or []
    dies = [(e["node"].get("dueAt") or "")[:10] + " " + str(e["node"].get("channelService")) for e in edges if (e["node"].get("dueAt") or "").startswith("2026-07-1")]
    print(f"STATUS {status}: total {len(edges)}; matches jul 15-19: {dies}")
