"""
Folders store — single-level grouping for sessions.

Persists to ``~/.springo/folders.json`` as ``[{"id","name","createdAt"}]``.
Folder ↔ session is a soft 1:N relation: each session row stores a nullable
``folder_id``; deleting a folder doesn't touch the sessions, callers must
null out the field via the sessions API. Inspired by Quick's
``session_folders`` SQLite table — single-level, no parent pointer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings

logger = logging.getLogger(__name__)


def _folders_path() -> Path:
    return settings.springo_config_path / "folders.json"


_lock = asyncio.Lock()


def _read_all() -> List[Dict[str, Any]]:
    p = _folders_path()
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except json.JSONDecodeError as e:
        logger.warning(f"folders.json malformed, treating as empty: {e}")
        return []


def _write_all(items: List[Dict[str, Any]]) -> None:
    p = _folders_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp-{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def _is_safe_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    s = name.strip()
    if len(s) == 0 or len(s) > 80:
        return False
    return True


async def list_folders() -> List[Dict[str, Any]]:
    async with _lock:
        return list(_read_all())


async def create_folder(name: str) -> Dict[str, Any]:
    if not _is_safe_name(name):
        raise ValueError("Folder name must be 1–80 characters")
    async with _lock:
        items = _read_all()
        # Reject duplicate names (case-insensitive) — simpler UX, matches Quick.
        norm = name.strip().lower()
        if any(f.get("name", "").strip().lower() == norm for f in items):
            raise ValueError("A folder with this name already exists")
        folder = {
            "id": f"fld-{uuid.uuid4().hex[:10]}",
            "name": name.strip(),
            "createdAt": int(time.time() * 1000),
        }
        items.append(folder)
        _write_all(items)
        return folder


async def rename_folder(folder_id: str, name: str) -> Dict[str, Any]:
    if not _is_safe_name(name):
        raise ValueError("Folder name must be 1–80 characters")
    async with _lock:
        items = _read_all()
        target = next((f for f in items if f.get("id") == folder_id), None)
        if not target:
            raise FileNotFoundError(f"Folder not found: {folder_id}")
        norm = name.strip().lower()
        # Disallow rename collision with a *different* folder.
        if any(
            f.get("id") != folder_id
            and f.get("name", "").strip().lower() == norm
            for f in items
        ):
            raise ValueError("A folder with this name already exists")
        target["name"] = name.strip()
        _write_all(items)
        return target


async def delete_folder(folder_id: str) -> bool:
    async with _lock:
        items = _read_all()
        before = len(items)
        items = [f for f in items if f.get("id") != folder_id]
        if len(items) == before:
            return False
        _write_all(items)
        return True
