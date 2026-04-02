"""Podcast Flow — Full pipeline from transcript to post."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.ui.state import get_graph, PROJECT_ROOT

st.set_page_config(page_title="Digital DNA - Podcast Flow", layout="wide")
st.title("Podcast to Post Flow")

graph = get_graph()
if graph.number_of_nodes() == 0:
    st.warning("Graph is empty. Run `digital-dna ingest` first.")
    st.stop()

# File selector
podcast_dir = PROJECT_ROOT / "data" / "podcasts"
podcast_files = sorted(f for f in podcast_dir.iterdir() if f.suffix == ".txt" and not f.name.startswith(".")) if podcast_dir.exists() else []

tab1, tab2 = st.tabs(["Upload / Paste", "Select from Files"])

with tab1:
    transcript = st.text_area("Paste transcript here", height=300, key="paste_transcript")

with tab2:
    if podcast_files:
        selected_file = st.selectbox("Select transcript", podcast_files, format_func=lambda f: f.name)
        if st.button("Load file"):
            transcript = selected_file.read_text(encoding="utf-8", errors="replace")
            st.session_state["paste_transcript"] = transcript
            st.rerun()
    else:
        st.info("No .txt files found in data/podcasts/. Drop files there or paste above.")
        transcript = ""

platform = st.selectbox("Target Platform", ["linkedin", "twitter", "email"])

if st.button("Run Full Pipeline", type="primary"):
    transcript_text = st.session_state.get("paste_transcript", "")
    if not transcript_text:
        st.error("Provide a transcript first.")
        st.stop()

    with st.status("Running podcast pipeline...", expanded=True):
        from src.llm.factory import create_llm
        from src.generation.agents import AgentSwarm
        from src.humanization.humanizer import humanize_post
        from src.humanization.quality_gate import quality_gate

        llm = create_llm()
        swarm = AgentSwarm(llm, graph)

        st.write("Step 1: Extracting narratives from transcript...")
        winner_narrative, narr_scores = swarm.extract_and_vote_narrative(transcript_text)

        if not winner_narrative:
            st.error("No narratives extracted.")
            st.stop()

        st.write(f"Winning narrative: {winner_narrative.get('hook', 'N/A')[:80]}")

        st.write("Step 2: Generating post variants...")
        winner_post, post_scores = swarm.generate_and_vote_posts(winner_narrative, platform)

        st.write("Step 3: Humanizing...")
        humanized = humanize_post(winner_post.get("text", ""), graph, llm, platform)

        st.write("Step 4: Quality gate...")
        qg = quality_gate(humanized, graph)

    # Results
    st.divider()

    # Narrative scores
    with st.expander("Narrative Voting Results"):
        if narr_scores:
            for nid, scores in narr_scores.items():
                st.write(f"**{nid}**: total={scores.get('total', 0):.1f}")

    # Post scores
    with st.expander("Post Voting Results"):
        if post_scores:
            for pid, scores in post_scores.items():
                st.write(f"**{pid}**: total={scores.get('total', 0):.1f}")

    # Quality gate
    from src.ui.components.post_preview import render_quality_gate, render_post_preview
    render_post_preview(humanized, qg)
