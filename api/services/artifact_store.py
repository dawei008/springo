"""
Artifact Store — filesystem-backed persistence for Canvas artifacts.

Layout on disk (~/.springo/artifacts/):
    art-<id>/
        _meta.json           meta: {id, name, type, icon, createdAt, updatedAt,
                                   pinnedBy:[sessionId...], version, sessionId}
        files/               current files (index.html, App.jsx, ...)
        state.json           latest runtime state pushed by the iframe
        versions/
            v001-<iso>/      snapshot of files/ at each patch
            v002-<iso>/
            ...

Design principles:
- Plain files. `ls`, `rm -rf`, `cat`, git — all Just Work.
- Schema is the directory layout itself; no migrations needed to introspect.
- Writes are coarse (dump JSON for meta, write every file for a patch).
- No cross-process locking yet — single-user local app. We pay attention to
  atomic rename only where partial writes would corrupt state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ARTIFACTS_ROOT = Path(os.path.expanduser("~/.springo/artifacts"))
MAX_VERSIONS = 50  # keep the last N versions; older ones are pruned


def _ensure_root() -> None:
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)


def _artifact_dir(artifact_id: str) -> Path:
    _validate_id(artifact_id)
    return ARTIFACTS_ROOT / artifact_id


def _validate_id(artifact_id: str) -> None:
    if not artifact_id or not re.fullmatch(r"[A-Za-z0-9_\-]+", artifact_id):
        raise ValueError(f"Invalid artifact id: {artifact_id!r}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# File type inference (matches frontend)
# ---------------------------------------------------------------------------

_TYPE_BY_EXT = {
    "html": "html", "htm": "html",
    "jsx": "jsx", "tsx": "jsx",
    "css": "css",
    "json": "json",
}

def _infer_file_type(path: str, explicit: Optional[str] = None) -> str:
    if explicit:
        for key in ("html", "jsx", "css", "json"):
            if key in explicit:
                return key
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _TYPE_BY_EXT.get(ext, "text")


# ---------------------------------------------------------------------------
# Meta schema helpers
# ---------------------------------------------------------------------------

def _default_meta(artifact_id: str, name: str, artifact_type: str, icon: str,
                  session_id: Optional[str]) -> Dict[str, Any]:
    now = _now_ms()
    return {
        "id": artifact_id,
        "name": name,
        "type": artifact_type,
        "icon": icon,
        "createdAt": now,
        "updatedAt": now,
        "version": 1,
        "sessionId": session_id,
        "pinnedBy": [],
        "pinned": False,
    }


def _read_meta(artifact_id: str) -> Dict[str, Any]:
    path = _artifact_dir(artifact_id) / "_meta.json"
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_id}")
    return json.loads(path.read_text("utf-8"))


def _write_meta(artifact_id: str, meta: Dict[str, Any]) -> None:
    meta["updatedAt"] = _now_ms()
    _atomic_write_json(_artifact_dir(artifact_id) / "_meta.json", meta)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_artifacts(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all artifacts; optionally filter to those pinned by a session."""
    _ensure_root()
    out: List[Dict[str, Any]] = []
    for d in sorted(ARTIFACTS_ROOT.iterdir()):
        if not d.is_dir() or not (d / "_meta.json").exists():
            continue
        try:
            meta = json.loads((d / "_meta.json").read_text("utf-8"))
        except Exception:
            continue
        if session_id and session_id not in meta.get("pinnedBy", []) and meta.get("sessionId") != session_id:
            continue
        file_count = len(list((d / "files").iterdir())) if (d / "files").exists() else 0
        out.append({
            "id": meta["id"],
            "name": meta.get("name", "Artifact"),
            "type": meta.get("type", "document"),
            "icon": meta.get("icon", "box"),
            "version": meta.get("version", 1),
            "pinned": meta.get("pinned", False),
            "pinnedBy": meta.get("pinnedBy", []),
            "sessionId": meta.get("sessionId"),
            "fileCount": file_count,
            "createdAt": meta.get("createdAt"),
            "updatedAt": meta.get("updatedAt"),
        })
    return out


def read_artifact(artifact_id: str) -> Dict[str, Any]:
    """Return full artifact: meta + files + state + version list."""
    meta = _read_meta(artifact_id)
    files = read_files(artifact_id)
    state = read_state(artifact_id)
    versions = list_versions(artifact_id)
    return {
        **meta,
        "files": files,
        "state": state,
        "versions": versions,
    }


def read_files(artifact_id: str) -> List[Dict[str, Any]]:
    """Return list of {path, type, content} for the current version.

    Walks the files/ tree recursively so nested paths (e.g.
    ``components/Button.jsx``) round-trip through the API.
    """
    d = _artifact_dir(artifact_id) / "files"
    if not d.exists():
        return []
    out: List[Dict[str, Any]] = []
    for f in sorted(d.rglob("*")):
        if f.is_file():
            rel = f.relative_to(d).as_posix()
            out.append({
                "path": rel,
                "type": _infer_file_type(rel),
                "content": f.read_text("utf-8"),
            })
    return out


def _resolve_file_path(artifact_id: str, path: str) -> Path:
    """Validate ``path`` and resolve it under the artifact's ``files/`` dir.

    Raises ValueError on traversal attempts or paths that escape the dir.
    Does NOT check existence — callers should follow with their own check.
    """
    if ".." in path.split("/"):
        raise ValueError(f"Unsafe file path: {path!r}")
    files_root = (_artifact_dir(artifact_id) / "files").resolve()
    target = (files_root / path).resolve()
    if files_root not in target.parents and target != files_root:
        raise ValueError(f"Path escapes artifact files dir: {path!r}")
    return target


def read_file(artifact_id: str, path: str) -> Dict[str, Any]:
    """Return a single file's content. Nested paths permitted under files/."""
    f = _resolve_file_path(artifact_id, path)
    if not f.exists():
        raise FileNotFoundError(f"File not found in {artifact_id}: {path}")
    return {
        "path": path,
        "type": _infer_file_type(path),
        "content": f.read_text("utf-8"),
    }


def read_state(artifact_id: str) -> Dict[str, Any]:
    """Return the latest runtime state (iframe → host)."""
    f = _artifact_dir(artifact_id) / "state.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except Exception:
        return {}


def save_state(artifact_id: str, state: Dict[str, Any]) -> None:
    """Persist iframe runtime state. Idempotent & overwriting."""
    _read_meta(artifact_id)  # raises if missing
    _atomic_write_json(_artifact_dir(artifact_id) / "state.json", state)


def list_versions(artifact_id: str) -> List[Dict[str, Any]]:
    """Return version stub list (newest last), without file contents."""
    vdir = _artifact_dir(artifact_id) / "versions"
    if not vdir.exists():
        return []
    out: List[Dict[str, Any]] = []
    for v in sorted(vdir.iterdir()):
        if not v.is_dir():
            continue
        out.append({
            "id": v.name,
            "createdAt": _parse_version_timestamp(v.name),
            "fileCount": len(list(v.iterdir())) if v.is_dir() else 0,
        })
    return out


def _parse_version_timestamp(vdir_name: str) -> Optional[int]:
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", vdir_name)
    if not m:
        return None
    dt = datetime.strptime(m.group(1), "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def read_version_file(artifact_id: str, version_id: str, path: str) -> Dict[str, Any]:
    """Read a file from a historical version (nested paths allowed)."""
    if "/" in version_id or ".." in version_id.split("/"):
        raise ValueError("Unsafe version id")
    if ".." in path.split("/"):
        raise ValueError("Unsafe file path")
    vroot = _artifact_dir(artifact_id) / "versions" / version_id
    vpath = (vroot / path).resolve()
    if vroot.resolve() not in vpath.parents and vpath != vroot:
        raise ValueError("Path escapes version dir")
    if not vpath.exists():
        raise FileNotFoundError(f"Version file not found: {artifact_id}/{version_id}/{path}")
    return {
        "path": path,
        "type": _infer_file_type(path),
        "content": vpath.read_text("utf-8"),
    }


def read_version_files(artifact_id: str, version_id: str) -> List[Dict[str, Any]]:
    """Return all files in a historical version, recursively."""
    if "/" in version_id or ".." in version_id.split("/"):
        raise ValueError("Unsafe version id")
    vdir = _artifact_dir(artifact_id) / "versions" / version_id
    if not vdir.exists():
        raise FileNotFoundError(f"Version not found: {artifact_id}/{version_id}")
    out: List[Dict[str, Any]] = []
    for f in sorted(vdir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(vdir).as_posix()
            out.append({
                "path": rel,
                "type": _infer_file_type(rel),
                "content": f.read_text("utf-8"),
            })
    return out


def create_artifact(
    name: str,
    artifact_type: str,
    icon: str,
    files: List[Dict[str, Any]],
    artifact_id: Optional[str] = None,
    session_id: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new artifact on disk."""
    _ensure_root()
    if not artifact_id:
        artifact_id = f"art-{_now_ms()}-{os.urandom(3).hex()}"
    _validate_id(artifact_id)

    d = _artifact_dir(artifact_id)
    if d.exists():
        raise FileExistsError(f"Artifact already exists: {artifact_id}")

    d.mkdir(parents=True)
    (d / "files").mkdir()
    (d / "versions").mkdir()

    # Write files/
    for f in files:
        _write_artifact_file(d / "files" / f["path"], f.get("content", ""))

    # Snapshot as v001
    _write_version_snapshot(d, files)

    # Write meta + state
    meta = _default_meta(artifact_id, name, artifact_type, icon, session_id)
    _write_meta(artifact_id, meta)
    if state:
        _atomic_write_json(d / "state.json", state)

    logger.info(f"[artifacts] created {artifact_id} ({len(files)} files)")
    return read_artifact(artifact_id)


def apply_patch(artifact_id: str, file_patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply replace/create/delete ops, bump version, snapshot new state."""
    meta = _read_meta(artifact_id)
    d = _artifact_dir(artifact_id)
    fdir = d / "files"

    for p in file_patches:
        path = p["path"]
        action = p.get("action", "replace")
        if ".." in path.split("/"):
            raise ValueError(f"Unsafe file path: {path!r}")
        target = (fdir / path).resolve()
        if fdir.resolve() not in target.parents:
            raise ValueError(f"Path escapes artifact files dir: {path!r}")
        if action == "delete":
            if target.exists():
                target.unlink()
                # Best-effort: prune empty parent dirs up to fdir.
                p_dir = target.parent
                while p_dir != fdir.resolve() and p_dir.is_dir() and not any(p_dir.iterdir()):
                    p_dir.rmdir()
                    p_dir = p_dir.parent
        elif action in ("replace", "create"):
            _write_artifact_file(target, p.get("content", ""))
        else:
            raise ValueError(f"Unknown patch action: {action!r}")

    # Snapshot + bump version
    current_files = read_files(artifact_id)
    _write_version_snapshot(d, current_files)
    _prune_versions(d)

    meta["version"] = int(meta.get("version", 1)) + 1
    _write_meta(artifact_id, meta)

    logger.info(f"[artifacts] patched {artifact_id} → v{meta['version']}")
    return read_artifact(artifact_id)


def delete_artifact(artifact_id: str) -> bool:
    """Delete the entire artifact directory. Idempotent."""
    _validate_id(artifact_id)
    d = _artifact_dir(artifact_id)
    if not d.exists():
        return False
    shutil.rmtree(d)
    logger.info(f"[artifacts] deleted {artifact_id}")
    return True


def set_pinned(artifact_id: str, pinned: bool) -> Dict[str, Any]:
    meta = _read_meta(artifact_id)
    meta["pinned"] = bool(pinned)
    _write_meta(artifact_id, meta)
    return meta


def pin_to_session(artifact_id: str, session_id: str) -> Dict[str, Any]:
    meta = _read_meta(artifact_id)
    pb = meta.get("pinnedBy", [])
    if session_id not in pb:
        pb.append(session_id)
    meta["pinnedBy"] = pb
    _write_meta(artifact_id, meta)
    return meta


def unpin_from_session(artifact_id: str, session_id: str) -> Dict[str, Any]:
    meta = _read_meta(artifact_id)
    meta["pinnedBy"] = [s for s in meta.get("pinnedBy", []) if s != session_id]
    _write_meta(artifact_id, meta)
    return meta


def rollback_to(artifact_id: str, version_id: str) -> Dict[str, Any]:
    """Replace files/ with the contents of versions/<version_id>/."""
    d = _artifact_dir(artifact_id)
    vdir = d / "versions" / version_id
    if not vdir.exists():
        raise FileNotFoundError(f"Version not found: {version_id}")
    fdir = d / "files"
    if fdir.exists():
        shutil.rmtree(fdir)
    shutil.copytree(vdir, fdir)

    # Snapshot post-rollback as a new version (so rollback itself is in history)
    current = read_files(artifact_id)
    _write_version_snapshot(d, current)
    _prune_versions(d)

    meta = _read_meta(artifact_id)
    meta["version"] = int(meta.get("version", 1)) + 1
    _write_meta(artifact_id, meta)

    logger.info(f"[artifacts] rolled back {artifact_id} ← {version_id}")
    return read_artifact(artifact_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_artifact_file(target: Path, content: str) -> None:
    if ".." in target.parts or target.is_absolute() and ARTIFACTS_ROOT not in target.parents:
        raise ValueError(f"Refusing to write outside artifacts root: {target}")
    _atomic_write_text(target, content)


def _write_version_snapshot(artifact_dir: Path, files: List[Dict[str, Any]]) -> str:
    """Copy `files` into versions/vNNN-<iso>/ and return the version id."""
    vdir_root = artifact_dir / "versions"
    vdir_root.mkdir(exist_ok=True)
    existing = sorted([p.name for p in vdir_root.iterdir() if p.is_dir()])
    next_n = 1
    if existing:
        m = re.match(r"v(\d+)-", existing[-1])
        if m:
            next_n = int(m.group(1)) + 1
    vname = f"v{next_n:03d}-{_now_iso()}"
    vpath = vdir_root / vname
    vpath.mkdir()
    for f in files:
        _write_artifact_file(vpath / f["path"], f.get("content", ""))
    return vname


def _prune_versions(artifact_dir: Path) -> None:
    vdir_root = artifact_dir / "versions"
    if not vdir_root.exists():
        return
    versions = sorted([p for p in vdir_root.iterdir() if p.is_dir()])
    if len(versions) <= MAX_VERSIONS:
        return
    for old in versions[:-MAX_VERSIONS]:
        try:
            shutil.rmtree(old)
        except Exception as e:
            logger.warning(f"[artifacts] failed to prune {old.name}: {e}")


# ---------------------------------------------------------------------------
# Debounce for high-frequency state updates (iframe setState loops)
# ---------------------------------------------------------------------------

_state_timers: Dict[str, asyncio.Task] = {}
_state_lock = asyncio.Lock()


async def save_state_debounced(artifact_id: str, state: Dict[str, Any], delay: float = 0.5) -> None:
    """Write state.json at most once per `delay` seconds per artifact.

    Call this from the HTTP handler; each call replaces the pending write
    for that artifact. Keeps state.json out of the hot path of editors
    that call setState on every keystroke.
    """
    async with _state_lock:
        prior = _state_timers.pop(artifact_id, None)
        if prior and not prior.done():
            prior.cancel()

        async def _later() -> None:
            try:
                await asyncio.sleep(delay)
                save_state(artifact_id, state)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"[artifacts] debounced state save failed for {artifact_id}: {e}")
            finally:
                _state_timers.pop(artifact_id, None)

        _state_timers[artifact_id] = asyncio.create_task(_later())
