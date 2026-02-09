"""
Context Router for FastAPI
上下文管理端点（完整版）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class ContextItem(BaseModel):
    """上下文项"""
    type: str  # "file", "url", "text", "image"
    content: str
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AddContextRequest(BaseModel):
    """添加上下文请求"""
    items: List[ContextItem] = Field(..., description="Context items to add")
    session_id: Optional[str] = None


class AddContextResponse(BaseModel):
    """添加上下文响应"""
    success: bool
    added: int
    total_tokens: int = 0
    error: Optional[str] = None


class GetContextResponse(BaseModel):
    """获取上下文响应"""
    items: List[ContextItem]
    total: int
    total_tokens: int = 0


class ClearContextResponse(BaseModel):
    """清除上下文响应"""
    success: bool
    cleared: int


class ContextStatsRequest(BaseModel):
    """上下文统计请求"""
    messages: List[Dict[str, Any]] = Field(default=[], description="Message history")
    system_prompt: str = Field(default="", description="System prompt")
    system: Optional[str] = None
    tools: Optional[List[Dict]] = None
    skills: Optional[List[Dict]] = None
    memory_files: Optional[List[Dict]] = None
    model: Optional[str] = None


class ContextSummarizeRequest(BaseModel):
    """上下文摘要请求"""
    messages: List[Dict[str, Any]] = Field(..., description="Message history")
    keep_recent: int = Field(default=10, description="Keep recent N messages")


class ContextAutoCheckRequest(BaseModel):
    """自动检查请求"""
    messages: List[Dict[str, Any]] = Field(default=[], description="Message history")
    system_prompt: str = Field(default="", description="System prompt")
    tools: Optional[List[Dict]] = None
    session_id: Optional[str] = None


# In-memory context store
_context_store: Dict[str, List[ContextItem]] = {}


# ============ Endpoints ============

@router.post("/context/add", response_model=AddContextResponse)
async def add_context(request: AddContextRequest):
    """添加上下文"""
    try:
        session_id = request.session_id or "default"
        if session_id not in _context_store:
            _context_store[session_id] = []
        _context_store[session_id].extend(request.items)

        from ..services.context_manager import count_tokens
        total_tokens = sum(count_tokens(item.content) for item in request.items)

        return AddContextResponse(success=True, added=len(request.items), total_tokens=total_tokens)
    except Exception as e:
        logger.error(f"Add context error: {e}")
        return AddContextResponse(success=False, added=0, error=str(e))


@router.get("/context", response_model=GetContextResponse)
async def get_context(session_id: Optional[str] = None):
    """获取当前上下文"""
    try:
        session_id = session_id or "default"
        items = _context_store.get(session_id, [])

        from ..services.context_manager import count_tokens
        total_tokens = sum(count_tokens(item.content) for item in items)

        return GetContextResponse(items=items, total=len(items), total_tokens=total_tokens)
    except Exception as e:
        logger.error(f"Get context error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/context", response_model=ClearContextResponse)
async def clear_context(session_id: Optional[str] = None):
    """清除上下文"""
    try:
        session_id = session_id or "default"
        cleared = len(_context_store.get(session_id, []))
        _context_store[session_id] = []
        return ClearContextResponse(success=True, cleared=cleared)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/context/{index}")
async def remove_context_item(index: int, session_id: Optional[str] = None):
    """删除指定上下文项"""
    try:
        session_id = session_id or "default"
        items = _context_store.get(session_id, [])
        if index < 0 or index >= len(items):
            raise HTTPException(status_code=404, detail=f"Context item {index} not found")
        removed = items.pop(index)
        return {"success": True, "removed": removed.model_dump(), "remaining": len(items)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/stats")
async def context_stats(request: ContextStatsRequest) -> Dict[str, Any]:
    """获取上下文 token 统计"""
    try:
        from ..services.context_manager import get_context_stats
        return get_context_stats(
            messages=request.messages,
            system_prompt=request.system_prompt,
            tools=request.tools,
            model=request.model,
        )
    except Exception as e:
        logger.error(f"Context stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/breakdown")
async def context_breakdown(request: ContextStatsRequest) -> Dict[str, Any]:
    """获取上下文 token 分解详情 (Flask 兼容格式)"""
    try:
        from ..services.context_manager import get_context_breakdown

        system = request.system or request.system_prompt or ""
        return get_context_breakdown(
            messages=request.messages,
            system_prompt=system,
            tools=request.tools,
            skills=request.skills,
            memory_files=request.memory_files,
            model=request.model,
        )
    except Exception as e:
        logger.error(f"Context breakdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/summarize")
async def context_summarize(request: ContextSummarizeRequest) -> Dict[str, Any]:
    """自动摘要上下文"""
    try:
        from ..services.context_manager import (
            summarize_context, extract_structured_info,
            split_messages_for_summary, get_context_stats,
        )
        # 尝试获取 bedrock service
        bedrock_service = None
        try:
            from ..services.bedrock import get_bedrock_service
            bedrock_service = get_bedrock_service()
        except Exception:
            pass

        old_stats = get_context_stats(messages=request.messages)

        result = await summarize_context(
            messages=request.messages,
            bedrock_service=bedrock_service,
            keep_recent=request.keep_recent,
        )

        # Enrich response with additional fields
        if result.get("summarized"):
            new_messages = result.get("messages", [])
            new_stats = get_context_stats(messages=new_messages)
            old_count = len(request.messages)
            new_count = len(new_messages)
            try:
                structured_info = extract_structured_info(request.messages)
            except Exception:
                structured_info = {}
            result.update({
                "messages_removed": old_count - new_count,
                "messages_kept": new_count,
                "old_stats": old_stats,
                "new_stats": new_stats,
                "structured_info": structured_info,
            })

        return result
    except Exception as e:
        logger.error(f"Context summarize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/auto-check")
async def context_auto_check(request: ContextAutoCheckRequest) -> Dict[str, Any]:
    """自动检查上下文健康状况"""
    try:
        from ..services.context_manager import auto_check_context
        result = auto_check_context(
            messages=request.messages,
            system_prompt=request.system_prompt,
            tools=request.tools,
        )

        # Persist summary event if session_id provided and summary was needed
        if request.session_id and result.get("needs_summary"):
            try:
                from ..services.context_manager import save_summary_event
                save_summary_event(
                    session_id=request.session_id,
                    summary=result.get("summary_prompt", "auto-check triggered"),
                    old_count=len(request.messages),
                    new_count=result.get("recent_count", 0),
                )
            except Exception as e:
                logger.warning(f"Failed to save summary event: {e}")

        return result
    except Exception as e:
        logger.error(f"Context auto-check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
