"""
ACP Tasks: named long-running conversations with an external ACP agent.

Each task pairs a human-friendly name (e.g. ``obo-demo``) with:
  - the agent it talks to (``agent_name``)
  - the agent-side session id (so prompts continue the same thread)
  - the springo chat session that spawned it (so we know what main-chat
    context to forward to the agent on each turn)

Tasks persist to ``~/.springo/acp_tasks.json``. The chat UI uses them to
render an ``@task-name`` mention picker that resumes existing threads, vs
``@agent-name`` which starts a fresh thread bound to that agent.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TASKS_FILE = Path(os.path.expanduser("~/.springo/acp_tasks.json"))
_lock = threading.Lock()
_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _load() -> Dict[str, Dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache
    if not _TASKS_FILE.exists():
        _cache = {}
        return _cache
    try:
        with _TASKS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _cache = data.get("tasks", {}) if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read {_TASKS_FILE}: {e}")
        _cache = {}
    return _cache


def _flush() -> None:
    """Atomic write of the in-memory cache to disk."""
    if _cache is None:
        return
    _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TASKS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"tasks": _cache}, f, indent=2, ensure_ascii=False)
    tmp.replace(_TASKS_FILE)


def list_tasks() -> List[Dict[str, Any]]:
    """All tasks, sorted by ``last_active`` desc."""
    with _lock:
        tasks = list(_load().values())
    tasks.sort(key=lambda t: t.get("last_active", 0), reverse=True)
    return tasks


def get_task(name: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _load().get(name)


def upsert_task(
    name: str,
    *,
    agent_name: str,
    agent_session_id: Optional[str] = None,
    springo_session_id: Optional[str] = None,
    description: str = "",
    cwd: str = "",
) -> Dict[str, Any]:
    """Create or update a task. Caller-provided fields are merged onto any
    existing entry; ``last_active`` is bumped on every call."""
    with _lock:
        tasks = _load()
        now = time.time()
        existing = tasks.get(name) or {}
        task = {
            **existing,
            "name": name,
            "agent_name": agent_name,
            "description": description or existing.get("description", ""),
            "cwd": cwd or existing.get("cwd", ""),
            "created": existing.get("created", now),
            "last_active": now,
        }
        if agent_session_id:
            task["agent_session_id"] = agent_session_id
        elif "agent_session_id" not in task:
            task["agent_session_id"] = None
        if springo_session_id:
            task["springo_session_id"] = springo_session_id
        elif "springo_session_id" not in task:
            task["springo_session_id"] = None
        tasks[name] = task
        _flush()
        return dict(task)


def touch_task(name: str, *, agent_session_id: Optional[str] = None) -> None:
    """Bump ``last_active`` (and optionally agent_session_id) on an existing task."""
    with _lock:
        tasks = _load()
        if name not in tasks:
            return
        tasks[name]["last_active"] = time.time()
        if agent_session_id:
            tasks[name]["agent_session_id"] = agent_session_id
        _flush()


def delete_task(name: str) -> bool:
    with _lock:
        tasks = _load()
        if name not in tasks:
            return False
        tasks.pop(name)
        _flush()
        return True
