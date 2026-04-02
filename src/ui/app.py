"""Digital DNA — Streamlit main app."""

import streamlit as st

st.set_page_config(
    page_title="Digital DNA",
    page_icon="\U0001f9ec",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Digital DNA \U0001f9ec")
st.sidebar.caption("Your personality, your graph, your voice")

st.markdown(
    """
    # Welcome to Digital DNA

    Use the sidebar to navigate between pages:

    - **Graph Explorer** — View and edit your personality knowledge graph
    - **Generate Post** — Create posts from viral topics with agent reasoning
    - **Podcast Flow** — Generate posts from podcast transcripts
    - **Settings** — Configure LLM provider and quality rules
    """
)
