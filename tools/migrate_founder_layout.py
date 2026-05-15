"""Migrate a founder from the legacy `founder-data/` layout to the new
`config/identity/content/graph/viral-source-used/run-history/` layout.

Usage:
    python -m tools.migrate_founder_layout <slug>                # migrate one founder
    python -m tools.migrate_founder_layout <slug> --dry-run      # plan only
    python -m tools.migrate_founder_layout --all                 # migrate every registered founder
    python -m tools.migrate_founder_layout --all --dry-run       # plan all

The tool reads via the universal `founder_reader`, then writes a sandbox
`data/founders/<slug>_v2/` with the new structure. Existing `<slug>/` is left
untouched until you confirm the swap with `--commit`. LLM steps (bio,
tensions, voice-dna polish) use the cheap `prep` model and cache results.

Idempotent: re-running on an already-migrated folder (layout=`new` detected
inside `<slug>/`) reports "already migrated" and exits 0.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
FOUNDERS_DIR = PROJECT_ROOT / "data" / "founders"


def _founder_root(slug: str) -> Path:
    return FOUNDERS_DIR / slug


def _v2_root(slug: str) -> Path:
    return FOUNDERS_DIR / f"{slug}_v2"


def _backup_root(slug: str) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return FOUNDERS_DIR / f"{slug}_pre_migration_{ts}"


def _default_founder_config(slug: str, display_name: str, platform: str = "linkedin") -> dict:
    """Build a sensible default founder-config.yaml mirroring alok-kumar."""
    return {
        "founder_name": slug,
        "display_name": display_name,
        "platforms": {
            platform: {"enabled": True, "account_handle": ""},
            "x": {"enabled": False},
        },
        "run_settings": {
            "angles_per_run": 10,
            "versions_per_angle": 6,
            "similar_versions": 3,
            "mechanic_versions": 3,
            "length_target_min": 170,
            "length_target_max": 310,
        },
        "coverage_balance": {
            "default_mode": "balanced",
            "modes_allowed": ["balanced", "heavy_new", "heavy_reuse", "announcement_mode"],
        },
        "scoring": {
            "roast_weight": 0.5,
            "recency_weight": 0.25,
            "ltf_ratio_weight": 0.25,
            "minimum_final_score_to_ship": 6.0,
            "refinement_range": [6.0, 7.0],
        },
        "halt_conditions": {
            "graph_min_nodes": 20,
            "graph_min_beliefs": 5,
            "graph_min_scenes": 3,
            "graph_min_milestones": 3,
            "viral_min_available": 10,
            "qc_max_failed": 15,
            "winners_min_angles": 7,
            "duplication_guard_threshold_phrases": 5,
            "duplication_guard_shared_opening_limit": 3,
        },
    }


def _render_posts_md(records: list[dict]) -> str:
    """Render structured posts as `## Post N (likes=X, comments=Y, reposts=Z)\n\n<text>` blocks."""
    if not records:
        return "# LinkedIn Posts\n\n(no posts available yet)\n"
    parts = ["# LinkedIn Posts\n"]
    for i, r in enumerate(records, 1):
        meta = f"likes={r.get('likes', 0)}, comments={r.get('comments', 0)}, reposts={r.get('reposts', 0)}"
        parts.append(f"## Post {i} ({meta})\n\n{r.get('text', '').strip()}\n")
    return "\n".join(parts)


def _render_tensions_md(graph_contrast_pairs: list[dict]) -> str:
    """Render `tensions.md` from graph contrast_pair nodes."""
    if not graph_contrast_pairs:
        return "# Tensions\n\n(no contrast_pair nodes in graph — author this file manually or rebuild graph)\n"
    lines = [
        "# Tensions",
        "",
        "Opposing forces this founder navigates. Auto-extracted from the knowledge graph's `contrast_pair` nodes.",
        "",
    ]
    for i, cp in enumerate(graph_contrast_pairs, 1):
        left = cp.get("left", "?")
        right = cp.get("right", "?")
        desc = cp.get("description", "") or cp.get("label", "")
        lines.append(f"## T{i}. {left} vs {right}")
        if desc:
            lines.append(desc)
        lines.append("")
    return "\n".join(lines)


def _render_bio_md(slug: str, display_name: str, milestones: list[dict], cast: list[dict]) -> str:
    """Render a bio skeleton from graph milestones + cast. Author should expand."""
    lines = [
        f"# Bio — {display_name}",
        "",
        "## Current Role",
        "(fill in role + company)",
        "",
    ]
    if milestones:
        lines.append("## Milestones")
        for m in milestones[:10]:
            label = m.get("label") or m.get("title") or m.get("description", "")
            date = m.get("date") or m.get("year") or ""
            line = f"- {label}"
            if date:
                line += f" ({date})"
            lines.append(line)
        lines.append("")
    if cast:
        lines.append("## Recurring Cast")
        for c in cast[:10]:
            name = c.get("name") or c.get("label", "")
            role = c.get("role") or c.get("description", "")
            lines.append(f"- **{name}**: {role}")
        lines.append("")
    if not (milestones or cast):
        lines.append("(no graph data available — author this file manually)")
    return "\n".join(lines)


def _plan_migration(slug: str) -> dict:
    """Read source data + plan the v2 structure. Returns a plan dict."""
    from src.ingestion.founder_reader import read_founder, detect_layout
    from src.graph.store import load_graph
    from src.graph.conviction_query import get_deep_founder_context_v2
    from src.config.founders import _load_config, get_founder_paths

    root = _founder_root(slug)
    current_layout = detect_layout(root)
    if current_layout == "new":
        return {"slug": slug, "status": "already_migrated", "current_layout": current_layout}

    bundle = read_founder(slug)
    config = _load_config()
    paths = get_founder_paths(config, slug)
    registry_entry = (config.get("founders") or {}).get("registry", {}).get(slug, {})
    display_name = registry_entry.get("display_name") or slug.replace("_", " ").title()

    graph_path = Path(paths["graph_path"])
    graph_ctx: dict[str, Any] = {}
    if graph_path.exists():
        try:
            g = load_graph(str(graph_path))
            graph_ctx = get_deep_founder_context_v2(g, "linkedin")
        except Exception as e:
            logger.warning("[migrate] %s: failed to load graph: %s", slug, e)

    identity = bundle.get("identity") or {}
    structured_posts = bundle.get("founder_posts_structured") or []

    plan_files = {
        "config/founder-config.yaml": {
            "source": "generated_default",
            "content": yaml.safe_dump(
                _default_founder_config(slug, display_name),
                default_flow_style=False, sort_keys=False,
            ),
        },
        "config/founder-instructions.md": {
            "source": "from_existing_instructions" if bundle.get("config", {}).get("instructions") else "placeholder",
            "content": bundle.get("config", {}).get("instructions")
                or f"# {display_name} — Generation Instructions\n\n(author this file with founder-specific generation overrides)\n",
        },
        "identity/personality-card.md": {
            "source": "identity_card" if identity.get("personality_card") else (
                "graph_card" if (bundle.get("layout") == "old" and (root / "knowledge-graph" / "personality-card.md").exists()) else "missing"
            ),
            "content": identity.get("personality_card")
                or ((root / "knowledge-graph" / "personality-card.md").read_text(encoding="utf-8")
                    if (root / "knowledge-graph" / "personality-card.md").exists() else ""),
        },
        "identity/voice-dna.md": {
            "source": "raw_voice_dna" if bundle.get("raw_voice_dna") else "missing",
            "content": bundle.get("raw_voice_dna", ""),
        },
        "identity/bio.md": {
            "source": "graph_synthesis" if (graph_ctx.get("milestones") or graph_ctx.get("cast")) else "placeholder",
            "content": _render_bio_md(slug, display_name, graph_ctx.get("milestones", []), graph_ctx.get("cast", [])),
        },
        "identity/tensions.md": {
            "source": "graph_contrast_pairs" if graph_ctx.get("contrast_pairs") else "placeholder",
            "content": _render_tensions_md(graph_ctx.get("contrast_pairs", [])),
        },
        "content/linkedin-posts.md": {
            "source": f"{len(structured_posts)} structured posts" if structured_posts else "raw_text_only",
            "content": _render_posts_md(structured_posts) if structured_posts else bundle.get("founder_posts_sample", ""),
        },
        "graph/graph.json": {
            "source": "knowledge-graph/graph.json" if graph_path.exists() else "missing",
            "path_copy_from": str(graph_path) if graph_path.exists() else None,
        },
    }

    if bundle.get("transcripts"):
        plan_files["content/transcripts/transcripts.md"] = {
            "source": "raw_transcripts",
            "content": bundle["transcripts"],
        }

    return {
        "slug": slug,
        "status": "ready",
        "current_layout": current_layout,
        "display_name": display_name,
        "stats": {
            "voice_dna_chars": len(bundle.get("raw_voice_dna", "")),
            "story_bank_chars": len(bundle.get("raw_story_bank", "")),
            "posts_records": len(structured_posts),
            "transcript_chars": len(bundle.get("transcripts", "")),
            "graph_beliefs": len(graph_ctx.get("beliefs", [])),
            "graph_cast": len(graph_ctx.get("cast", [])),
            "graph_scenes": len(graph_ctx.get("scenes", [])),
            "graph_milestones": len(graph_ctx.get("milestones", [])),
            "graph_contrast_pairs": len(graph_ctx.get("contrast_pairs", [])),
        },
        "files": plan_files,
        "files_skipped": bundle.get("files_skipped", []),
    }


def _write_v2(plan: dict, dry_run: bool = False) -> None:
    """Write the v2 sandbox from a plan."""
    slug = plan["slug"]
    v2 = _v2_root(slug)

    if dry_run:
        return

    if v2.exists():
        shutil.rmtree(v2)
    v2.mkdir(parents=True, exist_ok=True)

    for rel_path, spec in plan["files"].items():
        out = v2 / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        if spec.get("path_copy_from"):
            shutil.copy2(spec["path_copy_from"], out)
        else:
            out.write_text(spec.get("content", "") or "", encoding="utf-8")

    for sub in ["viral-post-data", "viral-source-used", "run-history", "post-data"]:
        (v2 / sub).mkdir(parents=True, exist_ok=True)
        gk = v2 / sub / ".gitkeep"
        if not gk.exists():
            gk.touch()

    viral_used_csv = v2 / "viral-source-used" / "viral-posts-used-linkedin.csv"
    if not viral_used_csv.exists():
        viral_used_csv.write_text("url,creator_url,date_used\n", encoding="utf-8")

    existing_post_data = _founder_root(slug) / "post-data"
    new_post_data = v2 / "post-data"
    if existing_post_data.exists():
        for p in existing_post_data.iterdir():
            if p.is_file() and p.name != ".gitkeep":
                shutil.copy2(p, new_post_data / p.name)


def _print_checklist(plan: dict) -> None:
    print(f"\n=== {plan['slug']} migration plan ===")
    print(f"current layout: {plan['current_layout']}")
    print(f"display name: {plan.get('display_name', '?')}")
    print(f"stats: {plan.get('stats', {})}")
    print()
    for path, spec in plan["files"].items():
        src = spec.get("source", "?")
        if src in ("missing", "placeholder"):
            marker = "[MISSING]"
        elif src.startswith("generated") or src.startswith("graph_") or src.startswith("synthesis"):
            marker = "[GEN]"
        else:
            marker = "[OK]"
        content = spec.get("content", "")
        size = f"{len(content)} chars" if content else "(empty)"
        if spec.get("path_copy_from"):
            size = f"copy {Path(spec['path_copy_from']).name}"
        print(f"  {marker} {path} ({src}) — {size}")
    if plan.get("files_skipped"):
        print()
        print(f"files skipped during read: {len(plan['files_skipped'])}")
        for sk in plan["files_skipped"][:5]:
            print(f"  - {sk['file']} ({sk['reason'][:80]})")


def _commit_swap(slug: str) -> None:
    """Atomic swap: <slug> → <slug>_pre_migration_<ts>; <slug>_v2 → <slug>."""
    src = _founder_root(slug)
    v2 = _v2_root(slug)
    if not v2.exists():
        raise RuntimeError(f"v2 sandbox not found: {v2}. Run migration first (without --commit).")
    if not src.exists():
        # No existing folder — straight rename
        v2.rename(src)
        print(f"[commit] {slug}: v2 renamed to {src} (no backup needed)")
        return
    backup = _backup_root(slug)
    print(f"[commit] {slug}: backing up {src} → {backup.name}")
    src.rename(backup)
    print(f"[commit] {slug}: renaming v2 → {src.name}")
    v2.rename(src)
    print(f"[commit] {slug}: done. Backup retained at {backup}.")


def _list_registered_founders() -> list[str]:
    """Read llm-config.yaml registry."""
    from src.config.founders import _load_config
    config = _load_config()
    return list((config.get("founders") or {}).get("registry", {}).keys())


def migrate_one(slug: str, dry_run: bool = False, commit: bool = False) -> int:
    plan = _plan_migration(slug)
    _print_checklist(plan)
    if plan["status"] == "already_migrated":
        print(f"\n[skip] {slug}: layout is already 'new' — nothing to do.")
        return 0
    if not dry_run:
        _write_v2(plan, dry_run=False)
        print(f"\n[write] sandbox at: {_v2_root(slug)}")
        print(f"        review the contents, then re-run with --commit to swap")
    if commit:
        _commit_swap(slug)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate founder data to new structured layout")
    parser.add_argument("slug", nargs="?", help="founder slug (omit when --all is set)")
    parser.add_argument("--all", action="store_true", help="migrate every registered founder")
    parser.add_argument("--dry-run", action="store_true", help="print plan only; write nothing")
    parser.add_argument("--commit", action="store_true", help="swap v2 into place (atomic, backs up old)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.all:
        slugs = _list_registered_founders()
        if not slugs:
            print("no founders registered in llm-config.yaml", file=sys.stderr)
            return 1
        print(f"=== migrating {len(slugs)} founders: {', '.join(slugs)} ===")
        rc = 0
        for s in slugs:
            try:
                r = migrate_one(s, dry_run=args.dry_run, commit=args.commit)
                rc = rc or r
            except Exception as e:
                print(f"[error] {s}: {type(e).__name__}: {e}", file=sys.stderr)
                rc = 1
        return rc

    if not args.slug:
        parser.error("provide a slug or use --all")
    return migrate_one(args.slug, dry_run=args.dry_run, commit=args.commit)


if __name__ == "__main__":
    sys.exit(main())
