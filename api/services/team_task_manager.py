"""
Springo Team Task Manager
Shared task board with dependency resolution for collaborative teams
"""
import logging
from typing import Optional, Dict, List, Literal, TYPE_CHECKING

from ..models.teams import EnhancedTaskBoardItem
from ..utils.streaming import SSEEventBuilder

if TYPE_CHECKING:
    from .message_bus import TeamMessageBus, AgentMessage

logger = logging.getLogger(__name__)


class TeamTaskManager:
    """Manages a shared task board for a collaborative team.

    Provides CRUD operations on tasks with automatic dependency
    resolution: when a task is completed, any tasks it blocks
    that have no remaining blockers are automatically unblocked
    and their owners are notified via the message bus.
    """

    def __init__(self, team_id: str, message_bus: "TeamMessageBus"):
        self.team_id = team_id
        self._bus = message_bus
        self._tasks: Dict[str, EnhancedTaskBoardItem] = {}
        self._counter = 0

    def create_task(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        owner: Optional[str] = None,
    ) -> EnhancedTaskBoardItem:
        """Create a new task and return it."""
        self._counter += 1
        task = EnhancedTaskBoardItem(
            task_id=str(self._counter),
            title=subject,
            description=description,
            active_form=active_form,
            owner=owner,
            status="pending",
        )
        self._tasks[task.task_id] = task
        logger.info(f"[TaskManager:{self.team_id}] Created task #{task.task_id}: {subject}")
        return task

    async def create_task_async(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        owner: Optional[str] = None,
    ) -> EnhancedTaskBoardItem:
        """Create a task and emit SSE event."""
        task = self.create_task(subject, description, active_form, owner)
        sse = SSEEventBuilder.team_task_created(
            team_id=self.team_id,
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            owner=task.owner,
        )
        await self._bus.emit_sse(sse)
        return task

    def get_task(self, task_id: str) -> Optional[EnhancedTaskBoardItem]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[EnhancedTaskBoardItem]:
        return list(self._tasks.values())

    async def update_task(
        self,
        task_id: str,
        status: Optional[Literal["pending", "in_progress", "completed", "error"]] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        active_form: Optional[str] = None,
        owner: Optional[str] = None,
        add_blocks: Optional[List[str]] = None,
        add_blocked_by: Optional[List[str]] = None,
    ) -> Optional[EnhancedTaskBoardItem]:
        """Update a task and handle dependency resolution if completed."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if subject is not None:
            task.title = subject
        if description is not None:
            task.description = description
        if active_form is not None:
            task.active_form = active_form
        if owner is not None:
            task.owner = owner
        if status is not None:
            task.status = status

        # Manage dependency edges
        if add_blocks:
            for blocked_id in add_blocks:
                if blocked_id not in task.blocks:
                    task.blocks.append(blocked_id)
                blocked_task = self._tasks.get(blocked_id)
                if blocked_task and task_id not in blocked_task.blocked_by:
                    blocked_task.blocked_by.append(task_id)

        if add_blocked_by:
            for blocker_id in add_blocked_by:
                if blocker_id not in task.blocked_by:
                    task.blocked_by.append(blocker_id)
                blocker_task = self._tasks.get(blocker_id)
                if blocker_task and task_id not in blocker_task.blocks:
                    blocker_task.blocks.append(task_id)

        # Emit update SSE
        sse = SSEEventBuilder.team_task_updated(
            team_id=self.team_id,
            task_id=task.task_id,
            status=task.status,
            owner=task.owner,
            title=task.title,
        )
        await self._bus.emit_sse(sse)

        # Resolve dependencies when a task is completed
        if status == "completed":
            await self._resolve_dependencies(task_id)

        return task

    async def _resolve_dependencies(self, completed_task_id: str):
        """When a task completes, check if any tasks it blocks are now unblocked.

        For each newly unblocked task, emit an SSE event and notify the owner
        via the message bus.
        """
        completed_task = self._tasks.get(completed_task_id)
        if not completed_task:
            return

        for blocked_id in completed_task.blocks:
            blocked_task = self._tasks.get(blocked_id)
            if not blocked_task:
                continue

            # Remove the completed task from blocked_by
            if completed_task_id in blocked_task.blocked_by:
                blocked_task.blocked_by.remove(completed_task_id)

            # Check if now fully unblocked
            if not blocked_task.blocked_by and blocked_task.status == "pending":
                logger.info(
                    f"[TaskManager:{self.team_id}] Task #{blocked_id} unblocked "
                    f"(was blocked by #{completed_task_id})"
                )

                # Emit unblocked SSE event
                sse = SSEEventBuilder.team_task_unblocked(
                    team_id=self.team_id,
                    task_id=blocked_id,
                    title=blocked_task.title,
                    owner=blocked_task.owner,
                )
                await self._bus.emit_sse(sse)

                # Notify the owner via message bus
                if blocked_task.owner:
                    from .message_bus import AgentMessage
                    notification = AgentMessage(
                        type="message",
                        sender="system",
                        recipient=blocked_task.owner,
                        content=(
                            f"Task #{blocked_id} '{blocked_task.title}' is now unblocked "
                            f"and ready to work on."
                        ),
                        summary=f"Task #{blocked_id} unblocked",
                    )
                    await self._bus.send_message(notification)

    def delete_task(self, task_id: str) -> bool:
        """Remove a task and clean up dependency edges."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        # Remove from blocks lists of tasks that block this one
        for blocker_id in task.blocked_by:
            blocker = self._tasks.get(blocker_id)
            if blocker and task_id in blocker.blocks:
                blocker.blocks.remove(task_id)

        # Remove from blocked_by lists of tasks this one blocks
        for blocked_id in task.blocks:
            blocked = self._tasks.get(blocked_id)
            if blocked and task_id in blocked.blocked_by:
                blocked.blocked_by.remove(task_id)

        del self._tasks[task_id]
        return True


# Registry of active task managers per team
_team_task_managers: Dict[str, TeamTaskManager] = {}


def get_or_create_task_manager(team_id: str, message_bus: "TeamMessageBus") -> TeamTaskManager:
    """Get or create a task manager for a team."""
    if team_id not in _team_task_managers:
        _team_task_managers[team_id] = TeamTaskManager(team_id, message_bus)
    return _team_task_managers[team_id]


def get_task_manager(team_id: str) -> Optional[TeamTaskManager]:
    """Get an existing task manager for a team."""
    return _team_task_managers.get(team_id)


def remove_task_manager(team_id: str):
    """Remove a team's task manager."""
    _team_task_managers.pop(team_id, None)
