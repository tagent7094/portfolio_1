"""Settings — LLM config, quality rules editing."""

import sys
from pathlib import Path

import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.ui.state import get_config, save_config, get_quality_rules, get_personality_card, PROJECT_ROOT

st.set_page_config(page_title="Digital DNA - Settings", layout="wide")
st.title("Settings")

config = get_config()

# LLM Provider
st.subheader("LLM Provider")
providers = ["ollama", "lmstudio", "anthropic", "openai"]
current_provider = config["llm"].get("provider", "ollama")
idx = providers.index(current_provider) if current_provider in providers else 0
provider = st.selectbox("Provider", providers, index=idx)

if provider in ("ollama", "lmstudio"):
    default_url = "http://localhost:11434" if provider == "ollama" else "http://localhost:1234/v1"
    model = st.text_input("Model", value=config["llm"].get("model", ""))
    base_url = st.text_input("Base URL", value=config["llm"].get("base_url", default_url))
else:
    model = st.text_input("Model", value=config["llm"].get("model", ""))
    api_key = st.text_input("API Key", type="password", value=config["llm"].get("api_key", ""))

temperature = st.slider("Temperature", 0.0, 1.0, value=float(config["llm"].get("temperature", 0.7)), step=0.05)
max_tokens = st.number_input("Max Tokens", value=int(config["llm"].get("max_tokens", 2000)), step=100)

if st.button("Save LLM Config", type="primary"):
    config["llm"]["provider"] = provider
    config["llm"]["model"] = model
    config["llm"]["temperature"] = temperature
    config["llm"]["max_tokens"] = max_tokens
    if provider in ("ollama", "lmstudio"):
        config["llm"]["base_url"] = base_url
    else:
        config["llm"]["api_key"] = api_key
    save_config(config)
    st.success("LLM config saved!")

# Quality Rules
st.divider()
st.subheader("Quality Rules")

qr_path = PROJECT_ROOT / "config" / "quality-rules.yaml"
try:
    quality_rules = get_quality_rules()
    checks = quality_rules.get("checks", {})

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Enabled Checks:**")
        for check_name, enabled in checks.items():
            checks[check_name] = st.checkbox(check_name.replace("_", " ").title(), value=enabled, key=f"qr_{check_name}")

    with col2:
        st.write("**Thresholds:**")
        min_score = st.slider("Min Score", 0, 100, value=quality_rules.get("quality_gate", {}).get("min_score", 75))
        max_retries = st.number_input("Max Retries", value=quality_rules.get("quality_gate", {}).get("max_retries", 2))

    if st.button("Save Quality Rules"):
        quality_rules["checks"] = checks
        quality_rules["quality_gate"]["min_score"] = min_score
        quality_rules["quality_gate"]["max_retries"] = max_retries
        with open(qr_path, "w") as f:
            yaml.dump(quality_rules, f, default_flow_style=False)
        st.success("Quality rules saved!")
except Exception as e:
    st.error(f"Could not load quality rules: {e}")

# Personality Card
st.divider()
st.subheader("Personality Card")
card = get_personality_card()
if card:
    with st.expander("View Personality Card", expanded=False):
        st.markdown(card)
else:
    st.info("No personality card yet. Run `digital-dna ingest` to generate one.")

# Graph info
st.divider()
st.subheader("Graph Storage")
st.write(f"**Graph path:** `{config['stores']['graph_path']}`")
st.write(f"**Vectors path:** `{config['stores']['vectors_path']}`")
st.write(f"**Personality card:** `{config['stores']['personality_card_path']}`")
