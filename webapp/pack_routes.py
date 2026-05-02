"""
Post-pack routes: browse and read per-founder Excel packs.

  GET   /api/admin/founders/{slug}/post-packs                → list available dates
  GET   /api/admin/founders/{slug}/post-packs/{date}         → parse Excel → JSON
  POST  /api/admin/founders/{slug}/post-packs/{date}/export-sheets → create Google Sheet
  POST  /api/admin/setup-google-key                          → one-time: upload service-account JSON
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from webapp.auth_routes import _require_admin

router = APIRouter(prefix="/api/admin/founders", tags=["admin-packs"])
setup_router = APIRouter(prefix="/api/admin", tags=["admin-setup"])
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


# ── Google Sheets export ──────────────────────────────────────────────────────

SA_FILE = Path("/etc/tagent/google-sa.json")
SHARE_WITH = "content@tagent.club"


class SheetsExportRequest(BaseModel):
    edits: dict[str, dict[str, str]] = {}


@router.post("/{slug}/post-packs/{date}/export-sheets")
async def export_to_sheets(slug: str, date: str, body: SheetsExportRequest, request: Request):
    _require_admin(request)

    if not SA_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Google Sheets not configured. Run deploy/setup_google.sh on the VPS first.",
        )

    try:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
    except ImportError:
        raise HTTPException(status_code=503, detail="google-api-python-client not installed. Run: pip install google-auth google-api-python-client")

    # Load the pack data (reuse existing logic)
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
        wb = openpyxl.load_workbook(target, read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not open Excel: {exc}")

    headers: list[str] = []
    rows: list[list[Any]] = []
    if "Posts" in wb.sheetnames:
        ws = wb["Posts"]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(c) if c is not None else f"col_{j}" for j, c in enumerate(row)]
            else:
                if all(v is None for v in row):
                    continue
                post: dict[str, Any] = {}
                for j, val in enumerate(row):
                    if j < len(headers):
                        post[headers[j]] = "" if val is None else (int(val) if isinstance(val, float) and val == int(val) else val)
                rows.append(post)
    wb.close()

    # Merge edits
    for row_dict in rows:
        row_id = str(row_dict.get("Row #", ""))
        if row_id in body.edits:
            for col_key, val in body.edits[row_id].items():
                if col_key in row_dict:
                    row_dict[col_key] = val

    # Build sheet values
    values = [headers] + [[str(r.get(h, "") or "") for h in headers] for r in rows]

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_file(str(SA_FILE), scopes=scopes)
        sheets_svc = build("sheets", "v4", credentials=creds)
        drive_svc  = build("drive",  "v3", credentials=creds)

        # Create spreadsheet
        title = f"{slug.replace('_', ' ').title()} — {date}"
        spreadsheet = sheets_svc.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Posts"}}],
        }).execute()
        sid = spreadsheet["spreadsheetId"]

        # Write data
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=sid,
            range="Posts!A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

        # Bold header row + freeze it
        sheets_svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
            {"repeatCell": {"range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}},
            {"updateSheetProperties": {"properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
        ]}).execute()

        # Share with content@tagent.club
        drive_svc.permissions().create(
            fileId=sid,
            body={"type": "user", "role": "writer", "emailAddress": SHARE_WITH},
            sendNotificationEmail=False,
        ).execute()

        url = f"https://docs.google.com/spreadsheets/d/{sid}"
        logger.info("Created Google Sheet %s for %s/%s", url, slug, date)
        return {"url": url}

    except Exception as exc:
        logger.exception("Google Sheets export failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sheets export failed: {exc}")


# ── One-time Google service account key upload ────────────────────────────────

@setup_router.post("/setup-google-key")
async def setup_google_key(request: Request, x_setup_token: str = Header(default="")):
    expected = os.environ.get("TAGENT_SETUP_TOKEN", "")
    if not expected or x_setup_token != expected:
        raise HTTPException(status_code=403, detail="invalid setup token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body must be valid JSON")

    if "type" not in body or body.get("type") != "service_account":
        raise HTTPException(status_code=400, detail="body must be a service_account JSON key")

    SA_FILE.parent.mkdir(parents=True, exist_ok=True)
    SA_FILE.write_text(json.dumps(body, indent=2))
    SA_FILE.chmod(0o600)
    try:
        import pwd
        uid = pwd.getpwnam("tagent").pw_uid
        gid = pwd.getpwnam("tagent").pw_gid
        os.chown(SA_FILE, uid, gid)
    except Exception:
        pass

    logger.info("Google service account key installed at %s", SA_FILE)
    return {"ok": True, "path": str(SA_FILE)}
