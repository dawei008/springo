"""
Scheduler Tools
Create and manage scheduled/delayed tasks
"""

import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..session import get_session_state

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

# In-memory scheduler storage (tasks are persisted on frontend via electronAPI.cache)
# This backend just handles API calls and returns data for UI to store


def scheduler(
    action: str,
    name: str = "",
    schedule_type: str = "",
    schedule_value: str = "",
    prompt: str = "",
    task_id: str = "",
    enabled: bool = True,
    notify_on_trigger: bool = True,
    create_session: bool = True,
    working_directory: str = "",
    max_executions: int = None,
    end_date: str = ""
) -> Dict[str, Any]:
    """
    Unified scheduler tool for creating and managing scheduled tasks.

    Args:
        action: create, list, cancel, update
        name: Task name/description
        schedule_type: cron, delay, once
        schedule_value: Cron expression, minutes to delay, or ISO datetime
        prompt: The prompt/task to execute when triggered
        task_id: Task ID for cancel/update actions
        enabled: Whether task is enabled (for update)
        notify_on_trigger: Show toast when triggered
        create_session: Create new session for execution
        working_directory: Working directory for task execution
        max_executions: Maximum number of executions for cron tasks
        end_date: End date for cron tasks (ISO format)
    """
    if action == "create":
        return _create_scheduled_task(
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            prompt=prompt,
            notify_on_trigger=notify_on_trigger,
            create_session=create_session,
            working_directory=working_directory,
            max_executions=max_executions,
            end_date=end_date
        )
    elif action == "list":
        return _list_scheduled_tasks()
    elif action == "cancel":
        return _cancel_scheduled_task(task_id)
    elif action == "update":
        return _update_scheduled_task(
            task_id=task_id,
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            prompt=prompt,
            enabled=enabled,
            notify_on_trigger=notify_on_trigger,
            create_session=create_session
        )
    elif action == "pause":
        return _pause_resume_task(task_id, enabled=False)
    elif action == "resume":
        return _pause_resume_task(task_id, enabled=True)
    else:
        return {"error": f"Unknown action: {action}"}


def _create_scheduled_task(
    name: str,
    schedule_type: str,
    schedule_value: str,
    prompt: str,
    notify_on_trigger: bool = True,
    create_session: bool = True,
    working_directory: str = "",
    max_executions: int = None,
    end_date: str = ""
) -> Dict[str, Any]:
    """Create a new scheduled task"""
    if not name:
        return {"error": "Task name is required"}
    if not schedule_type:
        return {"error": "Schedule type is required (cron, delay, or once)"}
    if not schedule_value:
        return {"error": "Schedule value is required"}
    if not prompt:
        return {"error": "Task prompt is required"}

    if schedule_type not in ["cron", "delay", "once"]:
        return {"error": f"Invalid schedule_type: {schedule_type}. Use 'cron', 'delay', or 'once'"}

    # Generate unique task ID
    task_id = f"sched_{uuid.uuid4().hex[:12]}"

    # Calculate next run time
    now = int(time.time() * 1000)  # milliseconds
    next_run = _calculate_next_run(schedule_type, schedule_value, now)

    if next_run is None and schedule_type != "cron":
        return {"error": "Could not calculate next run time from schedule_value"}

    task = {
        "id": task_id,
        "name": name,
        "scheduleType": schedule_type,
        "scheduleValue": schedule_value,
        "prompt": prompt,
        "enabled": True,
        "createdAt": now,
        "lastRun": None,
        "nextRun": next_run,
        "notifyOnTrigger": notify_on_trigger,
        "createSession": create_session,
        "workingDirectory": working_directory,
        "executionCount": 0
    }

    # Add termination conditions for cron tasks
    if schedule_type == "cron":
        if max_executions:
            task["maxExecutions"] = max_executions
        if end_date:
            task["endDate"] = end_date

    # Format human-readable schedule description
    schedule_desc = _format_schedule_description(schedule_type, schedule_value, next_run)

    return {
        "success": True,
        "task": task,
        "message": f"Scheduled task '{name}' created successfully",
        "schedule_description": schedule_desc,
        "ui_update": "schedules_panel"
    }


def _list_scheduled_tasks() -> Dict[str, Any]:
    """List all scheduled tasks (returns instruction for frontend to handle)"""
    # Tasks are stored on frontend, not backend
    # This returns a message indicating the frontend should display stored tasks
    return {
        "success": True,
        "message": "Scheduled tasks are managed by the frontend. Check the Schedules tab in the right panel.",
        "ui_update": "schedules_panel"
    }


def _cancel_scheduled_task(task_id: str) -> Dict[str, Any]:
    """Cancel/delete a scheduled task"""
    if not task_id:
        return {"error": "Task ID is required"}

    return {
        "success": True,
        "task_id": task_id,
        "action": "cancel",
        "message": f"Task {task_id} will be cancelled",
        "ui_update": "schedules_panel"
    }


def _update_scheduled_task(
    task_id: str,
    name: str = "",
    schedule_type: str = "",
    schedule_value: str = "",
    prompt: str = "",
    enabled: bool = True,
    notify_on_trigger: bool = True,
    create_session: bool = True
) -> Dict[str, Any]:
    """Update an existing scheduled task"""
    if not task_id:
        return {"error": "Task ID is required"}

    # Build update payload with only provided fields
    updates = {"id": task_id}
    if name:
        updates["name"] = name
    if schedule_type:
        updates["scheduleType"] = schedule_type
    if schedule_value:
        updates["scheduleValue"] = schedule_value
    if prompt:
        updates["prompt"] = prompt
    updates["enabled"] = enabled
    updates["notifyOnTrigger"] = notify_on_trigger
    updates["createSession"] = create_session

    # Recalculate next run if schedule changed
    if schedule_type and schedule_value:
        now = int(time.time() * 1000)
        updates["nextRun"] = _calculate_next_run(schedule_type, schedule_value, now)

    return {
        "success": True,
        "task_id": task_id,
        "updates": updates,
        "action": "update",
        "message": f"Task {task_id} will be updated",
        "ui_update": "schedules_panel"
    }


def _pause_resume_task(task_id: str, enabled: bool) -> Dict[str, Any]:
    """Pause or resume a scheduled task without deleting it."""
    if not task_id:
        return {"error": "Task ID is required"}

    return {
        "success": True,
        "task_id": task_id,
        "updates": {"id": task_id, "enabled": enabled},
        "action": "update",
        "message": f"Task {task_id} {'resumed' if enabled else 'paused'}",
        "ui_update": "schedules_panel"
    }


def _calculate_next_run(schedule_type: str, schedule_value: str, now: int) -> Optional[int]:
    """Calculate the next run time in milliseconds"""
    if schedule_type == "delay":
        # schedule_value is minutes
        try:
            minutes = int(schedule_value)
            return now + (minutes * 60 * 1000)
        except ValueError:
            return None

    elif schedule_type == "once":
        # schedule_value is ISO datetime string
        try:
            dt = datetime.fromisoformat(schedule_value.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            return None

    elif schedule_type == "cron":
        if HAS_CRONITER:
            try:
                base_dt = datetime.fromtimestamp(now / 1000)
                cron = croniter(schedule_value, base_dt)
                next_dt = cron.get_next(datetime)
                return int(next_dt.timestamp() * 1000)
            except (ValueError, KeyError):
                return None
        # Fallback: frontend will calculate
        return None

    return None


def _format_schedule_description(schedule_type: str, schedule_value: str, next_run: Optional[int]) -> str:
    """Format a human-readable schedule description"""
    if schedule_type == "delay":
        try:
            minutes = int(schedule_value)
            if minutes == 1:
                return "In 1 minute"
            elif minutes < 60:
                return f"In {minutes} minutes"
            else:
                hours = minutes // 60
                remaining = minutes % 60
                if remaining == 0:
                    return f"In {hours} hour{'s' if hours > 1 else ''}"
                return f"In {hours}h {remaining}m"
        except ValueError:
            return f"After {schedule_value}"

    elif schedule_type == "once":
        return f"Once at {schedule_value}"

    elif schedule_type == "cron":
        # Parse common cron patterns
        return _describe_cron(schedule_value)

    return schedule_value


def _describe_cron(cron_expr: str) -> str:
    """Convert cron expression to human-readable description"""
    parts = cron_expr.split()
    if len(parts) != 5:
        return f"Cron: {cron_expr}"

    minute, hour, day, month, weekday = parts

    day_names = {
        "0": "Sun", "1": "Mon", "2": "Tue",
        "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"
    }

    # Every N minutes
    if minute.startswith("*/"):
        try:
            n = int(minute[2:])
            return f"Every {n} minute{'s' if n > 1 else ''}"
        except ValueError:
            pass

    # Every N hours
    if minute == "0" and hour.startswith("*/"):
        try:
            n = int(hour[2:])
            return f"Every {n} hour{'s' if n > 1 else ''}"
        except ValueError:
            pass

    # Every minute
    if minute == "*" and hour == "*":
        return "Every minute"

    # Specific time patterns
    if minute != "*" and hour != "*" and not minute.startswith("*/") and not hour.startswith("*/"):
        try:
            h = int(hour)
            m = int(minute)
            time_str = f"{h:02d}:{m:02d}"

            if day == "*" and month == "*" and weekday == "*":
                return f"Every day at {time_str}"

            if day == "*" and month == "*" and weekday != "*":
                # Parse weekday ranges/lists: 1-5, 0,6, etc.
                if "-" in weekday:
                    start, end = weekday.split("-", 1)
                    start_name = day_names.get(start, start)
                    end_name = day_names.get(end, end)
                    return f"{start_name}-{end_name} at {time_str}"
                if weekday in day_names:
                    return f"Every {day_names[weekday]} at {time_str}"
                return f"Weekday {weekday} at {time_str}"

            if day != "*" and month == "*":
                return f"Day {day} of each month at {time_str}"
        except ValueError:
            pass

    # Validate with croniter and show next run
    if HAS_CRONITER:
        try:
            cron = croniter(cron_expr)
            next_dt = cron.get_next(datetime)
            return f"Cron: {cron_expr} (next: {next_dt.strftime('%m-%d %H:%M')})"
        except (ValueError, KeyError):
            pass

    return f"Cron: {cron_expr}"
