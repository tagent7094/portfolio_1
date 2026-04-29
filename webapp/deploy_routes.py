"""
Deploy webhook — called by GitHub Actions instead of SSH.
POST /api/deploy  with  X-Deploy-Secret: <DEPLOY_SECRET env var>

Returns 202 immediately. The webhook writes a trigger file at
/opt/tagent/data/deploy.trigger; a root-owned systemd path unit
(tagent-deploy.path) watches that file and runs ci-deploy.sh as root.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

TRIGGER_FILE = Path("/opt/tagent/data/deploy.trigger")


@router.post("/api/deploy", status_code=202)
async def webhook_deploy(x_deploy_secret: str | None = Header(default=None)):
    expected = os.environ.get("DEPLOY_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="deploy not configured")
    if x_deploy_secret != expected:
        raise HTTPException(status_code=401, detail="invalid secret")

    try:
        TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRIGGER_FILE.touch()
        logger.info("[deploy] trigger file written — systemd will run ci-deploy.sh")
    except Exception as exc:
        logger.error("[deploy] failed to write trigger file: %s", exc)
        raise HTTPException(status_code=500, detail="could not write trigger file")

    return {"status": "deploying"}
