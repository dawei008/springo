"""
Knowledge Base router — REST surface over kb_store.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import kb_store

logger = logging.getLogger(__name__)

router = APIRouter()


class WritePageIn(BaseModel):
    slug: str
    content: str


class IngestTextIn(BaseModel):
    title: str
    content: str
    source_url: Optional[str] = None


class CommitFullIn(BaseModel):
    source_path: str
    slug_hint: Optional[str] = None


class CommitDigestIn(BaseModel):
    title: str
    transcript: str
    original_path: Optional[str] = None
    original_url: Optional[str] = None
    original_size_bytes: Optional[int] = None


class CommitExternalIn(BaseModel):
    title: str
    external_path: str
    sha256: Optional[str] = None


@router.get("/kb/stats")
async def kb_stats() -> Dict[str, Any]:
    return kb_store.stats()


@router.get("/kb/graph")
async def kb_graph() -> Dict[str, Any]:
    return kb_store.get_graph()


@router.post("/kb/graph/regenerate")
async def kb_graph_regenerate() -> Dict[str, Any]:
    return kb_store._regenerate_graph()  # type: ignore[attr-defined]


@router.get("/kb/pages")
async def kb_pages() -> Dict[str, Any]:
    pages = kb_store.list_pages()
    return {"pages": pages, "total": len(pages)}


@router.get("/kb/pages/{slug}")
async def kb_read_page(slug: str) -> Dict[str, Any]:
    try:
        return kb_store.read_page(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/kb/pages/{slug}")
async def kb_write_page(slug: str, payload: WritePageIn) -> Dict[str, Any]:
    if payload.slug != slug:
        raise HTTPException(status_code=400, detail="slug in body must match URL")
    try:
        return kb_store.write_page(slug, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/kb/pages/{slug}")
async def kb_delete_page(slug: str) -> Dict[str, bool]:
    return {"deleted": kb_store.delete_page(slug)}


@router.post("/kb/ingest/plan")
async def kb_ingest_plan(source_path: str) -> Dict[str, Any]:
    try:
        return kb_store.plan_ingest(source_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/kb/ingest/full")
async def kb_ingest_full(payload: CommitFullIn) -> Dict[str, Any]:
    try:
        return kb_store.commit_ingest_full(payload.source_path, payload.slug_hint)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kb/ingest/digest")
async def kb_ingest_digest(payload: CommitDigestIn) -> Dict[str, Any]:
    return kb_store.commit_ingest_digest(
        title=payload.title,
        transcript=payload.transcript,
        original_path=payload.original_path,
        original_url=payload.original_url,
        original_size_bytes=payload.original_size_bytes,
    )


@router.post("/kb/ingest/external")
async def kb_ingest_external(payload: CommitExternalIn) -> Dict[str, Any]:
    return kb_store.commit_ingest_external(
        title=payload.title,
        external_path=payload.external_path,
        sha256=payload.sha256,
    )


@router.post("/kb/ingest/text")
async def kb_ingest_text_endpoint(payload: IngestTextIn) -> Dict[str, Any]:
    return kb_store.ingest_text(
        title=payload.title,
        content=payload.content,
        source_url=payload.source_url,
    )


@router.post("/kb/lint")
async def kb_lint() -> Dict[str, Any]:
    return kb_store.lint()
