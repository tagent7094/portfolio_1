"""Graph Explorer — View and edit the personality knowledge graph."""

import json
import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.ui.state import get_graph, save_graph_state, COLOR_MAP
from src.ui.components.graph_viewer import render_pyvis_graph
from src.ui.components.node_editor import render_node_editor

st.set_page_config(page_title="Digital DNA - Graph Explorer", layout="wide")
st.title("Knowledge Graph Explorer")

# Load graph
graph = get_graph()

if graph.number_of_nodes() == 0:
    st.warning("Graph is empty. Run `digital-dna ingest` first to build the knowledge graph.")
    st.stop()

# Sidebar: Filters
st.sidebar.header("Filter")
available_types = sorted(set(d.get("node_type", "unknown") for _, d in graph.nodes(data=True)))
node_types = st.sidebar.multiselect(
    "Show node types",
    available_types,
    default=available_types[:4],
)

# Sidebar: Node selector and editor
st.sidebar.divider()
st.sidebar.header("Node Editor")

all_node_ids = [
    nid for nid, d in graph.nodes(data=True) if d.get("node_type", "unknown") in node_types
]

if all_node_ids:
    selected_id = st.sidebar.selectbox(
        "Select node to edit",
        options=all_node_ids,
        format_func=lambda x: f"[{graph.nodes[x].get('node_type', '?')}] {(graph.nodes[x].get('title') or graph.nodes[x].get('stance') or graph.nodes[x].get('name') or graph.nodes[x].get('description') or x)[:40]}",
    )

    with st.sidebar:
        render_node_editor(graph, selected_id, save_graph_state)

# Main area: Graph visualization
col1, col2 = st.columns([4, 1])

with col1:
    render_pyvis_graph(graph, node_types, height="600px")

with col2:
    st.markdown("### Legend")
    for node_type in node_types:
        color = COLOR_MAP.get(node_type, "#888")
        count = sum(1 for _, d in graph.nodes(data=True) if d.get("node_type") == node_type)
        st.markdown(
            f'<span style="color:{color}; font-size:20px;">\u25cf</span> {node_type.replace("_", " ").title()} ({count})',
            unsafe_allow_html=True,
        )

# Bottom: Stats
st.divider()
type_counts = {}
for _, data in graph.nodes(data=True):
    t = data.get("node_type", "unknown")
    type_counts[t] = type_counts.get(t, 0) + 1

cols = st.columns(len(type_counts) + 1)
for i, (nt, count) in enumerate(sorted(type_counts.items())):
    with cols[i]:
        st.metric(nt.replace("_", " ").title(), count)
with cols[-1]:
    st.metric("Edges", graph.number_of_edges())

# Actions
st.divider()
col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    if st.button("+ Add Belief"):
        import uuid

        new_id = f"belief_{uuid.uuid4().hex[:6]}"
        graph.add_node(new_id, node_type="belief", topic="", stance="New belief - edit me", confidence=0.5)
        save_graph_state(graph)
        st.rerun()

with col_b:
    if st.button("+ Add Story"):
        import uuid

        new_id = f"story_{uuid.uuid4().hex[:6]}"
        graph.add_node(new_id, node_type="story", title="New story", summary="Edit me",
                       emotional_register="quiet_authority")
        save_graph_state(graph)
        st.rerun()

with col_c:
    if st.button("+ Add Style Rule"):
        import uuid

        new_id = f"style_{uuid.uuid4().hex[:6]}"
        graph.add_node(new_id, node_type="style_rule", rule_type="rhythm",
                       description="New style rule - edit me")
        save_graph_state(graph)
        st.rerun()

with col_d:
    if st.button("Export Graph JSON"):
        import networkx as nx

        graph_json = json.dumps(nx.node_link_data(graph), indent=2, default=str)
        st.download_button("Download JSON", graph_json, "knowledge-graph.json", "application/json")
