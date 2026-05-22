"""
Folders Router — single-level grouping for sessions.

Inspired by Quick's session_folders. Frontend stores folder membership on
sessions via the existing PATCH /v1/sessions/{id} endpoint with
``{metadata: {"folder_id": "fld-..."}}``; this router only manages folder
records themselves (id/name/createdAt).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import folders_store

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateFolderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class RenameFolderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


@router.get("/folders")
async def list_folders() -> Dict[str, Any]:
    items = await folders_store.list_folders()
    return {"folders": items, "total": len(items)}


@router.post("/folders", status_code=201)
async def create_folder(payload: CreateFolderIn) -> Dict[str, Any]:
    try:
        return await folders_store.create_folder(payload.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/folders/{folder_id}")
async def rename_folder(folder_id: str, payload: RenameFolderIn) -> Dict[str, Any]:
    try:
        return await folders_store.rename_folder(folder_id, payload.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str) -> Dict[str, bool]:
    """
    Delete a folder. Sessions previously assigned to this folder remain on
    disk with the now-orphaned folder_id; the frontend store is responsible
    for nulling out folder_id on affected sessions (it already iterates the
    sessions list to render the sidebar). This matches Quick's behavior of
    soft-deleting folders without cascading into session storage.
    """
    ok = await folders_store.delete_folder(folder_id)
    return {"deleted": ok}
