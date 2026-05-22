"""
Sessions Router for FastAPI
会话管理端点
"""
import re
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

from ..services.session_store import get_session_store, SessionStore

logger = logging.getLogger(__name__)

router = APIRouter()


def validate_session_id(session_id: str) -> bool:
    """Validate session ID format to prevent path traversal"""
    if not session_id:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]{1,64}$', session_id))


# ============ Request/Response Models ============

class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str
    created: Any  # Can be float (timestamp) or str (ISO format)
    modified: Any  # Can be float (timestamp) or str (ISO format)
    working_dir: str = ""
    title: str = ""
    message_count: int = 0
    session_mode: str = "general"
    pinned: bool = False
    pinned_at: Optional[float] = None
    folder_id: Optional[str] = None


class SessionsListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionInfo]
    total: int


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    session_id: str
    messages: List[Dict[str, Any]]
    metadata: Dict[str, Any] = {}
    message_count: int


class SaveSessionRequest(BaseModel):
    """保存会话请求"""
    messages: List[Dict[str, Any]] = Field(..., description="Messages to save")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata")


class SaveSessionResponse(BaseModel):
    """保存会话响应"""
    success: bool
    session_id: str
    message_count: int = 0
    error: Optional[str] = None


class HashRequest(BaseModel):
    """哈希请求"""
    working_dir: str


class HashResponse(BaseModel):
    """哈希响应"""
    hash: str
    working_dir: str


# ============ Endpoints ============
# NOTE: Static routes must come BEFORE dynamic routes to avoid path conflicts

@router.get("/sessions", response_model=SessionsListResponse)
async def list_sessions(
    working_dir: Optional[str] = Query(None, description="Filter by working directory")
):
    """
    列出所有会话
    
    List all saved sessions, optionally filtered by working directory.
    """
    try:
        store = get_session_store()
        sessions = store.list_sessions(working_dir)
        
        return SessionsListResponse(
            sessions=[SessionInfo(**s) for s in sessions],
            total=len(sessions)
        )
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/hash", response_model=HashResponse)
async def get_session_hash(request: HashRequest):
    """
    根据工作目录生成会话哈希
    
    Generate a session hash based on working directory (for project-level session management).
    """
    try:
        store = get_session_store()
        hash_value = store.get_session_hash(request.working_dir)
        
        return HashResponse(
            hash=hash_value,
            working_dir=request.working_dir
        )
    except Exception as e:
        logger.error(f"Get session hash error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/by-number/{number}")
async def get_session_by_number(
    number: int,
    working_dir: Optional[str] = Query(None, description="Filter by working directory")
):
    """
    通过编号获取会话
    
    Get session by display number (e.g., #168).
    The latest session has the highest number.
    """
    try:
        store = get_session_store()
        result = store.get_session_by_number(number, working_dir)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session by number error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """
    获取指定会话的详情

    Get details of a specific session including all messages.
    """
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    try:
        store = get_session_store()
        result = store.get_session(session_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


MAX_SESSION_SIZE = 1 * 1024 * 1024  # 1MB


@router.post("/sessions/{session_id}", response_model=SaveSessionResponse)
async def save_session(session_id: str, request: SaveSessionRequest):
    """
    保存消息到会话

    Save messages to session (complete overwrite mode, like Claude Code's JSONL format).
    """
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    try:
        # Check payload size
        import json as json_module
        payload_size = len(json_module.dumps(request.messages, ensure_ascii=False).encode('utf-8'))
        if payload_size > MAX_SESSION_SIZE:
            return SaveSessionResponse(
                success=False,
                session_id=session_id,
                error=f"Session data too large: {payload_size} bytes (max {MAX_SESSION_SIZE})"
            )

        store = get_session_store()
        result = store.save_session(session_id, request.messages, request.metadata)
        
        if "error" in result:
            return SaveSessionResponse(
                success=False,
                session_id=session_id,
                error=result["error"]
            )
        
        return SaveSessionResponse(
            success=True,
            session_id=session_id,
            message_count=result.get("message_count", 0)
        )
    except Exception as e:
        logger.error(f"Save session error: {e}")
        return SaveSessionResponse(
            success=False,
            session_id=session_id,
            error=str(e)
        )


class UpdateMetadataRequest(BaseModel):
    """更新会话元数据请求（不修改消息内容）"""
    metadata: Dict[str, Any] = Field(..., description="Metadata fields to update")


@router.patch("/sessions/{session_id}")
async def update_session_metadata(session_id: str, request: UpdateMetadataRequest):
    """
    只更新会话元数据（标题、workingDir 等），不修改消息内容。

    Update session metadata only (title, workingDir, etc.) without touching messages.
    Used by rename and other metadata-only operations to avoid data loss.
    """
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    try:
        store = get_session_store()
        result = store.update_metadata(session_id, request.metadata)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session metadata error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话

    Delete a session and all its data.
    """
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    try:
        store = get_session_store()
        result = store.delete_session(session_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
