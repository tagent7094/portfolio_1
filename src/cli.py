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
graph_app = typer.Typer(help="Inspect and export the knowledge graph.")
config_app = typer.Typer(help="View and modify configuration.")
auth_app = typer.Typer(help="Manage subdomain auth credentials for tagent.club deployment.")

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
def ingest():
    """[Removed] Ingestion pipeline has been removed. Use the web UI batch pipeline instead."""
    console.print("[red]The ingest command has been removed.[/red]")
    console.print("Use the web UI Generate button or the batch-generate CLI command instead.")
    raise typer.Exit(1)


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


@app.command("batch-generate")
def batch_generate(
    founder: str = typer.Option(..., help="Founder slug (e.g. sharath)"),
    sources: int = typer.Option(10, help="Number of source posts to adapt"),
    creativity: float = typer.Option(0.5, help="Creativity level 0.0-1.0"),
    platform: str = typer.Option("linkedin", help="Target platform"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run batch post generation — 9 posts per source, 10 sources = 90 posts."""
    _setup_logging(verbose)
    from src.batch.session import run_batch_cli
    output = run_batch_cli(founder, sources, creativity, platform)
    total = output["metadata"]["total_posts"]
    packs = len(output.get("packs", []))
    console.print(f"[green]Done[/green] Batch complete: {total} posts across {packs} packs")


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
