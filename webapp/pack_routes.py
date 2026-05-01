"""
Post-pack routes: browse and read per-founder Excel packs.

  GET  /api/admin/founders/{slug}/post-packs          → list available dates
  GET  /api/admin/founders/{slug}/post-packs/{date}   → parse Excel → JSON
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from webapp.auth_routes import _require_admin

router = APIRouter(prefix="/api/admin/founders", tags=["admin-packs"])
logger = logging.getLogger(__name__)

FOUNDERS_DIR = Path(__file__).parent.parent / "data" / "founders"


def _post_data_dir(slug: str) -> Path:
    """Resolve the post-data/ folder for a slug, tolerating mixed-case folder names."""
    if FOUNDERS_DIR.is_dir():
        for folder in FOUNDERS_DIR.iterdir():
            if not folder.is_dir():
                continue
            folder_slug = folder.name.lower().replace(" ", "_").replace("-", "_")
            if folder_slug == slug:
                return folder / "post-data"
    return FOUNDERS_DIR / slug / "post-data"


def _extract_date(filename: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else ""


@router.get("/{slug}/post-packs")
async def list_post_packs(slug: str, request: Request):
    _require_admin(request)
    post_dir = _post_data_dir(slug)
    if not post_dir.exists():
        return {"packs": []}

    packs = []
    for f in sorted(post_dir.glob("*.xlsx"), reverse=True):
        packs.append({
            "filename": f.name,
            "date": _extract_date(f.name),
            "size_kb": round(f.stat().st_size / 1024, 1),
        })
    return {"packs": packs}


@router.get("/{slug}/post-packs/{date}")
async def get_post_pack(slug: str, date: str, request: Request):
    _require_admin(request)
    post_dir = _post_data_dir(slug)

    target: Path | None = None
    for f in post_dir.glob("*.xlsx"):
        if date in f.name:
            target = f
            break

    if not target or not target.exists():
        raise HTTPException(status_code=404, detail=f"No pack found for {date}")

    try:
        import openpyxl  # type: ignore
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed on server")

    try:
        wb = openpyxl.load_workbook(target, read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not open Excel: {exc}")

    result: dict = {"readme": {}, "headers": [], "posts": []}

    if "README" in wb.sheetnames:
        for row in wb["README"].iter_rows(values_only=True):
            if row[0] is not None and row[1] is not None:
                result["readme"][str(row[0])] = str(row[1])

    if "Posts" in wb.sheetnames:
        ws = wb["Posts"]
        headers: list[str] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(c) if c is not None else f"col_{j}" for j, c in enumerate(row)]
                result["headers"] = headers
            else:
                if all(v is None for v in row):
                    continue
                post: dict = {}
                for j, val in enumerate(row):
                    if j < len(headers):
                        if val is None:
                            post[headers[j]] = ""
                        elif isinstance(val, float) and val == int(val):
                            post[headers[j]] = int(val)
                        else:
                            post[headers[j]] = val
                result["posts"].append(post)

    wb.close()
    return result
