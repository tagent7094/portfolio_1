# Debug Session: UI & Pipeline Sync Issues

## Symptoms
1. **Show Thinking toggle not working**: Toggle is checked in the UI, but intermediate steps aren't visible.
2. **Raw `<reasoning>` blocks in final posts**: LLM reasoning outputs are showing up in the generated texts.
3. **Graph Traversal Relevance**: Unsure if traversed nodes strictly align with the topic context.
4. **Reasoning UI Request**: The reasoning text should be a faded section on top of the post that disappears after generation.
5. **num_variants ignoring UI selection**: Console logs show X/10 variants generated even when user selected 5 in `GeneratePage.tsx`.

## Evidence Collection Plan
1. Check `webapp-react/src/pages/GeneratePage.tsx` routing `num_variants` parameter into SSE requests.
2. Check `server.py` and `src/langchain_agents/graph_workflow.py` to see if `num_variants` is passed correctly to `run_topic_generation_with_events`.
3. Check `src/humanization/quality_gate.py` and `humanizer.py` to see if `<reasoning>` tags are being stripped out properly before finalizing the post.
4. Check Graph API retrieval `src/graph/query.py` or similar to see node selection relevance metrics.
