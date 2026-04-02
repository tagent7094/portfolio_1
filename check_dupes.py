"""Quick script to check duplicate nodes in the knowledge graph."""
from src.graph.store import load_graph
from collections import Counter

g = load_graph('data/founders/sharath/knowledge-graph/graph.json')

for node_type in ['thinking_model', 'story', 'style_rule', 'belief']:
    nodes = [(nid, d) for nid, d in g.nodes(data=True) if d.get('node_type') == node_type]

    # Check by description/stance/summary
    field = {'thinking_model': 'description', 'story': 'summary', 'style_rule': 'description', 'belief': 'stance'}[node_type]
    descs = Counter()
    for nid, d in nodes:
        val = (d.get(field) or '')[:100]
        if val:
            descs[val] += 1

    dupes = [(desc, count) for desc, count in descs.most_common() if count > 1]
    unique = len(descs)
    print(f"\n{node_type}: {len(nodes)} total, {unique} unique, {len(dupes)} duplicated")
    for desc, count in dupes[:5]:
        print(f"  [{count}x] {desc[:70]}...")
