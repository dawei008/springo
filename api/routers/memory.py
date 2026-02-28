"""
Memory Router for FastAPI
AgentCore Memory 状态与管理端点 + 本地 memory/*.md 文件管理
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
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
        from ..services.memory_backend import get_memory_backend_type

        config = load_memory_config()
        memory_id = config.get("memory_id", "")
        memory_enabled = config.get("memory_enabled", True)
        memory_region = config.get("memory_region", "us-west-2")

        # Flat structure for frontend
        status = {
            "enabled": memory_enabled and bool(memory_id),
            "memory_id": memory_id,
            "region": memory_region,
            "memory_backend": get_memory_backend_type(),
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


# ---------------------------------------------------------------------------
# Session archive (Phase 3)
# ---------------------------------------------------------------------------

class ArchiveRequest(BaseModel):
    session_id: str


@router.post("/memory/archive")
async def archive_session_endpoint(request: ArchiveRequest) -> Dict[str, Any]:
    """Archive a session's messages to memory/*.md using watermark-based incremental archiving.

    Called by frontend on session switch/create/delete/close.
    Only processes messages added since the last archive (watermark).
    """
    try:
        from ..services.memory_archiver import archive_session
        result = await archive_session(request.session_id)
        return result
    except Exception as e:
        logger.error(f"Archive endpoint error: {e}")
        return {"archived": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Local memory file management (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/memory/files")
async def list_memory_files() -> Dict[str, Any]:
    """List all local memory files with metadata."""
    try:
        from ..services.memory_files import get_memory_file_manager
        mgr = get_memory_file_manager()
        if mgr is None:
            return {"files": [], "error": "memory_file_manager_not_initialized"}
        files = mgr.list_files()
        return {"files": files, "workspace": mgr.workspace_dir}
    except Exception as e:
        logger.error(f"List memory files error: {e}")
        return {"files": [], "error": str(e)}


@router.post("/memory/cleanup")
async def cleanup_memory_files() -> Dict[str, Any]:
    """Remove memory files older than retention period."""
    try:
        from ..services.memory_files import get_memory_file_manager
        mgr = get_memory_file_manager()
        if mgr is None:
            return {"removed": [], "error": "memory_file_manager_not_initialized"}
        removed = mgr.cleanup_old_files()
        return {"removed": removed, "count": len(removed)}
    except Exception as e:
        logger.error(f"Cleanup memory files error: {e}")
        return {"removed": [], "error": str(e)}
