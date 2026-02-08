"""
Tool Results Router for FastAPI
工具执行结果存储端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import json
import logging
from pathlib import Path
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ToolResultItem(BaseModel):
    """工具结果项"""
    tool_use_id: str
    name: str
    result: Any
    timestamp: str


class ToolResultsResponse(BaseModel):
    """工具结果列表响应"""
    session_id: str
    results: List[ToolResultItem]
    total: int


class SaveToolResultRequest(BaseModel):
    """保存工具结果请求"""
    session_id: str
    tool_use_id: str
    name: str
    result: Any


class SaveToolResultResponse(BaseModel):
    """保存工具结果响应"""
    success: bool
    tool_use_id: str
    path: Optional[str] = None
    error: Optional[str] = None


class CleanupResponse(BaseModel):
    """清理响应"""
    success: bool
    cleaned: int
    message: str


def _get_tool_results_dir(session_id: str) -> Path:
    """获取工具结果目录"""
    return settings.session_storage_path / session_id / "tool-results"


@router.get("/tool-results/{session_id}", response_model=ToolResultsResponse)
async def get_tool_results(session_id: str):
    """
    获取会话的所有工具执行结果
    """
    results_dir = _get_tool_results_dir(session_id)
    results = []
    
    if results_dir.exists():
        for file in results_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding='utf-8'))
                results.append(ToolResultItem(
                    tool_use_id=data.get("tool_use_id", file.stem),
                    name=data.get("name", "unknown"),
                    result=data.get("result"),
                    timestamp=data.get("timestamp", "")
                ))
            except Exception as e:
                logger.warning(f"Failed to read tool result {file}: {e}")
    
    return ToolResultsResponse(
        session_id=session_id,
        results=results,
        total=len(results)
    )


@router.get("/tool-results/{session_id}/{tool_use_id}")
async def get_tool_result(session_id: str, tool_use_id: str):
    """
    获取单个工具执行结果
    """
    results_dir = _get_tool_results_dir(session_id)
    result_file = results_dir / f"{tool_use_id}.json"
    
    if not result_file.exists():
        raise HTTPException(status_code=404, detail=f"Tool result not found: {tool_use_id}")
    
    try:
        data = json.loads(result_file.read_text(encoding='utf-8'))
        return data
    except Exception as e:
        logger.error(f"Error reading tool result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tool-results", response_model=SaveToolResultResponse)
async def save_tool_result(request: SaveToolResultRequest):
    """
    保存工具执行结果
    """
    try:
        results_dir = _get_tool_results_dir(request.session_id)
        results_dir.mkdir(parents=True, exist_ok=True)
        
        result_file = results_dir / f"{request.tool_use_id}.json"
        
        data = {
            "tool_use_id": request.tool_use_id,
            "name": request.name,
            "result": request.result,
            "timestamp": datetime.now().isoformat()
        }
        
        result_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        
        return SaveToolResultResponse(
            success=True,
            tool_use_id=request.tool_use_id,
            path=str(result_file)
        )
    except Exception as e:
        logger.error(f"Error saving tool result: {e}")
        return SaveToolResultResponse(
            success=False,
            tool_use_id=request.tool_use_id,
            error=str(e)
        )


@router.post("/tool-results/cleanup", response_model=CleanupResponse)
async def cleanup_tool_results():
    """
    清理旧的工具结果（超过7天）
    """
    try:
        cleaned = 0
        sessions_dir = settings.session_storage_path
        
        if sessions_dir.exists():
            import time
            now = time.time()
            max_age = 7 * 24 * 60 * 60  # 7 days
            
            for session_dir in sessions_dir.iterdir():
                if session_dir.is_dir():
                    results_dir = session_dir / "tool-results"
                    if results_dir.exists():
                        for file in results_dir.glob("*.json"):
                            if now - file.stat().st_mtime > max_age:
                                file.unlink()
                                cleaned += 1
        
        return CleanupResponse(
            success=True,
            cleaned=cleaned,
            message=f"Cleaned {cleaned} old tool results"
        )
    except Exception as e:
        logger.error(f"Error cleaning up tool results: {e}")
        return CleanupResponse(
            success=False,
            cleaned=0,
            message=str(e)
        )
