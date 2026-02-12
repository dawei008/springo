"""
Unit tests for TeamMessageBus and AgentMailbox
"""
import pytest
import asyncio

from api.services.message_bus import (
    AgentMessage,
    AgentMailbox,
    TeamMessageBus,
    get_or_create_bus,
    get_bus,
    remove_bus,
)


@pytest.fixture
def bus():
    """Create a fresh message bus for testing."""
    b = TeamMessageBus("test-team-1")
    yield b


@pytest.fixture
def bus_with_agents(bus):
    """Message bus with two registered agents."""
    bus.register_agent("alice")
    bus.register_agent("bob")
    return bus


class TestAgentMailbox:
    """Tests for AgentMailbox."""

    @pytest.mark.asyncio
    async def test_deliver_and_receive(self):
        mailbox = AgentMailbox("test-agent")
        msg = AgentMessage(sender="user", recipient="test-agent", content="hello")
        await mailbox.deliver(msg)
        received = await mailbox.receive(timeout=1.0)
        assert received is not None
        assert received.content == "hello"
        assert received.sender == "user"

    @pytest.mark.asyncio
    async def test_receive_timeout(self):
        mailbox = AgentMailbox("test-agent")
        received = await mailbox.receive(timeout=0.1)
        assert received is None

    @pytest.mark.asyncio
    async def test_history(self):
        mailbox = AgentMailbox("test-agent")
        msg1 = AgentMessage(sender="a", recipient="test-agent", content="msg1")
        msg2 = AgentMessage(sender="b", recipient="test-agent", content="msg2")
        await mailbox.deliver(msg1)
        await mailbox.deliver(msg2)
        await mailbox.receive(timeout=1.0)
        await mailbox.receive(timeout=1.0)
        assert len(mailbox.history) == 2

    def test_idle_state(self):
        mailbox = AgentMailbox("test-agent")
        assert mailbox.is_idle is True


class TestTeamMessageBus:
    """Tests for TeamMessageBus."""

    def test_register_agent(self, bus):
        mailbox = bus.register_agent("alice")
        assert mailbox is not None
        assert mailbox.agent_name == "alice"
        assert "alice" in bus.agent_names

    def test_register_duplicate(self, bus):
        m1 = bus.register_agent("alice")
        m2 = bus.register_agent("alice")
        assert m1 is m2  # Same mailbox returned

    def test_unregister_agent(self, bus):
        bus.register_agent("alice")
        bus.unregister_agent("alice")
        assert "alice" not in bus.agent_names

    @pytest.mark.asyncio
    async def test_send_message(self, bus_with_agents):
        bus = bus_with_agents
        msg = AgentMessage(
            type="message",
            sender="alice",
            recipient="bob",
            content="hello bob",
            summary="greeting",
        )
        await bus.send_message(msg)

        bob_mailbox = bus.get_mailbox("bob")
        received = await bob_mailbox.receive(timeout=1.0)
        assert received is not None
        assert received.content == "hello bob"
        assert received.sender == "alice"

    @pytest.mark.asyncio
    async def test_send_message_unknown_recipient(self, bus_with_agents):
        bus = bus_with_agents
        msg = AgentMessage(
            sender="alice",
            recipient="charlie",
            content="hello charlie",
        )
        # Should not raise, just log warning
        await bus.send_message(msg)

    @pytest.mark.asyncio
    async def test_broadcast(self, bus_with_agents):
        bus = bus_with_agents
        msg = AgentMessage(
            type="broadcast",
            sender="alice",
            content="announcement",
            summary="team announcement",
        )
        await bus.broadcast(msg)

        # Bob should receive it
        bob_mailbox = bus.get_mailbox("bob")
        received = await bob_mailbox.receive(timeout=1.0)
        assert received is not None
        assert received.content == "announcement"
        assert received.type == "broadcast"

        # Alice should NOT receive her own broadcast
        alice_mailbox = bus.get_mailbox("alice")
        received_alice = await alice_mailbox.receive(timeout=0.1)
        assert received_alice is None

    @pytest.mark.asyncio
    async def test_sse_event_on_send(self, bus_with_agents):
        bus = bus_with_agents
        msg = AgentMessage(
            sender="alice",
            recipient="bob",
            content="test",
            summary="test msg",
        )
        await bus.send_message(msg)

        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_agent_message" in sse

    @pytest.mark.asyncio
    async def test_sse_event_on_broadcast(self, bus_with_agents):
        bus = bus_with_agents
        msg = AgentMessage(
            type="broadcast",
            sender="alice",
            content="broadcast test",
        )
        await bus.broadcast(msg)

        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_agent_broadcast" in sse

    @pytest.mark.asyncio
    async def test_notify_idle(self, bus_with_agents):
        bus = bus_with_agents
        await bus.notify_idle("alice")

        alice_mailbox = bus.get_mailbox("alice")
        assert alice_mailbox.is_idle is True

        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_agent_idle" in sse

    @pytest.mark.asyncio
    async def test_notify_shutdown(self, bus_with_agents):
        bus = bus_with_agents
        await bus.notify_shutdown("bob")

        sse = await bus.get_sse_event(timeout=1.0)
        assert sse is not None
        assert "team_agent_shutdown" in sse
        assert "bob" not in bus.agent_names

    @pytest.mark.asyncio
    async def test_message_history(self, bus_with_agents):
        bus = bus_with_agents
        msg1 = AgentMessage(sender="alice", recipient="bob", content="msg1")
        msg2 = AgentMessage(sender="bob", recipient="alice", content="msg2")
        await bus.send_message(msg1)
        await bus.send_message(msg2)

        history = bus.get_message_history()
        assert len(history) == 2
        assert history[0]["sender"] == "alice"
        assert history[1]["sender"] == "bob"

    @pytest.mark.asyncio
    async def test_get_sse_event_timeout(self, bus):
        sse = await bus.get_sse_event(timeout=0.1)
        assert sse is None

    @pytest.mark.asyncio
    async def test_emit_sse(self, bus):
        await bus.emit_sse("event: test\ndata: {}\n\n")
        sse = await bus.get_sse_event(timeout=1.0)
        assert sse == "event: test\ndata: {}\n\n"


class TestBusRegistry:
    """Tests for the global bus registry functions."""

    def test_get_or_create(self):
        bus = get_or_create_bus("registry-test-1")
        assert bus is not None
        assert bus.team_id == "registry-test-1"

        # Same bus returned on second call
        bus2 = get_or_create_bus("registry-test-1")
        assert bus is bus2

        remove_bus("registry-test-1")

    def test_get_nonexistent(self):
        assert get_bus("nonexistent-team") is None

    def test_remove(self):
        get_or_create_bus("registry-test-2")
        remove_bus("registry-test-2")
        assert get_bus("registry-test-2") is None
