"""Generate Post — Create posts with agent reasoning visibility."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.ui.state import get_graph, get_graph_path
from src.ui.components.post_preview import (
    render_agent_reasoning,
    render_post_preview,
    render_post_variants,
    render_quality_gate,
)

st.set_page_config(page_title="Digital DNA - Generate Post", layout="wide")
st.title("Generate Post")

graph = get_graph()
if graph.number_of_nodes() == 0:
    st.warning("Graph is empty. Run `digital-dna ingest` first.")
    st.stop()

mode = st.radio("Mode", ["Viral Topic", "Podcast Narrative"], horizontal=True)

if mode == "Viral Topic":
    topic = st.text_input("Topic", placeholder="Why AI agents won't replace contact centers")
    platform = st.selectbox("Platform", ["linkedin", "twitter", "email"])

    if st.button("Generate Post", type="primary"):
        if not topic:
            st.error("Enter a topic.")
            st.stop()

        with st.status("Generating with LangGraph workflow...", expanded=True):
            try:
                from src.langchain_agents.graph_workflow import run_topic_generation

                st.write("Matching topic to knowledge graph...")
                result = run_topic_generation(topic, platform, get_graph_path())

                st.write("Generation complete!")
            except Exception as e:
                st.error(f"LangGraph error: {e}. Falling back to classic pipeline...")
                # Fallback to original agent system
                from src.llm.factory import create_llm
                from src.generation.topic_matcher import match_topic_to_graph
                from src.generation.agents import AgentSwarm
                from src.humanization.humanizer import humanize_post
                from src.humanization.quality_gate import quality_gate

                llm = create_llm()
                match = match_topic_to_graph(topic, graph, None, llm)
                narrative = {
                    "id": "topic_match",
                    "narrative": match.get("suggested_angle", topic),
                    "angle": f"Based on founder's beliefs about {topic}",
                    "hook": match.get("suggested_angle", topic)[:100],
                }
                swarm = AgentSwarm(llm, graph)
                winner_post, post_scores = swarm.generate_and_vote_posts(narrative, platform, topic)
                humanized = humanize_post(winner_post.get("text", ""), graph, llm, platform)
                qg = quality_gate(humanized, graph)

                result = {
                    "humanized_post": humanized,
                    "quality_result": qg,
                    "post_variants": [],
                    "post_scores": post_scores,
                    "agent_log": [],
                }

        # Display results
        if result:
            render_agent_reasoning(result.get("agent_log", []))
            render_post_variants(result.get("post_variants", []), result.get("post_scores", {}))
            render_post_preview(
                result.get("humanized_post", ""),
                result.get("quality_result"),
            )

elif mode == "Podcast Narrative":
    transcript = st.text_area("Paste podcast transcript", height=200)
    platform = st.selectbox("Platform", ["linkedin", "twitter", "email"], key="podcast_platform")

    if st.button("Generate from Podcast", type="primary"):
        if not transcript:
            st.error("Paste a transcript.")
            st.stop()

        with st.status("Generating...", expanded=True):
            try:
                from src.llm.factory import create_llm
                from src.generation.agents import AgentSwarm
                from src.humanization.humanizer import humanize_post
                from src.humanization.quality_gate import quality_gate

                llm = create_llm()
                swarm = AgentSwarm(llm, graph)

                st.write("Extracting & voting on narratives...")
                winner_narrative, narr_scores = swarm.extract_and_vote_narrative(transcript)

                st.write("Generating & voting on posts...")
                winner_post, post_scores = swarm.generate_and_vote_posts(winner_narrative, platform)

                st.write("Humanizing...")
                humanized = humanize_post(winner_post.get("text", ""), graph, llm, platform)

                st.write("Quality gate...")
                qg = quality_gate(humanized, graph)

                result = {
                    "humanized_post": humanized,
                    "quality_result": qg,
                    "post_variants": [],
                    "post_scores": post_scores,
                    "agent_log": [],
                }
            except Exception as e:
                st.error(f"Error: {e}")
                result = None

        if result:
            render_post_preview(
                result.get("humanized_post", ""),
                result.get("quality_result"),
            )
