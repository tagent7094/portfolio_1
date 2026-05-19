"""Build the askrevsure knowledge graph from per-client extracts.

Reads every JSON file under data/founders/deepinder/revsure-extracts/,
builds a NetworkX DiGraph with Client/Pain/ToolFrom/Tussle/Contrarian/
RevSureProblem/Win/BestAspect/Quote nodes, and serializes via the
existing src.graph.store.save_graph helper.

Edge types (Client-centric hub-and-spoke + every claim cites its quote):
  Client --HAS_PAIN--> Pain
  Client --SWITCHED_FROM--> ToolFrom
  Client --HAS_TUSSLE--> Tussle
  Client --VOICED_CONTRARIAN--> Contrarian
  Client --HIT_PROBLEM--> RevSureProblem
  Client --SECURED_WIN--> Win
  Client --PRAISED--> BestAspect
  <claim node> --CITED_BY--> Quote
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from pathlib import Path

import networkx as nx

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.store import save_graph  # noqa: E402

EXTRACTS_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "revsure-extracts"
GRAPH_PATH = PROJECT_ROOT / "data" / "founders" / "deepinder" / "knowledge-graph" / "revsure_qa_graph.json"

logger = logging.getLogger("revsure_graph_builder")


def _id(prefix: str, payload: str) -> str:
    """Stable, short, content-addressed node id."""
    return f"{prefix}_{hashlib.md5(payload.encode('utf-8', errors='replace')).hexdigest()[:10]}"


def _quote_id(quote: str, speaker: str, timestamp: str) -> str:
    return _id("q", f"{speaker}|{timestamp}|{quote[:200]}")


def _client_id(name: str) -> str:
    return _id("client", name.lower().strip())


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower() or "x"


def _add_claim_node(g: nx.DiGraph, *, prefix: str, label: str, payload: dict, client_id: str, edge_type: str) -> str | None:
    """Add a claim node + its CITED_BY Quote edge + the Client-->Claim edge.

    Returns the new claim node id, or None if `payload` lacks a quote
    (claim nodes are only added when a verbatim quote backs them).
    """
    quote = (payload.get("quote") or "").strip()
    if not quote:
        return None
    speaker = payload.get("speaker", "unknown") or "unknown"
    ts = payload.get("timestamp", "") or ""

    claim_id = _id(prefix, f"{client_id}|{label[:80]}|{quote[:80]}")
    if claim_id not in g:
        g.add_node(claim_id, node_type=prefix, label=label[:200], **{
            k: v for k, v in payload.items() if k not in ("quote", "speaker", "timestamp")
        })
    g.add_edge(client_id, claim_id, edge_type=edge_type)

    qid = _quote_id(quote, speaker, ts)
    if qid not in g:
        g.add_node(qid, node_type="Quote", text=quote, speaker=speaker, timestamp=ts)
    g.add_edge(claim_id, qid, edge_type="CITED_BY")
    return claim_id


def build_graph_from_extracts(extracts_dir: Path = EXTRACTS_DIR) -> nx.DiGraph:
    g = nx.DiGraph()

    json_files = sorted(extracts_dir.glob("*.json"))
    if not json_files:
        logger.warning("no extract JSON files under %s — graph will be empty", extracts_dir)
        return g

    for jpath in json_files:
        try:
            extract = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("failed to read %s: %s", jpath.name, e)
            continue

        client_name = extract.get("client_name") or jpath.stem
        cid = _client_id(client_name)

        before = extract.get("before_state") or {}
        after = extract.get("after_state") or {}
        g.add_node(
            cid,
            node_type="Client",
            label=client_name,
            slug=_slug(client_name),
            before_stack=before.get("stack", []) or [],
            before_pain_summary=before.get("pain_summary", "") or "",
            before_kpis_unhealthy=before.get("kpis_unhealthy", []) or [],
            after_with_revsure=after.get("with_revsure", "") or "",
            after_wins_realized=after.get("wins_realized", []) or [],
            after_open_issues=after.get("open_issues", []) or [],
            source_files=(extract.get("_meta") or {}).get("source_files", []),
        )

        findings = extract.get("findings") or {}

        for item in findings.get("pains", []) or []:
            _add_claim_node(g, prefix="Pain", label=item.get("summary", ""), payload=item, client_id=cid, edge_type="HAS_PAIN")

        for item in findings.get("tools_switched_from", []) or []:
            label = item.get("tool") or item.get("vendor") or "tool"
            _add_claim_node(g, prefix="ToolFrom", label=label, payload=item, client_id=cid, edge_type="SWITCHED_FROM")

        for item in findings.get("political_tussles", []) or []:
            label = item.get("tension_label") or " ↔ ".join(item.get("actors", []) or [])
            _add_claim_node(g, prefix="Tussle", label=label, payload=item, client_id=cid, edge_type="HAS_TUSSLE")

        for item in findings.get("contrarians", []) or []:
            _add_claim_node(g, prefix="Contrarian", label=item.get("claim", ""), payload=item, client_id=cid, edge_type="VOICED_CONTRARIAN")

        for item in findings.get("revsure_problems", []) or []:
            label = f"[{item.get('category', '?')}] {item.get('problem', '')}"
            _add_claim_node(g, prefix="RevSureProblem", label=label, payload=item, client_id=cid, edge_type="HIT_PROBLEM")

        wins = findings.get("wins") or {}
        for item in wins.get("immediate", []) or []:
            payload = {**item, "horizon": "immediate"}
            _add_claim_node(g, prefix="Win", label=item.get("win", ""), payload=payload, client_id=cid, edge_type="SECURED_WIN")
        for item in wins.get("long_term", []) or []:
            payload = {**item, "horizon": "long_term"}
            _add_claim_node(g, prefix="Win", label=item.get("win", ""), payload=payload, client_id=cid, edge_type="SECURED_WIN")

        for item in findings.get("best_about_revsure", []) or []:
            _add_claim_node(g, prefix="BestAspect", label=item.get("summary", ""), payload=item, client_id=cid, edge_type="PRAISED")

        logger.info("[%s] added: pains=%d tools=%d tussles=%d contrarians=%d problems=%d wins=%d best=%d",
                    client_name,
                    len(findings.get("pains", []) or []),
                    len(findings.get("tools_switched_from", []) or []),
                    len(findings.get("political_tussles", []) or []),
                    len(findings.get("contrarians", []) or []),
                    len(findings.get("revsure_problems", []) or []),
                    sum(len(wins.get(k, []) or []) for k in ("immediate", "long_term")),
                    len(findings.get("best_about_revsure", []) or []))

    g.graph["schema_version"] = "v1.0.0"
    g.graph["graph_type"] = "revsure_qa"
    return g


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    g = build_graph_from_extracts()
    logger.info("graph built: %d nodes, %d edges", g.number_of_nodes(), g.number_of_edges())

    by_type: dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        t = attrs.get("node_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", k, v)

    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_graph(g, str(GRAPH_PATH))
    logger.info("wrote %s", GRAPH_PATH)


if __name__ == "__main__":
    main()
