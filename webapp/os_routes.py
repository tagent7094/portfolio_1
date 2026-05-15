"""OS management API for os.tagent.club — file browser, terminal, logs, stats.

All endpoints require admin auth. File operations are sandboxed to /opt/tagent
and /var/log. The backend runs on the VPS itself, so commands execute locally.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import re
import shutil
import signal
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from webapp.auth_routes import _require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/os", tags=["os"])

# ── Path sandboxing ──

_ALLOWED_READ_ROOTS = [Path("/opt/tagent"), Path("/var/log")]
_ALLOWED_WRITE_ROOTS = [Path("/opt/tagent")]
_SENSITIVE_PATTERNS = re.compile(r"(\.env|auth\.yaml|-auth\.yaml|jwt.secret|jwt-secret)", re.IGNORECASE)

_IS_LINUX = platform.system() == "Linux"


def _validate_path(p: str, *, writable: bool = False) -> Path:
    resolved = Path(p).resolve()
    roots = _ALLOWED_WRITE_ROOTS if writable else _ALLOWED_READ_ROOTS
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(status_code=403, detail=f"Access denied: {p}")
    if writable and _SENSITIVE_PATTERNS.search(resolved.name):
        raise HTTPException(status_code=403, detail=f"Cannot write to sensitive file: {resolved.name}")
    return resolved


async def _run(cmd: list[str], timeout: float = 30) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail="Command timed out")
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=stderr.decode(errors="replace")[:500])
    return stdout.decode(errors="replace")


# ── System Stats ──

@router.get("/stats")
async def get_stats(request: Request):
    _require_admin(request)
    if not _IS_LINUX:
        return {"error": "Stats only available on Linux"}

    results = await asyncio.gather(
        _run(["hostname"]),
        _run(["uptime", "-p"]),
        _run(["cat", "/proc/loadavg"]),
        _run(["free", "-b"]),
        _run(["df", "-B1", "--output=target,size,used,avail,pcent"]),
    )
    hostname = results[0].strip()
    uptime = results[1].strip()
    loadavg_parts = results[2].strip().split()
    load_1, load_5, load_15 = loadavg_parts[0], loadavg_parts[1], loadavg_parts[2]

    mem_lines = results[3].strip().split("\n")
    mem_parts = mem_lines[1].split()
    mem_total = int(mem_parts[1])
    mem_used = int(mem_parts[2])

    disks = []
    for line in results[4].strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 5:
            disks.append({
                "mount": parts[0],
                "total": int(parts[1]),
                "used": int(parts[2]),
                "available": int(parts[3]),
                "percent": parts[4],
            })

    cpu_pct = 0.0
    try:
        top_out = await _run(["top", "-bn1", "-w", "512"])
        for line in top_out.split("\n"):
            if "Cpu(s)" in line or "%Cpu" in line:
                idle_match = re.search(r"([\d.]+)\s*id", line)
                if idle_match:
                    cpu_pct = round(100.0 - float(idle_match.group(1)), 1)
                break
    except Exception:
        pass

    return {
        "hostname": hostname,
        "uptime": uptime,
        "load": {"1m": float(load_1), "5m": float(load_5), "15m": float(load_15)},
        "cpu_percent": cpu_pct,
        "memory": {"total": mem_total, "used": mem_used, "percent": round(mem_used / mem_total * 100, 1) if mem_total else 0},
        "disks": disks,
    }


# ── Processes ──

@router.get("/processes")
async def get_processes(request: Request):
    _require_admin(request)
    if not _IS_LINUX:
        return {"processes": []}
    out = await _run(["ps", "aux", "--sort=-%mem"])
    processes = []
    for line in out.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append({
                "user": parts[0],
                "pid": int(parts[1]),
                "cpu": float(parts[2]),
                "mem": float(parts[3]),
                "vsz": int(parts[4]),
                "rss": int(parts[5]),
                "stat": parts[7],
                "start": parts[8],
                "time": parts[9],
                "command": parts[10],
            })
    return {"processes": processes}


class KillRequest(BaseModel):
    signal: str = "TERM"


@router.post("/processes/{pid}/kill")
async def kill_process(pid: int, request: Request, body: KillRequest = KillRequest()):
    _require_admin(request)
    if pid <= 1:
        raise HTTPException(status_code=403, detail="Cannot kill PID 0 or 1")
    sig_map = {"TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "HUP": signal.SIGHUP}
    sig = sig_map.get(body.signal.upper())
    if not sig:
        raise HTTPException(status_code=400, detail=f"Unknown signal: {body.signal}")
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail=f"Process {pid} not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied killing PID {pid}")
    return {"ok": True, "pid": pid, "signal": body.signal}


# ── File Browser ──

@router.get("/files")
async def list_files(request: Request, path: str = Query("/opt/tagent")):
    _require_admin(request)
    resolved = _validate_path(path)
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    entries = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                st = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": st.st_size if not entry.is_dir() else None,
                    "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    "permissions": stat.filemode(st.st_mode),
                })
            except (PermissionError, OSError):
                entries.append({"name": entry.name, "type": "unknown", "size": None, "modified": None, "permissions": None})
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    return {"path": str(resolved), "entries": entries}


@router.get("/files/read")
async def read_file(request: Request, path: str = Query(...), offset: int = Query(0), limit: int = Query(500)):
    _require_admin(request)
    resolved = _validate_path(path)
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    size = resolved.stat().st_size
    is_binary = False
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
        total_lines = len(lines)
        content = "".join(lines[offset:offset + limit])
    except UnicodeDecodeError:
        is_binary = True
        with open(resolved, "rb") as f:
            raw = f.read(min(size, 1024 * 1024))
        content = base64.b64encode(raw).decode()
        total_lines = 0
    return {
        "path": str(resolved),
        "size": size,
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "is_binary": is_binary,
        "content": content,
    }


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.put("/files/write")
async def write_file(request: Request, body: FileWriteRequest):
    _require_admin(request)
    resolved = _validate_path(body.path, writable=True)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(body.content, encoding="utf-8")
    return {"ok": True, "path": str(resolved), "size": resolved.stat().st_size}


class FileActionRequest(BaseModel):
    action: str  # mkdir, delete, rename, copy, move
    path: str
    dest: Optional[str] = None


@router.post("/files/action")
async def file_action(request: Request, body: FileActionRequest):
    _require_admin(request)
    resolved = _validate_path(body.path, writable=True)
    if body.action == "mkdir":
        resolved.mkdir(parents=True, exist_ok=True)
    elif body.action == "delete":
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
    elif body.action in ("rename", "move"):
        if not body.dest:
            raise HTTPException(status_code=400, detail="dest required")
        dest = _validate_path(body.dest, writable=True)
        shutil.move(str(resolved), str(dest))
    elif body.action == "copy":
        if not body.dest:
            raise HTTPException(status_code=400, detail="dest required")
        dest = _validate_path(body.dest, writable=True)
        if resolved.is_dir():
            shutil.copytree(str(resolved), str(dest))
        else:
            shutil.copy2(str(resolved), str(dest))
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
    return {"ok": True, "action": body.action, "path": str(resolved)}


@router.post("/files/upload")
async def upload_file(request: Request, path: str = Query(...), file: UploadFile = File(...)):
    _require_admin(request)
    dest_dir = _validate_path(path, writable=True)
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="Destination is not a directory")
    dest_file = dest_dir / file.filename
    if _SENSITIVE_PATTERNS.search(file.filename):
        raise HTTPException(status_code=403, detail=f"Cannot upload sensitive file: {file.filename}")
    content = await file.read()
    dest_file.write_bytes(content)
    return {"ok": True, "path": str(dest_file), "size": len(content)}


# ── Logs ──

_ALLOWED_LOG_FILES = {
    "tagent": "/opt/tagent/error.log",
    "nginx-access": "/var/log/nginx/access.log",
    "nginx-error": "/var/log/nginx/error.log",
    "syslog": "/var/log/syslog",
}


@router.get("/logs/stream")
async def stream_log(request: Request, file: str = Query("tagent"), lines: int = Query(100)):
    _require_admin(request)
    log_path = _ALLOWED_LOG_FILES.get(file)
    if not log_path:
        raise HTTPException(status_code=400, detail=f"Unknown log: {file}. Allowed: {list(_ALLOWED_LOG_FILES.keys())}")
    if not Path(log_path).exists():
        raise HTTPException(status_code=404, detail=f"Log file not found: {log_path}")

    async def generate():
        proc = await asyncio.create_subprocess_exec(
            "tail", "-n", str(lines), "-f", log_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            while True:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
                if not line:
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                    continue
                yield f"data: {json.dumps({'type': 'line', 'text': line.decode(errors='replace').rstrip()})}\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            proc.kill()
            await proc.wait()

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.get("/logs/search")
async def search_logs(request: Request, file: str = Query("tagent"), q: str = Query(...), lines: int = Query(1000)):
    _require_admin(request)
    log_path = _ALLOWED_LOG_FILES.get(file)
    if not log_path:
        raise HTTPException(status_code=400, detail=f"Unknown log: {file}")
    if not Path(log_path).exists():
        raise HTTPException(status_code=404, detail=f"Log file not found: {log_path}")
    out = await _run(["grep", "-n", "-i", "--color=never", "-m", str(lines), q, log_path], timeout=15)
    matches = []
    for line in out.strip().split("\n"):
        if ":" in line:
            num, text = line.split(":", 1)
            matches.append({"line": int(num), "text": text})
    return {"file": file, "query": q, "matches": matches}


# ── Services ──

_MANAGED_SERVICES = ["tagent", "nginx"]


@router.get("/services")
async def list_services(request: Request):
    _require_admin(request)
    if not _IS_LINUX:
        return {"services": []}
    services = []
    for name in _MANAGED_SERVICES:
        try:
            out = await _run(["systemctl", "show", name, "--property=ActiveState,SubState,MainPID"])
            props = dict(line.split("=", 1) for line in out.strip().split("\n") if "=" in line)
            services.append({
                "name": name,
                "active": props.get("ActiveState", "unknown"),
                "sub": props.get("SubState", "unknown"),
                "pid": int(props.get("MainPID", "0")),
            })
        except Exception:
            services.append({"name": name, "active": "error", "sub": "error", "pid": 0})
    return {"services": services}


class ServiceActionRequest(BaseModel):
    action: str  # start, stop, restart


@router.post("/services/{name}/action")
async def service_action(name: str, request: Request, body: ServiceActionRequest):
    _require_admin(request)
    if name not in _MANAGED_SERVICES:
        raise HTTPException(status_code=400, detail=f"Unknown service: {name}")
    if body.action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
    await _run(["systemctl", body.action, name], timeout=30)
    return {"ok": True, "service": name, "action": body.action}


# ── Journal / LLM logs ──

@router.get("/logs/journal")
async def get_journal(request: Request, unit: str = Query("tagent"), lines: int = Query(200)):
    _require_admin(request)
    if unit not in _MANAGED_SERVICES:
        raise HTTPException(status_code=400, detail=f"Unknown unit: {unit}")
    out = await _run(["journalctl", "-u", unit, "-n", str(min(lines, 2000)), "--no-pager", "-o", "short-iso"])
    return {"unit": unit, "lines": out.strip().split("\n")}


# ── WebSocket Terminal ──

@router.websocket("/terminal")
async def websocket_terminal(ws: WebSocket):
    # Validate admin auth from cookie
    token = ws.cookies.get("admin_token", "")
    if os.environ.get("TAGENT_AUTH_ENABLED", "").lower() in ("1", "true", "yes"):
        from src.auth.tokens import decode_token
        claims = decode_token(token)
        if not claims or claims.get("sub") != "admin":
            await ws.close(code=4001, reason="admin authentication required")
            return

    await ws.accept()
    logger.info("[os-terminal] WebSocket connected")

    import pty
    import select
    import struct
    import termios
    import fcntl

    master_fd, slave_fd = pty.openpty()
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "--login",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)

    os.set_blocking(master_fd, False)

    async def read_pty():
        loop = asyncio.get_event_loop()
        try:
            while True:
                await loop.run_in_executor(None, lambda: select.select([master_fd], [], [], 0.1))
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        await ws.send_bytes(data)
                except OSError:
                    break
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass

    read_task = asyncio.create_task(read_pty())

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "bytes" in msg:
                os.write(master_fd, msg["bytes"])
            elif "text" in msg:
                text = msg["text"]
                if text.startswith('{"type":"resize"'):
                    try:
                        data = json.loads(text)
                        rows = data.get("rows", 24)
                        cols = data.get("cols", 80)
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    except Exception:
                        pass
                else:
                    os.write(master_fd, text.encode())
    except WebSocketDisconnect:
        pass
    finally:
        read_task.cancel()
        try:
            os.close(master_fd)
        except OSError:
            pass
        proc.kill()
        await proc.wait()
        logger.info("[os-terminal] WebSocket disconnected")
