"""
Memory Router for FastAPI
AgentCore Memory 状态与管理端点（完整版）
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class MemoryStatus(BaseModel):
    """内存状态"""
    enabled: bool = False
    configured: bool = False
    connected: bool = False
    memory_id: Optional[str] = None
    region: Optional[str] = None
    queue_size: int = 0
    worker_running: bool = False
    sync_check_done: bool = False
    error: Optional[str] = None


class MemoryStatusResponse(BaseModel):
    """内存状态响应"""
    status: str
    memory: MemoryStatus


@router.get("/memory/status")
async def get_memory_status() -> Dict[str, Any]:
    """获取长期记忆状态"""
    import os
    import json as json_module

    try:
        from ..services.memory_sync import get_sync_manager, load_memory_config

        config = load_memory_config()
        memory_id = config.get("memory_id", "")
        memory_enabled = config.get("memory_enabled", True)
        memory_region = config.get("memory_region", "us-west-2")

        # Flat structure for frontend
        status = {
            "enabled": memory_enabled and bool(memory_id),
            "memory_id": memory_id,
            "region": memory_region,
            "running": False,
            "sessions_synced": 0,
            "total_events": 0,
            "pending": 0,
        }

        if not memory_enabled or not memory_id:
            status["status"] = "disabled"
            return status

        manager = get_sync_manager()
        if manager is None:
            status["status"] = "not_running"
            return status

        status["running"] = True

        # Count synced sessions from disk
        sessions_dir = os.path.expanduser("~/.springo/sessions")
        if os.path.exists(sessions_dir):
            synced_sessions = 0
            total_synced = 0
            for session_id in os.listdir(sessions_dir):
                sync_file = os.path.join(sessions_dir, session_id, ".sync_state.json")
                if os.path.exists(sync_file):
                    try:
                        with open(sync_file, 'r') as f:
                            state = json_module.load(f)
                            if state.get("last_synced_index", -1) >= 0:
                                synced_sessions += 1
                                total_synced += state.get("total_synced", 0)
                    except Exception:
                        pass
            status["sessions_synced"] = synced_sessions
            status["total_events"] = total_synced

        # Check queue
        try:
            stats = manager.get_stats()
            status["pending"] = stats.get("queue_size", 0)
        except Exception:
            pass

        # Determine status
        if status["pending"] > 0:
            status["status"] = "syncing"
        else:
            status["status"] = "synced"

        return status
    except Exception as e:
        logger.error(f"Memory status error: {e}")
        return {"status": "error", "error": str(e)}
