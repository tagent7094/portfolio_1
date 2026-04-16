"""CLI entry point for digital-dna."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="digital-dna", help="Build personality knowledge graphs and generate authentic social posts.")
generate_app = typer.Typer(help="Generate posts from podcasts or viral topics.")
graph_app = typer.Typer(help="Inspect and export the knowledge graph.")
config_app = typer.Typer(help="View and modify configuration.")
auth_app = typer.Typer(help="Manage subdomain auth credentials for tagent.club deployment.")

app.add_typer(generate_app, name="generate")
app.add_typer(graph_app, name="graph")
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")


@auth_app.command("set")
def auth_set(slug: str = typer.Argument(..., help="Founder slug (e.g. sharath)")):
    """Set or replace the password for a founder slug."""
    from src.auth.store import set_password
    password = typer.prompt(
        f"New password for '{slug}'",
        hide_input=True,
        confirmation_prompt=True,
    )
    set_password(slug, password)
    console.print(f"[green]✓[/green] Password set for [bold]{slug}[/bold]")


@auth_app.command("list")
def auth_list():
    """List founder slugs that have credentials configured."""
    from src.auth.store import list_slugs
    slugs = list_slugs()
    if not slugs:
        console.print("[yellow]No credentials configured.[/yellow] Run [bold]digital-dna auth set <slug>[/bold].")
        return
    for s in slugs:
        console.print(f"  • {s}")


@auth_app.command("admin")
def auth_admin():
    """Set or replace the admin password for the /admin control panel."""
    from src.auth.permissions import set_admin_password
    password = typer.prompt(
        "New admin password",
        hide_input=True,
        confirmation_prompt=True,
    )
    set_admin_password(password)
    console.print("[green]✓[/green] Admin password set")

console = Console()

# Resolve project root (where pyproject.toml lives)
PROJECT_ROOT = Path(__file__).parent.parent


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _save_log(data: dict, name: str):
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"{name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path


@app.command()
def ingest(
    data_dir: str = typer.Option("data/founder-data", help="Directory containing founder files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Read founder data, extract personality, and build the knowledge graph."""
    _setup_logging(verbose)

    config = _load_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]
    vectors_path = PROJECT_ROOT / config["stores"]["vectors_path"]
    card_path = PROJECT_ROOT / config["stores"]["personality_card_path"]

    console.print("[bold blue]Phase 1: Reading files...[/bold blue]")
    from .ingestion.file_reader import read_all_files
    from .ingestion.chunker import chunk_content

    abs_data_dir = PROJECT_ROOT / data_dir
    raw_chunks = read_all_files(str(abs_data_dir))
    if not raw_chunks:
        console.print("[red]No files found in %s[/red]" % abs_data_dir)
        raise typer.Exit(1)
    console.print(f"  Found {len(raw_chunks)} raw chunks from {abs_data_dir}")

    # Create LLM first to determine adaptive chunk size
    console.print("[bold blue]Phase 2: Setting up LLM + adaptive chunking...[/bold blue]")
    from .llm.factory import create_llm
    from .ingestion.llm_extractor import (
        extract_beliefs,
        extract_stories,
        extract_style_rules,
        extract_thinking_models,
        extract_vocabulary,
        generate_personality_card,
    )

    llm = create_llm(str(PROJECT_ROOT / "config" / "llm-config.yaml"), purpose="ingestion")

    # Adaptive chunk size based on provider's context window
    from .ingestion.chunker import adaptive_chunk_size
    from .llm.rate_limiter import get_spec
    provider_spec = get_spec(llm._provider_name, llm._model_name)
    chunk_size = adaptive_chunk_size(llm._provider_name, llm._model_name)
    console.print(f"  Provider: {llm._provider_name}/{llm._model_name}")
    console.print(f"  Context window: {provider_spec.context_window:,} tokens")
    console.print(f"  Max output: {provider_spec.max_output_tokens:,} tokens")
    console.print(f"  Adaptive chunk size: {chunk_size:,} chars ({'local' if provider_spec.is_local else 'cloud'})")

    # Chunk the content with adaptive size
    text_chunks = []
    for chunk in raw_chunks:
        text_chunks.extend(chunk_content(chunk.text, chunk.source_file, max_size=chunk_size))
    console.print(f"  Split into {len(text_chunks)} text chunks")

    console.print("[bold blue]Phase 3: Extracting style stats (NLP)...[/bold blue]")
    from .ingestion.style_extractor import extract_style_stats

    all_text = " ".join(c.text for c in text_chunks)
    style_stats = extract_style_stats(all_text)
    console.print(f"  Extracted {len(style_stats)} style features")

    console.print("[bold blue]Phase 4: LLM extraction (beliefs, stories, style)...[/bold blue]")

    # ── Smart batch plan ──
    from .llm.rate_limiter import calculate_batch_plan, log_batch_plan
    chunk_texts = [c.text for c in text_chunks]
    plan = calculate_batch_plan(
        items=chunk_texts,
        prompt_template_chars=900,  # average prompt template size
        provider=llm._provider_name,
        model=llm._model_name,
        max_output_tokens=2000,
    )
    log_batch_plan(plan)
    console.print(f"  [dim]Batch plan: {plan.batch_size} items/batch, {plan.total_batches} batches, ~{plan.estimated_time_minutes}min est.[/dim]")

    # ── Resume support: load progress checkpoint if it exists ──
    import json as _json
    checkpoint_path = graph_path.parent / "ingestion_checkpoint.json"
    ingestion_log_path = PROJECT_ROOT / "data" / "logs" / "ingestion_live.log"
    ingestion_log_path.parent.mkdir(parents=True, exist_ok=True)

    all_beliefs = []
    all_stories = []
    all_style_rules = []
    all_models = []
    start_chunk = 0

    if checkpoint_path.exists():
        try:
            cp = _json.loads(checkpoint_path.read_text(encoding="utf-8"))
            all_beliefs = cp.get("beliefs", [])
            all_stories = cp.get("stories", [])
            all_style_rules = cp.get("style_rules", [])
            all_models = cp.get("thinking_models", [])
            start_chunk = cp.get("last_chunk", 0) + 1
            console.print(f"  [yellow]Resuming from chunk {start_chunk}/{len(text_chunks)} "
                          f"({len(all_beliefs)} beliefs, {len(all_stories)} stories so far)[/yellow]")
        except Exception as e:
            console.print(f"  [red]Checkpoint corrupted, starting fresh: {e}[/red]")
            start_chunk = 0

    def _write_log(msg: str):
        """Append to live ingestion log file."""
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(ingestion_log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{ts}] {msg}\n")

    _write_log(f"Ingestion started: {len(text_chunks)} chunks, resuming from chunk {start_chunk}")

    # Track consecutive failures to detect fatal errors (billing, auth)
    consecutive_failures = 0
    FATAL_ERROR_KEYWORDS = ["credit balance is too low", "authentication", "invalid api key", "unauthorized", "forbidden"]

    def _is_fatal(error_msg: str) -> bool:
        msg_lower = str(error_msg).lower()
        return any(kw in msg_lower for kw in FATAL_ERROR_KEYWORDS)

    for i in range(start_chunk, len(text_chunks)):
        chunk = text_chunks[i]
        console.print(f"  Processing chunk {i + 1}/{len(text_chunks)}...")
        _write_log(f"Chunk {i + 1}/{len(text_chunks)} — {len(chunk.text)} chars from {chunk.source_file}")

        chunk_had_failure = False

        try:
            new_beliefs = extract_beliefs(chunk.text, llm)
            all_beliefs.extend(new_beliefs)
            _write_log(f"  -> {len(new_beliefs)} beliefs")
        except Exception as e:
            _write_log(f"  x beliefs failed: {e}")
            console.print(f"    [red]Beliefs extraction failed: {e}[/red]")
            chunk_had_failure = True
            if _is_fatal(e):
                console.print(f"\n  [bold red]FATAL: {e}[/bold red]")
                console.print(f"  [red]Aborting ingestion. Fix the issue and re-run to resume from chunk {i}.[/red]")
                _write_log(f"FATAL ERROR — aborting: {e}")
                raise typer.Exit(1)

        try:
            new_stories = extract_stories(chunk.text, llm)
            all_stories.extend(new_stories)
            _write_log(f"  -> {len(new_stories)} stories")
        except Exception as e:
            _write_log(f"  x stories failed: {e}")
            console.print(f"    [red]Stories extraction failed: {e}[/red]")
            chunk_had_failure = True
            if _is_fatal(e):
                console.print(f"\n  [bold red]FATAL: {e}[/bold red]")
                _write_log(f"FATAL ERROR — aborting: {e}")
                raise typer.Exit(1)

        try:
            new_rules = extract_style_rules(chunk.text, llm)
            all_style_rules.extend(new_rules)
            _write_log(f"  -> {len(new_rules)} style rules")
        except Exception as e:
            _write_log(f"  x style rules failed: {e}")
            console.print(f"    [red]Style rules extraction failed: {e}[/red]")
            chunk_had_failure = True
            if _is_fatal(e):
                console.print(f"\n  [bold red]FATAL: {e}[/bold red]")
                _write_log(f"FATAL ERROR — aborting: {e}")
                raise typer.Exit(1)

        try:
            new_models = extract_thinking_models(chunk.text, llm)
            all_models.extend(new_models)
            _write_log(f"  -> {len(new_models)} thinking models")
        except Exception as e:
            _write_log(f"  x thinking models failed: {e}")
            console.print(f"    [red]Thinking models extraction failed: {e}[/red]")
            chunk_had_failure = True
            if _is_fatal(e):
                console.print(f"\n  [bold red]FATAL: {e}[/bold red]")
                _write_log(f"FATAL ERROR — aborting: {e}")
                raise typer.Exit(1)

        # Track consecutive all-fail chunks (provider might be down)
        if chunk_had_failure:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                console.print(f"\n  [bold red]3 consecutive chunks failed. Provider may be down or out of credits.[/bold red]")
                console.print(f"  [red]Aborting. Resume from chunk {i + 1} when ready.[/red]")
                _write_log(f"ABORT: 3 consecutive failures at chunk {i + 1}")
                raise typer.Exit(1)
        else:
            consecutive_failures = 0

        # ── Save checkpoint after every chunk ──
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(_json.dumps({
            "last_chunk": i,
            "total_chunks": len(text_chunks),
            "beliefs": all_beliefs,
            "stories": all_stories,
            "style_rules": all_style_rules,
            "thinking_models": all_models,
        }, default=str), encoding="utf-8")

        # ── Build and save graph incrementally every 10 chunks ──
        if (i + 1) % 10 == 0 or i == len(text_chunks) - 1:
            _write_log(f"  Saving incremental graph ({len(all_beliefs)}b, {len(all_stories)}s, {len(all_style_rules)}r, {len(all_models)}m)")
            console.print(f"    [dim]Saving incremental graph...[/dim]")
            from .graph.builder import build_graph
            from .graph.store import save_graph as _save_g
            incremental_data = {
                "beliefs": all_beliefs,
                "stories": all_stories,
                "style_rules": all_style_rules,
                "thinking_models": all_models,
                "style_stats": style_stats,
            }
            inc_graph = build_graph(incremental_data)
            _save_g(inc_graph, str(graph_path))

    console.print(
        f"  Extracted: {len(all_beliefs)} beliefs, {len(all_stories)} stories, "
        f"{len(all_style_rules)} style rules, {len(all_models)} thinking models"
    )
    _write_log(f"Extraction complete: {len(all_beliefs)}b, {len(all_stories)}s, {len(all_style_rules)}r, {len(all_models)}m")

    console.print("[bold blue]Phase 5: Deduplicating ALL node types with embeddings...[/bold blue]")
    from .vectors.embedder import Embedder
    from .graph.dedup import dedup_extracted_data

    embedder = Embedder(config["embedding"]["model"])

    pre_counts = f"{len(all_beliefs)}b, {len(all_stories)}s, {len(all_style_rules)}r, {len(all_models)}m"

    deduped = dedup_extracted_data({
        "beliefs": all_beliefs,
        "stories": all_stories,
        "style_rules": all_style_rules,
        "thinking_models": all_models,
    }, embedder)

    all_beliefs = deduped["beliefs"]
    all_stories = deduped["stories"]
    all_style_rules = deduped["style_rules"]
    all_models = deduped["thinking_models"]

    post_counts = f"{len(all_beliefs)}b, {len(all_stories)}s, {len(all_style_rules)}r, {len(all_models)}m"
    console.print(f"  Before: {pre_counts}")
    console.print(f"  After:  {post_counts}")

    console.print("[bold blue]Phase 6: Extracting vocabulary fingerprint...[/bold blue]")
    all_text = " ".join(c.text for c in text_chunks)
    vocabulary = extract_vocabulary(all_text, llm)
    console.print(f"  Signature phrases: {len(vocabulary.get('phrases_used', []))}")
    console.print(f"  Banned words: {len(vocabulary.get('phrases_never', []))}")
    _write_log(f"Vocabulary: {len(vocabulary.get('phrases_used', []))} used, {len(vocabulary.get('phrases_never', []))} banned")

    console.print("[bold blue]Phase 7: Generating personality card...[/bold blue]")
    extracted_data = {
        "beliefs": all_beliefs,
        "stories": all_stories,
        "style_rules": all_style_rules,
        "thinking_models": all_models,
        "vocabulary": vocabulary,
        "style_stats": style_stats,
    }
    personality_card = generate_personality_card(extracted_data, llm)
    extracted_data["personality_card"] = personality_card

    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(personality_card, encoding="utf-8")
    console.print(f"  Personality card saved to {card_path} ({len(personality_card)} chars)")
    _write_log(f"Personality card: {len(personality_card)} chars")

    console.print("[bold blue]Phase 8: Building final knowledge graph...[/bold blue]")
    from .graph.builder import build_graph
    from .graph.store import save_graph, load_graph

    graph = build_graph(extracted_data)
    save_graph(graph, str(graph_path))
    _write_log(f"Final graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    console.print("[bold blue]Phase 7: Building vector store...[/bold blue]")
    from .vectors.store import VectorStore

    vs = VectorStore(persist_dir=str(vectors_path))
    chunk_texts = [c.text for c in text_chunks]
    chunk_ids = [c.chunk_id for c in text_chunks]
    chunk_metas = [{"source": c.source_file, "position": c.position} for c in text_chunks]
    embeddings = embedder.embed(chunk_texts)
    vs.add(ids=chunk_ids, texts=chunk_texts, metadatas=chunk_metas, embeddings=embeddings)

    console.print(f"  Stored {len(chunk_texts)} chunks in vector store")

    # Save log
    _save_log(extracted_data, "ingest")

    # Clean up checkpoint on success
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        console.print("  [dim]Checkpoint cleared (ingestion complete)[/dim]")

    _write_log("Ingestion complete!")

    console.print("[bold green]Ingestion complete![/bold green]")
    console.print(f"  Beliefs: {len(all_beliefs)}")
    console.print(f"  Stories: {len(all_stories)}")
    console.print(f"  Style rules: {len(all_style_rules)}")
    console.print(f"  Thinking models: {len(all_models)}")
    console.print(f"  Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")


@generate_app.command("podcast")
def generate_podcast(
    file: str = typer.Argument(..., help="Path to podcast transcript file"),
    platform: str = typer.Option("linkedin", help="Target platform: linkedin, twitter, email"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a post from a podcast transcript."""
    _setup_logging(verbose)

    config = _load_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]
    vectors_path = PROJECT_ROOT / config["stores"]["vectors_path"]

    from .llm.factory import create_llm
    from .graph.store import load_graph
    from .generation.agents import AgentSwarm
    from .humanization.humanizer import humanize_post
    from .humanization.quality_gate import quality_gate

    llm = create_llm(str(PROJECT_ROOT / "config" / "llm-config.yaml"))
    graph = load_graph(str(graph_path))

    if graph.number_of_nodes() == 0:
        console.print("[red]No knowledge graph found. Run 'digital-dna ingest' first.[/red]")
        raise typer.Exit(1)

    transcript_path = Path(file)
    if not transcript_path.is_absolute():
        transcript_path = PROJECT_ROOT / file
    transcript = transcript_path.read_text(encoding="utf-8", errors="replace")
    console.print(f"[blue]Loaded transcript: {len(transcript)} chars[/blue]")

    swarm = AgentSwarm(llm, graph)

    console.print("[bold blue]Step 1: Extracting & voting on narratives...[/bold blue]")
    winner_narrative, narr_scores = swarm.extract_and_vote_narrative(transcript)
    if not winner_narrative:
        console.print("[red]No narratives extracted from transcript.[/red]")
        raise typer.Exit(1)
    console.print(f"  Winning narrative: {winner_narrative.get('hook', 'N/A')}")

    console.print("[bold blue]Step 2: Generating & voting on posts...[/bold blue]")
    winner_post, post_scores = swarm.generate_and_vote_posts(winner_narrative, platform)
    if not winner_post:
        console.print("[red]No posts generated.[/red]")
        raise typer.Exit(1)

    console.print("[bold blue]Step 3: Humanizing...[/bold blue]")
    humanized = humanize_post(winner_post["text"], graph, llm, platform)

    console.print("[bold blue]Step 4: Quality gate...[/bold blue]")
    qg = quality_gate(humanized, graph)

    if not qg["passed"]:
        console.print(f"[yellow]Quality gate score: {qg['score']}% (below threshold). Re-humanizing...[/yellow]")
        humanized = humanize_post(humanized, graph, llm, platform)
        qg = quality_gate(humanized, graph)

    # Save output
    output_dir = PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"post_{platform}_{ts}.txt"
    output_path.write_text(humanized, encoding="utf-8")

    _save_log({
        "narrative": winner_narrative,
        "narrative_scores": narr_scores,
        "post_scores": post_scores,
        "quality_gate": qg,
        "platform": platform,
    }, f"generate_podcast_{platform}")

    console.print("\n[bold green]Generated Post:[/bold green]\n")
    console.print(humanized)
    console.print(f"\n[dim]Quality: {qg['score']}% | Saved: {output_path}[/dim]")


@generate_app.command("topic")
def generate_topic(
    topic: str = typer.Argument(..., help="Viral topic to generate a post about"),
    platform: str = typer.Option("linkedin", help="Target platform: linkedin, twitter, email"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a post on a viral topic."""
    _setup_logging(verbose)

    config = _load_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]
    vectors_path = PROJECT_ROOT / config["stores"]["vectors_path"]

    from .llm.factory import create_llm
    from .graph.store import load_graph
    from .vectors.store import VectorStore
    from .generation.topic_matcher import match_topic_to_graph
    from .generation.agents import AgentSwarm
    from .humanization.humanizer import humanize_post
    from .humanization.quality_gate import quality_gate

    llm = create_llm(str(PROJECT_ROOT / "config" / "llm-config.yaml"))
    graph = load_graph(str(graph_path))

    if graph.number_of_nodes() == 0:
        console.print("[red]No knowledge graph found. Run 'digital-dna ingest' first.[/red]")
        raise typer.Exit(1)

    vs = None
    try:
        vs = VectorStore(persist_dir=str(PROJECT_ROOT / vectors_path))
    except Exception:
        pass

    console.print(f"[blue]Matching topic to graph: {topic}[/blue]")
    match = match_topic_to_graph(topic, graph, vs, llm)
    console.print(f"  Angle: {match.get('suggested_angle', 'N/A')}")

    # Create a narrative from the match
    narrative = {
        "id": "topic_match",
        "narrative": match.get("suggested_angle", topic),
        "angle": f"Based on founder's beliefs about {topic}",
        "hook": match.get("suggested_angle", topic)[:100],
    }

    swarm = AgentSwarm(llm, graph)

    console.print("[bold blue]Generating & voting on posts...[/bold blue]")
    winner_post, post_scores = swarm.generate_and_vote_posts(narrative, platform, topic)
    if not winner_post:
        console.print("[red]No posts generated.[/red]")
        raise typer.Exit(1)

    console.print("[bold blue]Humanizing...[/bold blue]")
    humanized = humanize_post(winner_post["text"], graph, llm, platform)

    console.print("[bold blue]Quality gate...[/bold blue]")
    qg = quality_gate(humanized, graph)

    if not qg["passed"]:
        console.print(f"[yellow]Quality: {qg['score']}%. Re-humanizing...[/yellow]")
        humanized = humanize_post(humanized, graph, llm, platform)
        qg = quality_gate(humanized, graph)

    output_dir = PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"post_{platform}_{ts}.txt"
    output_path.write_text(humanized, encoding="utf-8")

    _save_log({
        "topic": topic,
        "match": match,
        "post_scores": post_scores,
        "quality_gate": qg,
        "platform": platform,
    }, f"generate_topic_{platform}")

    console.print("\n[bold green]Generated Post:[/bold green]\n")
    console.print(humanized)
    console.print(f"\n[dim]Quality: {qg['score']}% | Saved: {output_path}[/dim]")


@graph_app.command("show")
def graph_show(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Print graph summary."""
    _setup_logging(verbose)
    config = _load_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]

    from .graph.store import load_graph

    graph = load_graph(str(graph_path))

    if graph.number_of_nodes() == 0:
        console.print("[yellow]Graph is empty. Run 'digital-dna ingest' first.[/yellow]")
        return

    # Count by type
    counts = {}
    for _, data in graph.nodes(data=True):
        t = data.get("node_type", "unknown")
        counts[t] = counts.get(t, 0) + 1

    table = Table(title="Knowledge Graph Summary")
    table.add_column("Node Type", style="cyan")
    table.add_column("Count", justify="right", style="green")

    for node_type, count in sorted(counts.items()):
        table.add_row(node_type, str(count))

    table.add_row("", "")
    table.add_row("[bold]Total Nodes[/bold]", f"[bold]{graph.number_of_nodes()}[/bold]")
    table.add_row("[bold]Total Edges[/bold]", f"[bold]{graph.number_of_edges()}[/bold]")

    pc = graph.graph.get("personality_card", "")
    table.add_row("[bold]Personality Card[/bold]", f"[bold]{len(pc.split())} words[/bold]")

    console.print(table)


@graph_app.command("export")
def graph_export(
    output: str = typer.Option("data/knowledge-graph/graph-export.json", help="Output path"),
):
    """Export graph as JSON."""
    config = _load_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]

    from .graph.store import load_graph
    import networkx as nx

    graph = load_graph(str(graph_path))
    data = nx.node_link_data(graph)
    out_path = PROJECT_ROOT / output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    console.print(f"[green]Graph exported to {out_path}[/green]")


@config_app.command("show")
def config_show():
    """Show current configuration."""
    config = _load_config()
    console.print_json(json.dumps(config, indent=2))


@config_app.command("set-llm")
def config_set_llm(
    provider: str = typer.Argument(..., help="LLM provider: ollama, lmstudio, anthropic, openai"),
    model: str = typer.Option(None, help="Model name"),
    base_url: str = typer.Option(None, help="Base URL for local providers"),
    api_key: str = typer.Option(None, help="API key for cloud providers"),
):
    """Switch LLM provider."""
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    config = _load_config()

    config["llm"]["provider"] = provider
    if model:
        config["llm"]["model"] = model
    if base_url:
        config["llm"]["base_url"] = base_url
    if api_key:
        config["llm"]["api_key"] = api_key

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    console.print(f"[green]LLM provider set to: {provider}[/green]")
    if model:
        console.print(f"  Model: {model}")


@app.command()
def ui(
    port: int = typer.Option(8501, help="Port for the Streamlit server"),
):
    """Launch the web UI for graph visualization and editing."""
    import subprocess

    app_path = PROJECT_ROOT / "src" / "ui" / "app.py"
    console.print(f"[blue]Launching Streamlit UI at http://localhost:{port}[/blue]")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
    ])


if __name__ == "__main__":
    app()
