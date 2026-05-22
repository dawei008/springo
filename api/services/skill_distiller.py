"""
Skill Distiller — daily background job.

Walks every session under ~/.springo/sessions, asks Haiku (via skill_proposer)
whether each one contains a reusable pattern, and skips sessions whose
``modified`` timestamp hasn't changed since the previous distill run.

Companion to skill_proposer.propose_skill_from_session: that one fires from
memory_archiver as a session is wrapped up; this one runs once a day across
the *whole* corpus (so older sessions that pre-dated the proposer get a shot)
and additionally garbage-collects skills nobody actually uses.

State files (all under ~/.springo/skills/):
- _distill_state.json — { last_run, per_session: {sid: last_seen_modified_ms} }
- _usage.json         — { skill_name: { count, last_used } }  (written by skill_loader)
- _archive/           — auto-archived skills (auto-generated, 0 uses, > grace days)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(os.path.expanduser("~/.springo/skills"))
DISTILL_STATE_PATH = SKILLS_DIR / "_distill_state.json"
USAGE_PATH = SKILLS_DIR / "_usage.json"
ARCHIVE_DIR = SKILLS_DIR / "_archive"
SESSIONS_DIR = Path(os.path.expanduser("~/.springo/sessions"))

# Configuration knobs
DAILY_INTERVAL_SEC = 24 * 60 * 60      # one full pass per day
WAKE_INTERVAL_SEC = 6 * 60 * 60        # check every 6h whether 24h has passed
PER_SESSION_DELAY_SEC = 2.0            # courteous pacing between Haiku calls
PER_RUN_SESSION_CAP = 50               # max sessions per pass — protects budget
UNUSED_GRACE_DAYS = 14                 # auto-generated skills with 0 uses for this long → archive
MIN_SESSION_MESSAGE_COUNT = 4          # below this don't bother — too thin to extract a pattern


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state() -> Dict[str, Any]:
    if not DISTILL_STATE_PATH.exists():
        return {"last_run": None, "per_session": {}, "history": []}
    try:
        return json.loads(DISTILL_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("[Distiller] state file corrupt, resetting")
        return {"last_run": None, "per_session": {}, "history": []}


def _save_state(state: Dict[str, Any]) -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    DISTILL_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_usage() -> Dict[str, Dict[str, Any]]:
    if not USAGE_PATH.exists():
        return {}
    try:
        return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_usage(data: Dict[str, Dict[str, Any]]) -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_skill_use(skill_name: str) -> None:
    """Public entry: bump a skill's usage counter. Cheap; safe to call hot."""
    if not skill_name:
        return
    try:
        data = _load_usage()
        rec = data.get(skill_name, {"count": 0, "first_used": None, "last_used": None})
        rec["count"] = int(rec.get("count", 0)) + 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not rec.get("first_used"):
            rec["first_used"] = now
        rec["last_used"] = now
        data[skill_name] = rec
        _save_usage(data)
    except Exception as e:
        logger.debug(f"[Distiller] record_skill_use failed for {skill_name}: {e}")


# ---------------------------------------------------------------------------
# Session enumeration
# ---------------------------------------------------------------------------

def _list_session_files() -> List[Path]:
    if not SESSIONS_DIR.exists():
        return []
    out: List[Path] = []
    for sd in SESSIONS_DIR.iterdir():
        if not sd.is_dir():
            continue
        sf = sd / "session.jsonl"
        if not sf.exists():
            # Try legacy: session_<id>.jsonl in the workspace dir
            for child in sd.iterdir():
                if child.suffix == ".jsonl":
                    sf = child
                    break
        if sf.exists():
            out.append(sf)
    return out


def _build_transcript(session_path: Path) -> tuple[str, int]:
    """Return (transcript_text, message_count). Skips metadata lines."""
    parts: List[str] = []
    count = 0
    try:
        with session_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "metadata":
                    continue
                role = obj.get("role") or (obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}).get("role")
                content = obj.get("content")
                if content is None and isinstance(obj.get("message"), dict):
                    content = obj["message"].get("content")
                # Flatten content into plain text
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for blk in content:
                        if isinstance(blk, dict) and blk.get("type") == "text":
                            text += blk.get("text", "") + "\n"
                if not text.strip():
                    continue
                count += 1
                parts.append(f"{role or 'user'}: {text.strip()}")
                if sum(len(p) for p in parts) > 28000:
                    break
    except Exception as e:
        logger.debug(f"[Distiller] failed to read {session_path}: {e}")
    return "\n\n".join(parts), count


def _extract_session_id(session_path: Path) -> str:
    # session_path is ~/.springo/sessions/<sid>/session.jsonl
    return session_path.parent.name


# ---------------------------------------------------------------------------
# Garbage collection
# ---------------------------------------------------------------------------

def _list_active_skill_dirs() -> List[Path]:
    if not SKILLS_DIR.exists():
        return []
    out: List[Path] = []
    for child in SKILLS_DIR.iterdir():
        if child.is_dir() and not child.name.startswith(("_", ".")) and (child / "SKILL.md").exists():
            out.append(child)
    return out


def _is_user_edited(skill_dir: Path) -> bool:
    """Heuristic: user-edited if mtime is later than the directory's ctime by
    more than 60s, or if a ``.user_edited`` marker file exists. Keeps safety:
    any skill the user has actively touched is exempt from auto-archive."""
    marker = skill_dir / ".user_edited"
    if marker.exists():
        return True
    try:
        sm = (skill_dir / "SKILL.md").stat()
        return (sm.st_mtime - sm.st_ctime) > 60
    except FileNotFoundError:
        return False


def _archive_skill(skill_dir: Path, reason: str) -> Optional[Path]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVE_DIR / skill_dir.name
    if dest.exists():
        # Don't overwrite — append a timestamp.
        dest = ARCHIVE_DIR / f"{skill_dir.name}-{int(time.time())}"
    try:
        shutil.move(str(skill_dir), str(dest))
        # Drop a short note next to the archived skill for trace.
        (dest / ".archive_note.txt").write_text(
            f"archived_at={datetime.now(timezone.utc).isoformat(timespec='seconds')}\nreason={reason}\n",
            encoding="utf-8",
        )
        return dest
    except Exception as e:
        logger.warning(f"[Distiller] archive failed for {skill_dir.name}: {e}")
        return None


def _is_auto_generated(skill_dir: Path) -> bool:
    """Only skills written by skill_proposer.approve_proposal carry this
    marker. Plugin-installed and user-authored skills do NOT, so the GC
    pass leaves them alone."""
    return (skill_dir / ".auto_generated").exists()


def garbage_collect_unused_skills(grace_days: int = UNUSED_GRACE_DAYS) -> List[str]:
    """Auto-archive skills that meet ALL of:
      - `.auto_generated` marker present (created by the proposer flow)
      - no `.user_edited` opt-out marker
      - 0 usage records, or last use older than `grace_days`
      - older than `grace_days` since approval

    Plugin-installed skills and any skill the user has touched are exempt
    by virtue of lacking the `.auto_generated` marker. This is intentionally
    conservative: a wrongly-archived skill is irritating; a wrongly-kept
    skill is cheap context."""
    usage = _load_usage()
    now = datetime.now(timezone.utc).timestamp()
    archived: List[str] = []
    for d in _list_active_skill_dirs():
        if not _is_auto_generated(d):
            continue
        if _is_user_edited(d):
            continue
        slug = d.name
        try:
            approved_age_days = (now - (d / ".auto_generated").stat().st_ctime) / 86400.0
        except FileNotFoundError:
            continue
        if approved_age_days < grace_days:
            continue  # still within grace
        rec = usage.get(slug)
        if rec and int(rec.get("count", 0)) > 0:
            # Has been used at least once — only archive if last-use is
            # itself stale by `grace_days`.
            last = rec.get("last_used") or rec.get("first_used")
            try:
                last_ts = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp() if last else None
            except Exception:
                last_ts = None
            if last_ts and (now - last_ts) / 86400.0 < grace_days:
                continue
        # Otherwise: auto-generated, never (or stalely) used, past grace → archive.
        reason = (
            f"auto-generated, 0 uses for {approved_age_days:.1f}d (grace {grace_days}d)"
            if not rec or rec.get("count", 0) == 0
            else f"auto-generated, last use stale > {grace_days}d"
        )
        if _archive_skill(d, reason):
            archived.append(slug)
    return archived


# ---------------------------------------------------------------------------
# Distill pass
# ---------------------------------------------------------------------------

async def run_distill_pass(force: bool = False) -> Dict[str, Any]:
    """Walk all sessions, propose new skills for those whose modification time
    has advanced since their last seen mtime in state, and garbage-collect
    unused auto-generated skills. Returns a summary dict.

    `force=True` re-evaluates every session regardless of watermark. Useful for
    bootstrapping an existing corpus, or for a manual re-run.
    """
    state = _load_state()
    per_session: Dict[str, Any] = state.get("per_session", {}) or {}

    sessions = _list_session_files()
    started = time.time()
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sessions_total": len(sessions),
        "sessions_processed": 0,
        "sessions_skipped_unchanged": 0,
        "sessions_skipped_thin": 0,
        "proposals_created": 0,
        "errors": 0,
        "archived_skills": [],
    }

    # Import lazily so test environments without bedrock can still import this module.
    from .skill_proposer import propose_skill_from_session

    # Sort newest-first so a budget-capped run still covers fresh sessions.
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for session_path in sessions:
        if summary["sessions_processed"] >= PER_RUN_SESSION_CAP:
            logger.info(f"[Distiller] hit per-run cap {PER_RUN_SESSION_CAP}, stopping early")
            break

        sid = _extract_session_id(session_path)
        try:
            mtime_ms = int(session_path.stat().st_mtime * 1000)
        except FileNotFoundError:
            continue

        seen = per_session.get(sid, {}).get("last_modified_ms") if isinstance(per_session.get(sid), dict) else None
        if not force and seen is not None and seen >= mtime_ms:
            summary["sessions_skipped_unchanged"] += 1
            continue

        transcript, msg_count = _build_transcript(session_path)
        if msg_count < MIN_SESSION_MESSAGE_COUNT:
            summary["sessions_skipped_thin"] += 1
            per_session[sid] = {"last_modified_ms": mtime_ms, "skipped": "thin"}
            continue

        try:
            proposal = await propose_skill_from_session(sid, transcript)
            summary["sessions_processed"] += 1
            if proposal is not None:
                summary["proposals_created"] += 1
            per_session[sid] = {
                "last_modified_ms": mtime_ms,
                "last_processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "yielded_proposal": proposal is not None,
            }
        except Exception as e:
            logger.warning(f"[Distiller] session {sid} failed: {e}")
            summary["errors"] += 1
            # Don't update watermark on error so we retry next pass.
        # Pace ourselves so we don't hammer Haiku in a tight loop.
        await asyncio.sleep(PER_SESSION_DELAY_SEC)

    # GC pass — runs every distill regardless of how many sessions we touched.
    try:
        archived = garbage_collect_unused_skills()
        summary["archived_skills"] = archived
    except Exception as e:
        logger.warning(f"[Distiller] GC failed: {e}")

    summary["elapsed_sec"] = round(time.time() - started, 2)
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    state["last_run"] = summary["finished_at"]
    state["per_session"] = per_session
    history = state.get("history") or []
    history.append({k: summary[k] for k in (
        "finished_at", "sessions_total", "sessions_processed",
        "sessions_skipped_unchanged", "proposals_created", "archived_skills", "errors",
    )})
    # Cap history to last 60 runs (~2 months).
    state["history"] = history[-60:]
    _save_state(state)

    logger.info(
        f"[Distiller] done: processed {summary['sessions_processed']}, "
        f"proposals {summary['proposals_created']}, "
        f"skipped {summary['sessions_skipped_unchanged']}, "
        f"archived {len(summary['archived_skills'])}"
    )
    return summary


def get_status() -> Dict[str, Any]:
    state = _load_state()
    usage = _load_usage()
    return {
        "last_run": state.get("last_run"),
        "history": state.get("history", [])[-10:],
        "tracked_skills": len(usage),
        "active_skills": len(_list_active_skill_dirs()),
        "archived_skills_total": len([d for d in ARCHIVE_DIR.iterdir() if d.is_dir()]) if ARCHIVE_DIR.exists() else 0,
    }


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

_loop_task: Optional[asyncio.Task] = None


async def _background_loop() -> None:
    """Wake every WAKE_INTERVAL_SEC; if 24h has elapsed since the last run,
    fire a distill pass. The first iteration delays by WAKE_INTERVAL_SEC so
    we don't pile work onto app startup."""
    while True:
        try:
            await asyncio.sleep(WAKE_INTERVAL_SEC)
            state = _load_state()
            last = state.get("last_run")
            should_run = True
            if last:
                try:
                    last_ts = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
                    should_run = (time.time() - last_ts) >= DAILY_INTERVAL_SEC
                except Exception:
                    pass
            if should_run:
                logger.info("[Distiller] daily pass triggered by background loop")
                await run_distill_pass()
        except asyncio.CancelledError:
            logger.info("[Distiller] background loop cancelled")
            return
        except Exception as e:
            logger.warning(f"[Distiller] background loop iteration failed: {e}")


def start_background_loop() -> None:
    """Idempotent: ensure the daily distill loop is running."""
    global _loop_task
    if _loop_task and not _loop_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _loop_task = loop.create_task(_background_loop())
        logger.info("[Distiller] background loop started")
    except RuntimeError as e:
        logger.warning(f"[Distiller] couldn't start loop (no running event loop?): {e}")


def stop_background_loop() -> None:
    global _loop_task
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        _loop_task = None
