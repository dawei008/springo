"""
Schedule Tasks CRUD Router

Endpoints for persisting and restoring scheduled tasks.
Frontend owns timer logic; backend owns storage.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _get_service():
    from ..services.scheduler_service import get_scheduler_service
    return get_scheduler_service()


class TaskBody(BaseModel):
    task: Dict[str, Any]


class BulkSyncBody(BaseModel):
    tasks: Dict[str, Dict[str, Any]]


@router.get("")
async def list_tasks(session_id: Optional[str] = None):
    """List all scheduled tasks, optionally filtered by source session."""
    svc = _get_service()
    return {"tasks": svc.list_tasks(session_id)}


@router.post("")
async def save_task(body: TaskBody):
    """Create or update a single task."""
    svc = _get_service()
    result = svc.save_task(body.task)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "task": result}


@router.put("/bulk")
async def bulk_sync(body: BulkSyncBody):
    """Full sync — replaces all tasks with frontend state."""
    svc = _get_service()
    svc.bulk_sync(body.tasks)
    return {"success": True, "count": len(body.tasks)}


@router.patch("/{task_id}")
async def update_task(task_id: str, updates: Dict[str, Any]):
    """Partial update of a task."""
    svc = _get_service()
    result = svc.update_task(task_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": result}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a scheduled task."""
    svc = _get_service()
    if not svc.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}
