"""Custom agent node — executes a user-defined prompt against the LLM."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def execute_custom_agent(
    post_text: str,
    prompt: str,
    context: dict,
    llm,
) -> str:
    """Execute a custom agent with the given prompt.

    The prompt can reference {post} and {context} placeholders.
    Returns the LLM response text.
    """
    from ...llm.base import LLMProvider

    # Build the full prompt with context
    full_prompt = prompt.replace("{post}", post_text)
    full_prompt = full_prompt.replace("{context}", str(context.get("personality_card", ""))[:500])
    full_prompt = full_prompt.replace("{topic}", context.get("topic", ""))
    full_prompt = full_prompt.replace("{platform}", context.get("platform", "linkedin"))

    print(f"\n{'='*60}\n[Custom Agent] Executing...\n{'='*60}", file=sys.stderr)

    if isinstance(llm, LLMProvider):
        result = llm.generate(full_prompt, temperature=0.7, max_tokens=2000)
    else:
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=full_prompt)])
        result = response.content

    return result.strip()
