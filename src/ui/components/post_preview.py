"""Post preview component with quality score display."""

from __future__ import annotations

import streamlit as st


def render_quality_gate(quality_result: dict):
    """Render quality gate results as a checklist."""
    score = quality_result.get("score", 0)
    passed = quality_result.get("passed", False)
    checks = quality_result.get("checks", {})

    color = "green" if passed else "red"
    st.markdown(f"### Quality Gate: :{color}[{score}%]")

    cols = st.columns(3)
    check_labels = {
        "bold_opening": "Bold opening",
        "no_generic_opening": "No generic opener",
        "no_banned_phrases": "No banned phrases",
        "no_em_dashes": "No em-dashes",
        "no_hashtags": "No hashtags",
        "has_specifics": "Has specifics",
        "has_contrast": "Has contrast",
        "no_question_ending": "No question ending",
        "no_cta_ending": "No CTA ending",
        "good_length": "Good length",
    }

    items = list(checks.items())
    for i, (check_key, check_val) in enumerate(items):
        label = check_labels.get(check_key, check_key)
        icon = "\u2705" if check_val else "\u274c"
        with cols[i % 3]:
            st.write(f"{icon} {label}")


def render_post_preview(post_text: str, quality_result: dict | None = None, editable: bool = True):
    """Render a post preview with optional quality gate."""
    if quality_result:
        render_quality_gate(quality_result)

    st.subheader("Final Post")
    if editable:
        edited = st.text_area("Edit before publishing:", value=post_text, height=300, key="post_edit")
    else:
        edited = post_text
        st.markdown(f"```\n{post_text}\n```")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Copy to Clipboard", key="copy_btn"):
            st.code(edited)
            st.info("Copy the text from the code block above.")
    with col2:
        if st.button("Save to /output", key="save_btn"):
            from datetime import datetime
            from pathlib import Path

            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = output_dir / f"post_ui_{ts}.txt"
            path.write_text(edited, encoding="utf-8")
            st.success(f"Saved to {path.name}")
    with col3:
        if st.button("Regenerate", key="regen_btn"):
            st.rerun()

    return edited


def render_agent_reasoning(agent_log: list[dict]):
    """Render agent reasoning as expandable panels."""
    if not agent_log:
        return

    with st.expander("Agent Reasoning Log", expanded=False):
        for entry in agent_log:
            step = entry.get("step", "?")
            if step == "topic_match":
                st.write(f"**Topic Match** -> Angle: {entry.get('angle', 'N/A')[:100]}")
            elif step == "generate_post":
                st.write(f"**Generated** ({entry.get('strategy', '?')}) -> {entry.get('length', 0)} chars")
            elif step == "vote_post":
                scores = entry.get("scores", {})
                st.write(f"**{entry.get('agent', '?')}** scored `{entry.get('post', '?')[:20]}`: {scores}")
            elif step == "humanize":
                st.write(f"**Humanize** attempt {entry.get('attempt', '?')}: {entry.get('input_length', 0)} -> {entry.get('output_length', 0)} chars")
            elif step == "quality_gate":
                st.write(f"**Quality Gate**: {entry.get('score', 0)}% ({'PASS' if entry.get('passed') else 'FAIL'})")


def render_post_variants(post_variants: list[dict], post_scores: dict):
    """Render post variants with their vote scores."""
    if not post_variants:
        return

    with st.expander("Post Variants & Scores", expanded=False):
        for post in post_variants:
            pid = post["id"]
            scores = post_scores.get(pid, {})
            total = scores.get("total", 0)
            is_winner = total == max(s.get("total", 0) for s in post_scores.values()) if post_scores else False

            prefix = "\U0001f3c6 WINNER: " if is_winner else ""
            st.markdown(f"**{prefix}{post.get('strategy', pid)}** (Score: {total:.1f})")
            st.caption(post["text"][:200] + "..." if len(post["text"]) > 200 else post["text"])
            st.divider()
