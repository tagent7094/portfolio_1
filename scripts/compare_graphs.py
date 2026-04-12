import json, sys
from collections import Counter

for name, path in [('Sharath', 'data/founders/sharath/knowledge-graph/graph.json'), ('Deepinder', 'data/founders/deepinder/knowledge-graph/graph.json')]:
    with open(path) as f:
        g = json.load(f)
    edges = g.get('edges', g.get('links', []))
    print(f'=== {name} ===')
    print(f'Nodes: {len(g.get("nodes",[]))}')
    print(f'Edges: {len(edges)}')
    c = Counter(e.get('edge_type','NO_TYPE') for e in edges)
    for t, cnt in c.most_common():
        print(f'  {t}: {cnt}')
    for e in edges[:3]:
        print(f'  Ex: {json.dumps(e)[:200]}')
    # Check if edges use 'type' or 'edge_type'
    if edges:
        print(f'  Edge keys: {list(edges[0].keys())}')
    print()
