"""
Meeting Notes persistence — saves transcripts to ~/.springo/meetings/.

Each meeting is one Markdown file named by timestamp + session id, so a
recording is never lost when the panel is cleared or the app restarts.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

MEETINGS_ROOT = Path.home() / ".springo" / "meetings"


def _ensure_root() -> None:
    MEETINGS_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_session(session_id: str) -> str:
    """Keep only filename-safe chars so session_id can't escape the dir."""
    return re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:80] or "session"


class SaveMeetingIn(BaseModel):
    session_id: str = Field(..., description="Springo session the meeting belongs to")
    transcript: str = Field(..., description="Full transcript text")
    title: Optional[str] = Field(default=None, description="Optional human title")
    language: Optional[str] = Field(default=None, description="Transcription language")


@router.post("/meetings/save")
async def save_meeting(payload: SaveMeetingIn) -> Dict[str, Any]:
    """Persist (or overwrite) a meeting transcript for a session.

    One file per session — re-saving the same session updates the file in
    place so the latest transcript wins. Empty transcripts are ignored.
    """
    text = (payload.transcript or "").strip()
    if not text:
        return {"saved": False, "reason": "empty transcript"}

    _ensure_root()
    safe = _safe_session(payload.session_id)
    path = MEETINGS_ROOT / f"{safe}.md"

    now = datetime.now(timezone.utc).astimezone()
    title = (payload.title or "").strip() or f"Meeting {now.strftime('%Y-%m-%d %H:%M')}"

    front = [
        "---",
        f"title: {title}",
        f"session_id: {payload.session_id}",
        f"language: {payload.language or 'auto'}",
        f"saved_at: {now.isoformat(timespec='seconds')}",
        "---",
        "",
        text,
        "",
    ]
    try:
        path.write_text("\n".join(front), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save meeting {safe}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Saved meeting transcript: {path} ({len(text)} chars)")
    return {"saved": True, "path": str(path), "bytes": path.stat().st_size}


@router.get("/meetings")
async def list_meetings() -> Dict[str, Any]:
    """List saved meetings, newest first, with metadata + preview."""
    _ensure_root()
    items: List[Dict[str, Any]] = []
    for f in MEETINGS_ROOT.glob("*.md"):
        try:
            raw = f.read_text(encoding="utf-8")
        except Exception:
            continue
        meta: Dict[str, str] = {}
        body = raw
        if raw.startswith("---"):
            end = raw.find("\n---", 3)
            if end != -1:
                for line in raw[3:end].strip().splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip()
                body = raw[end + 4 :].strip()
        items.append({
            "file": f.name,
            "session_id": meta.get("session_id", f.stem),
            "title": meta.get("title", f.stem),
            "language": meta.get("language", "auto"),
            "saved_at": meta.get("saved_at"),
            "preview": body[:200],
            "bytes": f.stat().st_size,
        })
    items.sort(key=lambda x: x.get("saved_at") or "", reverse=True)
    return {"meetings": items, "total": len(items)}


@router.get("/meetings/{session_id}")
async def get_meeting(session_id: str) -> Dict[str, Any]:
    """Return the full saved transcript for a session, if any."""
    _ensure_root()
    safe = _safe_session(session_id)
    path = MEETINGS_ROOT / f"{safe}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No saved meeting for this session")
    return {"session_id": session_id, "content": path.read_text(encoding="utf-8")}
