"""
Unit tests for TeamTaskManager
"""
import pytest
import asyncio

from api.services.message_bus import TeamMessageBus
from api.services.team_task_manager import (
    TeamTaskManager,
    get_or_create_task_manager,
    get_task_manager,
    remove_task_manager,
)


@pytest.fixture
def bus():
    """Create a message bus for task manager tests."""
    return TeamMessageBus("test-team-tasks")


@pytest.fixture
def mgr(bus):
    """Create a task manager with a message bus."""
    bus.register_agent("alice")
    bus.register_agent("bob")
    return TeamTaskManager("test-team-tasks", bus)


class TestTaskCRUD:
    """Tests for basic task operations."""

    def test_create_task(self, mgr):
        task = mgr.create_task(subject="Test task", description="Do the thing")
        assert task.task_id == "1"
        assert task.title == "Test task"
        assert task.description == "Do the thing"
        assert task.status == "pending"
        assert task.owner is None

    def test_create_with_active_form(self, mgr):
        task = mgr.create_task(
            subject="Run tests",
            description="Execute test suite",
            active_form="Running tests",
        )
        assert task.active_form == "Running tests"

    def test_create_with_owner(self, mgr):
        task = mgr.create_task(subject="Task", description="", owner="alice")
        assert task.owner == "alice"

    def test_auto_increment_ids(self, mgr):
        t1 = mgr.create_task(subject="Task 1", description="")
        t2 = mgr.create_task(subject="Task 2", description="")
        t3 = mgr.create_task(subject="Task 3", description="")
        assert t1.task_id == "1"
        assert t2.task_id == "2"
        assert t3.task_id == "3"

    def test_get_task(self, mgr):
        mgr.create_task(subject="Find me", description="desc")
        task = mgr.get_task("1")
        assert task is not None
        assert task.title == "Find me"

    def test_get_nonexistent(self, mgr):
        assert mgr.get_task("999") is None

    def test_list_tasks(self, mgr):
        mgr.create_task(subject="Task A", description="")
        mgr.create_task(subject="Task B", description="")
        tasks = mgr.list_tasks()
        assert len(tasks) == 2

    def test_list_empty(self, mgr):
        assert mgr.list_tasks() == []

    def test_delete_task(self, mgr):
        mgr.create_task(subject="Delete me", description="")
        assert mgr.delete_task("1") is True
        assert mgr.get_task("1") is None

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete_task("999") is False


class TestTaskUpdate:
    """Tests for task updates."""

    @pytest.mark.asyncio
    async def test_update_status(self, mgr):
        mgr.create_task(subject="Task", description="")
        task = await mgr.update_task("1", status="in_progress")
        assert task.status == "in_progress"

    @pytest.mark.asyncio
    async def test_update_owner(self, mgr):
        mgr.create_task(subject="Task", description="")
        task = await mgr.update_task("1", owner="bob")
        assert task.owner == "bob"

    @pytest.mark.asyncio
    async def test_update_subject(self, mgr):
        mgr.create_task(subject="Old title", description="")
        task = await mgr.update_task("1", subject="New title")
        assert task.title == "New title"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, mgr):
        result = await mgr.update_task("999", status="completed")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_emits_sse(self, mgr, bus):
        mgr.create_task(subject="Task", description="")
        await mgr.update_task("1", status="in_progress")
        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_task_updated" in sse


class TestTaskDependencies:
    """Tests for task dependency resolution."""

    @pytest.mark.asyncio
    async def test_add_blocked_by(self, mgr):
        mgr.create_task(subject="Blocker", description="")
        mgr.create_task(subject="Blocked", description="")
        task = await mgr.update_task("2", add_blocked_by=["1"])
        assert "1" in task.blocked_by

        blocker = mgr.get_task("1")
        assert "2" in blocker.blocks

    @pytest.mark.asyncio
    async def test_add_blocks(self, mgr):
        mgr.create_task(subject="Blocker", description="")
        mgr.create_task(subject="Blocked", description="")
        task = await mgr.update_task("1", add_blocks=["2"])
        assert "2" in task.blocks

        blocked = mgr.get_task("2")
        assert "1" in blocked.blocked_by

    @pytest.mark.asyncio
    async def test_resolve_dependencies(self, mgr, bus):
        # Task 1 blocks Task 2
        mgr.create_task(subject="First", description="")
        t2 = mgr.create_task(subject="Second", description="", owner="bob")
        await mgr.update_task("2", add_blocked_by=["1"])

        # Complete task 1 — should auto-unblock task 2
        await mgr.update_task("1", status="completed")

        t2_updated = mgr.get_task("2")
        assert "1" not in t2_updated.blocked_by

        # Should have emitted unblocked SSE event
        events = []
        for _ in range(10):
            sse = await bus.get_sse_event(timeout=0.5)
            if sse is None:
                break
            events.append(sse)

        unblocked_events = [e for e in events if "team_task_unblocked" in e]
        assert len(unblocked_events) >= 1

    @pytest.mark.asyncio
    async def test_partial_unblock(self, mgr):
        """Task blocked by 2 tasks should not unblock when only 1 completes."""
        mgr.create_task(subject="Blocker 1", description="")
        mgr.create_task(subject="Blocker 2", description="")
        mgr.create_task(subject="Blocked", description="")
        await mgr.update_task("3", add_blocked_by=["1", "2"])

        # Complete only task 1
        await mgr.update_task("1", status="completed")
        t3 = mgr.get_task("3")
        # Should still be blocked by task 2
        assert "2" in t3.blocked_by

    @pytest.mark.asyncio
    async def test_full_unblock(self, mgr):
        """Task should unblock when all blockers complete."""
        mgr.create_task(subject="Blocker 1", description="")
        mgr.create_task(subject="Blocker 2", description="")
        mgr.create_task(subject="Blocked", description="")
        await mgr.update_task("3", add_blocked_by=["1", "2"])

        await mgr.update_task("1", status="completed")
        await mgr.update_task("2", status="completed")
        t3 = mgr.get_task("3")
        assert len(t3.blocked_by) == 0

    @pytest.mark.asyncio
    async def test_notify_owner_on_unblock(self, mgr, bus):
        """Owner should receive a notification when their task is unblocked."""
        mgr.create_task(subject="Blocker", description="")
        mgr.create_task(subject="Blocked", description="", owner="bob")
        await mgr.update_task("2", add_blocked_by=["1"])

        await mgr.update_task("1", status="completed")

        # Bob should have a message in his mailbox
        bob_mailbox = bus.get_mailbox("bob")
        msg = await bob_mailbox.receive(timeout=1.0)
        assert msg is not None
        assert "unblocked" in msg.content.lower()

    def test_delete_cleans_dependencies(self, mgr):
        """Deleting a task should clean up dependency edges."""
        mgr.create_task(subject="A", description="")
        mgr.create_task(subject="B", description="")
        # Manually set up dependencies
        t1 = mgr.get_task("1")
        t2 = mgr.get_task("2")
        t1.blocks.append("2")
        t2.blocked_by.append("1")

        mgr.delete_task("1")
        t2 = mgr.get_task("2")
        assert "1" not in t2.blocked_by


class TestAsyncCreate:
    """Tests for async task creation with SSE."""

    @pytest.mark.asyncio
    async def test_create_task_async(self, mgr, bus):
        task = await mgr.create_task_async(subject="Async task", description="test")
        assert task.task_id == "1"
        assert task.title == "Async task"

        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_task_created" in sse


class TestTaskManagerRegistry:
    """Tests for the global task manager registry."""

    def test_get_or_create(self):
        bus = TeamMessageBus("registry-tm-1")
        mgr = get_or_create_task_manager("registry-tm-1", bus)
        assert mgr is not None

        mgr2 = get_or_create_task_manager("registry-tm-1", bus)
        assert mgr is mgr2

        remove_task_manager("registry-tm-1")

    def test_get_nonexistent(self):
        assert get_task_manager("nonexistent-tm") is None

    def test_remove(self):
        bus = TeamMessageBus("registry-tm-2")
        get_or_create_task_manager("registry-tm-2", bus)
        remove_task_manager("registry-tm-2")
        assert get_task_manager("registry-tm-2") is None
