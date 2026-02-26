"""
Scheduler Service — persistent task storage (~/.springo/schedules.json)

Independent from session_store: schedule tasks have their own lifecycle.
Frontend creates/updates/deletes tasks; backend persists and restores on startup.
"""

import json
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

SCHEDULES_FILE = os.path.expanduser("~/.springo/schedules.json")
LEGACY_SCHEDULES_FILE = os.path.expanduser("~/.springo/scheduled_tasks.json")


class SchedulerService:
    """Persistent storage for scheduled tasks."""

    def __init__(self):
        self._tasks: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load persisted tasks from disk, migrating from legacy file if needed."""
        try:
            if os.path.exists(SCHEDULES_FILE):
                with open(SCHEDULES_FILE, "r") as f:
                    data = json.load(f)
                self._tasks = data.get("tasks", {})
                logger.info(f"Loaded {len(self._tasks)} scheduled tasks from {SCHEDULES_FILE}")
            elif os.path.exists(LEGACY_SCHEDULES_FILE):
                # Migrate from legacy scheduled_tasks.json (dict keyed by task id)
                with open(LEGACY_SCHEDULES_FILE, "r") as f:
                    legacy_data = json.load(f)
                # Legacy format: {task_id: task_dict, ...} (flat dict, no wrapper)
                if isinstance(legacy_data, dict):
                    # Check if it's already wrapped with "tasks" key
                    if "tasks" in legacy_data and isinstance(legacy_data["tasks"], dict):
                        self._tasks = legacy_data["tasks"]
                    else:
                        self._tasks = legacy_data
                logger.info(f"Migrated {len(self._tasks)} tasks from legacy {LEGACY_SCHEDULES_FILE}")
                self._save()  # Save to new location
        except Exception as e:
            logger.error(f"Failed to load schedules: {e}")
            self._tasks = {}

    def _save(self):
        """Persist tasks to disk."""
        try:
            os.makedirs(os.path.dirname(SCHEDULES_FILE), exist_ok=True)
            with open(SCHEDULES_FILE, "w") as f:
                json.dump(
                    {"tasks": self._tasks, "updated_at": datetime.now().isoformat()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.error(f"Failed to save schedules: {e}")

    def list_tasks(self, session_id: Optional[str] = None) -> List[dict]:
        """List all tasks, optionally filtered by source session."""
        tasks = list(self._tasks.values())
        if session_id:
            tasks = [t for t in tasks if t.get("sourceSessionId") == session_id]
        return tasks

    def get_task(self, task_id: str) -> Optional[dict]:
        return self._tasks.get(task_id)

    def save_task(self, task: dict) -> dict:
        """Create or update a single task."""
        task_id = task.get("id")
        if not task_id:
            return {"error": "Missing task id"}
        self._tasks[task_id] = task
        self._save()
        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[dict]:
        """Partial update of a task."""
        if task_id not in self._tasks:
            return None
        self._tasks[task_id].update(updates)
        self._save()
        return self._tasks[task_id]

    def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def bulk_sync(self, tasks: Dict[str, dict]):
        """Full sync from frontend — replaces all tasks."""
        self._tasks = tasks
        self._save()


# Singleton
_instance: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    global _instance
    if _instance is None:
        _instance = SchedulerService()
    return _instance
