"""
Artifacts Router — REST API over filesystem-backed Canvas artifacts.
"""
from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services import artifact_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------

class FileIn(BaseModel):
    path: str
    type: Optional[str] = None
    content: str = ""


class FilePatchIn(BaseModel):
    path: str
    action: str = Field(..., pattern="^(replace|create|delete)$")
    content: str = ""
    file_type: Optional[str] = None


class CreateArtifactIn(BaseModel):
    id: Optional[str] = None
    name: str = "Artifact"
    type: str = "document"
    icon: str = "box"
    session_id: Optional[str] = None
    files: List[FileIn] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)


class PatchArtifactIn(BaseModel):
    files: List[FilePatchIn]


class StateIn(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict)


class PinnedIn(BaseModel):
    pinned: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/artifacts")
async def list_all(session_id: Optional[str] = None) -> Dict[str, Any]:
    items = artifact_store.list_artifacts(session_id=session_id)
    return {"artifacts": items, "total": len(items)}


@router.post("/artifacts", status_code=201)
async def create(payload: CreateArtifactIn) -> Dict[str, Any]:
    try:
        files = [f.model_dump() for f in payload.files]
        artifact = artifact_store.create_artifact(
            name=payload.name,
            artifact_type=payload.type,
            icon=payload.icon,
            files=files,
            artifact_id=payload.id,
            session_id=payload.session_id,
            state=payload.state or None,
        )
        return artifact
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifacts/{artifact_id}")
async def read(artifact_id: str) -> Dict[str, Any]:
    try:
        return artifact_store.read_artifact(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/artifacts/{artifact_id}/files")
async def read_files(artifact_id: str) -> Dict[str, Any]:
    try:
        artifact_store._read_meta(artifact_id)  # ensure exists
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"files": artifact_store.read_files(artifact_id)}


@router.get("/artifacts/{artifact_id}/files/{path:path}")
async def read_file(artifact_id: str, path: str) -> Dict[str, Any]:
    try:
        return artifact_store.read_file(artifact_id, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifacts/{artifact_id}/raw/{path:path}")
async def read_file_raw(artifact_id: str, path: str):
    """
    Stream a file's raw bytes back. Used by canvas viewers that need binary
    content (PDFs, images embedded as <img>, etc.) — the JSON read_file
    endpoint can't carry binary because it does ``read_text("utf-8")``.

    Path resolution and traversal guards mirror artifact_store.read_file.
    """
    if ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="Unsafe path")
    try:
        artifact_store._read_meta(artifact_id)  # ensure artifact exists
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    files_root = (artifact_store._artifact_dir(artifact_id) / "files").resolve()
    target = (files_root / path).resolve()
    if files_root not in target.parents and target != files_root:
        raise HTTPException(status_code=400, detail="Path escapes artifact dir")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(str(target), media_type=media_type or "application/octet-stream")


@router.patch("/artifacts/{artifact_id}")
async def patch(artifact_id: str, payload: PatchArtifactIn) -> Dict[str, Any]:
    try:
        patches = [p.model_dump() for p in payload.files]
        return artifact_store.apply_patch(artifact_id, patches)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifacts/{artifact_id}/state")
async def get_state(artifact_id: str) -> Dict[str, Any]:
    try:
        artifact_store._read_meta(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"state": artifact_store.read_state(artifact_id)}


@router.put("/artifacts/{artifact_id}/state")
async def put_state(artifact_id: str, payload: StateIn) -> Dict[str, bool]:
    try:
        artifact_store._read_meta(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await artifact_store.save_state_debounced(artifact_id, payload.state)
    return {"queued": True}


@router.post("/artifacts/{artifact_id}/pin")
async def pin(artifact_id: str, payload: PinnedIn) -> Dict[str, Any]:
    try:
        return artifact_store.set_pinned(artifact_id, payload.pinned)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/artifacts/{artifact_id}/pin/{session_id}")
async def pin_session(artifact_id: str, session_id: str) -> Dict[str, Any]:
    try:
        return artifact_store.pin_to_session(artifact_id, session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/artifacts/{artifact_id}/pin/{session_id}")
async def unpin_session(artifact_id: str, session_id: str) -> Dict[str, Any]:
    try:
        return artifact_store.unpin_from_session(artifact_id, session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/artifacts/{artifact_id}")
async def delete(artifact_id: str) -> Dict[str, bool]:
    try:
        ok = artifact_store.delete_artifact(artifact_id)
        return {"deleted": ok}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifacts/{artifact_id}/versions")
async def list_versions(artifact_id: str) -> Dict[str, Any]:
    try:
        artifact_store._read_meta(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"versions": artifact_store.list_versions(artifact_id)}


@router.get("/artifacts/{artifact_id}/versions/{version_id}/files")
async def read_version_files(artifact_id: str, version_id: str) -> Dict[str, Any]:
    try:
        return {"files": artifact_store.read_version_files(artifact_id, version_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifacts/{artifact_id}/versions/{version_id}/files/{path:path}")
async def read_version_file(artifact_id: str, version_id: str, path: str) -> Dict[str, Any]:
    try:
        return artifact_store.read_version_file(artifact_id, version_id, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/artifacts/{artifact_id}/rollback/{version_id}")
async def rollback(artifact_id: str, version_id: str) -> Dict[str, Any]:
    try:
        return artifact_store.rollback_to(artifact_id, version_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
