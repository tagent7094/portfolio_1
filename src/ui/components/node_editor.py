"""Node editor sidebar component for Streamlit."""

from __future__ import annotations

import streamlit as st


def render_node_editor(graph, selected_id: str, save_callback):
    """Render the node editor form in the sidebar."""
    if not selected_id or selected_id not in graph.nodes:
        st.info("Select a node to edit.")
        return

    node_data = dict(graph.nodes[selected_id])
    node_type = node_data.get("node_type", "unknown")

    st.subheader(f"Edit: {selected_id[:30]}")
    st.caption(f"Type: `{node_type}`")

    if node_type == "belief":
        new_topic = st.text_input("Topic", value=node_data.get("topic", ""), key="edit_topic")
        new_stance = st.text_area("Stance", value=node_data.get("stance", ""), height=100, key="edit_stance")
        new_confidence = st.slider("Confidence", 0.0, 1.0, value=float(node_data.get("confidence", 0.5)), step=0.05, key="edit_conf")
        new_opposes = st.text_input("Opposes", value=node_data.get("opposes", "") or "", key="edit_opp")

        if st.button("Save Changes", type="primary", key="save_belief"):
            graph.nodes[selected_id]["topic"] = new_topic
            graph.nodes[selected_id]["stance"] = new_stance
            graph.nodes[selected_id]["confidence"] = new_confidence
            graph.nodes[selected_id]["opposes"] = new_opposes
            save_callback(graph)
            st.success("Saved!")
            st.rerun()

    elif node_type == "story":
        new_title = st.text_input("Title", value=node_data.get("title", ""), key="edit_title")
        new_summary = st.text_area("Summary", value=node_data.get("summary", ""), height=100, key="edit_summary")
        registers = ["controlled_anger", "quiet_authority", "earned_vulnerability", "generosity", "paranoid_optimist"]
        current_reg = node_data.get("emotional_register", "quiet_authority")
        idx = registers.index(current_reg) if current_reg in registers else 1
        new_register = st.selectbox("Emotional Register", registers, index=idx, key="edit_reg")
        new_contrast = st.text_input("Contrast Pair", value=node_data.get("contrast_pair", "") or "", key="edit_contrast")

        if st.button("Save Changes", type="primary", key="save_story"):
            graph.nodes[selected_id]["title"] = new_title
            graph.nodes[selected_id]["summary"] = new_summary
            graph.nodes[selected_id]["emotional_register"] = new_register
            graph.nodes[selected_id]["contrast_pair"] = new_contrast
            save_callback(graph)
            st.success("Saved!")
            st.rerun()

    elif node_type == "style_rule":
        new_desc = st.text_area("Description", value=node_data.get("description", ""), height=80, key="edit_desc")
        rule_types = ["opening", "closing", "rhythm", "rhetorical_move", "vocabulary", "punctuation"]
        current_rt = node_data.get("rule_type", "rhythm")
        idx = rule_types.index(current_rt) if current_rt in rule_types else 2
        new_rule_type = st.selectbox("Rule Type", rule_types, index=idx, key="edit_rt")
        new_anti = st.text_area("Anti-pattern", value=node_data.get("anti_pattern", "") or "", height=60, key="edit_anti")

        if st.button("Save Changes", type="primary", key="save_style"):
            graph.nodes[selected_id]["description"] = new_desc
            graph.nodes[selected_id]["rule_type"] = new_rule_type
            graph.nodes[selected_id]["anti_pattern"] = new_anti
            save_callback(graph)
            st.success("Saved!")
            st.rerun()

    elif node_type == "thinking_model":
        new_name = st.text_input("Name", value=node_data.get("name", ""), key="edit_name")
        new_desc = st.text_area("Description", value=node_data.get("description", ""), height=80, key="edit_mdesc")
        new_priority = st.slider("Priority", 0, 10, value=int(node_data.get("priority", 0)), key="edit_prio")

        if st.button("Save Changes", type="primary", key="save_model"):
            graph.nodes[selected_id]["name"] = new_name
            graph.nodes[selected_id]["description"] = new_desc
            graph.nodes[selected_id]["priority"] = new_priority
            save_callback(graph)
            st.success("Saved!")
            st.rerun()

    else:
        st.json(node_data)

    # Connections
    st.divider()
    st.caption("**Connections**")
    out_edges = list(graph.out_edges(selected_id, data=True))
    in_edges = list(graph.in_edges(selected_id, data=True))

    for _, target, edata in out_edges:
        tgt = graph.nodes.get(target, {})
        st.caption(f"-> [{edata.get('edge_type', '?')}] {target[:25]} ({tgt.get('node_type', '?')})")
    for source, _, edata in in_edges:
        src = graph.nodes.get(source, {})
        st.caption(f"<- [{edata.get('edge_type', '?')}] {source[:25]} ({src.get('node_type', '?')})")

    if not out_edges and not in_edges:
        st.caption("No connections.")

    # Delete
    st.divider()
    if st.button("Delete this node", key="delete_node"):
        graph.remove_node(selected_id)
        save_callback(graph)
        st.warning(f"Deleted {selected_id}")
        st.rerun()
