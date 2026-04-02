"""Pyvis graph rendering component for Streamlit."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit.components.v1 as components
from pyvis.network import Network

from ..state import COLOR_MAP


def render_pyvis_graph(graph, node_types_filter: list[str], height: str = "600px"):
    """Render an interactive Pyvis graph inside Streamlit."""
    net = Network(
        height=height,
        width="100%",
        bgcolor="#0f1117",
        font_color="#e4e6f0",
        select_menu=False,
        filter_menu=False,
    )

    net.set_options("""
    {
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -50,
                "centralGravity": 0.01,
                "springLength": 100,
                "springConstant": 0.08
            },
            "solver": "forceAtlas2Based",
            "stabilization": {"iterations": 150}
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 200
        },
        "nodes": {
            "font": {"size": 12, "face": "Inter, sans-serif"},
            "borderWidth": 1
        },
        "edges": {
            "color": {"inherit": "both"},
            "smooth": {"type": "curvedCW", "roundness": 0.2},
            "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}
        }
    }
    """)

    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "unknown")
        if node_type not in node_types_filter:
            continue

        color = COLOR_MAP.get(node_type, "#888888")

        if node_type == "belief":
            title = f"BELIEF: {data.get('stance', '')}\nConfidence: {data.get('confidence', '?')}\nTopic: {data.get('topic', '?')}"
            label = (data.get("stance", node_id) or node_id)[:40]
            size = 20 + (float(data.get("confidence", 0.5)) * 20)
        elif node_type == "story":
            title = f"STORY: {data.get('title', '')}\nRegister: {data.get('emotional_register', '?')}"
            label = (data.get("title", node_id) or node_id)[:30]
            size = 20
        elif node_type == "style_rule":
            title = f"STYLE: {data.get('description', '')}\nType: {data.get('rule_type', '?')}"
            label = data.get("rule_type", node_id) or node_id
            size = 18
        elif node_type == "thinking_model":
            title = f"MODEL: {data.get('name', '')}\n{data.get('description', '')}"
            label = (data.get("name", node_id) or node_id)[:25]
            size = 18
        else:
            title = str(node_type)
            label = node_id[:20]
            size = 15

        net.add_node(
            node_id,
            label=label,
            title=title,
            color=color,
            size=size,
            shape="dot",
        )

    for source, target, data in graph.edges(data=True):
        src_type = graph.nodes[source].get("node_type", "")
        tgt_type = graph.nodes[target].get("node_type", "")
        if src_type in node_types_filter and tgt_type in node_types_filter:
            edge_type = data.get("edge_type", "")
            net.add_edge(source, target, title=edge_type)

    # Save to temp file and display
    tmp = Path(tempfile.gettempdir()) / "digital_dna_graph.html"
    net.save_graph(str(tmp))
    html_content = tmp.read_text(encoding="utf-8")
    components.html(html_content, height=int(height.replace("px", "")) + 20, scrolling=False)
