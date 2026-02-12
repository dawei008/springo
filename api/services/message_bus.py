"""
Springo Team Message Bus
Inter-agent message routing for collaborative team mode
"""
import uuid
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Literal

from ..utils.streaming import SSEEventBuilder
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """A message sent between agents or from user to agent."""
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    type: Literal["message", "broadcast", "shutdown_request", "shutdown_response"] = "message"
    sender: str = ""
    recipient: str = ""
    content: str = ""
    summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class AgentMailbox:
    """Per-agent inbox with idle state tracking."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self.is_idle: bool = True
        self._message_history: List[AgentMessage] = []

    async def receive(self, timeout: float = 30.0) -> Optional[AgentMessage]:
        """Wait for the next message, returning None on timeout."""
        try:
            msg = await asyncio.wait_for(self.inbox.get(), timeout=timeout)
            self._message_history.append(msg)
            return msg
        except asyncio.TimeoutError:
            return None

    async def deliver(self, msg: AgentMessage):
        """Put a message into this agent's inbox."""
        await self.inbox.put(msg)

    @property
    def history(self) -> List[AgentMessage]:
        return list(self._message_history)


class TeamMessageBus:
    """Routes messages between agents in a collaborative team.

    Each team gets one message bus instance. The bus:
    - Registers agents with named mailboxes
    - Delivers DMs to specific agents
    - Broadcasts to all agents
    - Emits SSE events for frontend consumption
    """

    def __init__(self, team_id: str):
        self.team_id = team_id
        self._mailboxes: Dict[str, AgentMailbox] = {}
        self._sse_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=settings.team_event_queue_max
        )
        self._message_log: List[AgentMessage] = []
        self._message_log_max = settings.team_message_log_max

    def register_agent(self, name: str) -> AgentMailbox:
        """Create a mailbox for an agent and return it."""
        if name in self._mailboxes:
            return self._mailboxes[name]
        mailbox = AgentMailbox(name)
        self._mailboxes[name] = mailbox
        logger.info(f"[MessageBus:{self.team_id}] Registered agent: {name}")
        return mailbox

    def unregister_agent(self, name: str):
        """Remove an agent's mailbox."""
        self._mailboxes.pop(name, None)

    def get_mailbox(self, name: str) -> Optional[AgentMailbox]:
        return self._mailboxes.get(name)

    @property
    def agent_names(self) -> List[str]:
        return list(self._mailboxes.keys())

    def _trim_log(self):
        """Keep message log within bounds (rolling window)."""
        if len(self._message_log) > self._message_log_max:
            # Remove oldest 20% to avoid trimming on every append
            trim_count = self._message_log_max // 5
            self._message_log = self._message_log[trim_count:]

    async def _put_sse(self, event: str):
        """Put an SSE event on the queue, dropping oldest if full."""
        if self._sse_queue.full():
            try:
                self._sse_queue.get_nowait()  # Drop oldest
            except asyncio.QueueEmpty:
                pass
        await self._sse_queue.put(event)

    async def send_message(self, msg: AgentMessage):
        """Deliver a message to a specific agent's inbox.

        Also logs the message and emits an SSE event.
        """
        self._message_log.append(msg)
        self._trim_log()

        recipient_mailbox = self._mailboxes.get(msg.recipient)
        if not recipient_mailbox:
            logger.warning(
                f"[MessageBus:{self.team_id}] Recipient '{msg.recipient}' not found. "
                f"Known agents: {list(self._mailboxes.keys())}"
            )
            return

        await recipient_mailbox.deliver(msg)

        # Emit SSE event
        sse_event = SSEEventBuilder.team_agent_message(
            team_id=self.team_id,
            sender=msg.sender,
            recipient=msg.recipient,
            content=msg.content,
            summary=msg.summary,
            message_id=msg.message_id,
        )
        await self._put_sse(sse_event)

        logger.debug(
            f"[MessageBus:{self.team_id}] {msg.sender} -> {msg.recipient}: "
            f"{msg.summary or msg.content[:60]}"
        )

    async def broadcast(self, msg: AgentMessage):
        """Deliver a message to all agents except the sender."""
        self._message_log.append(msg)
        self._trim_log()

        for name, mailbox in self._mailboxes.items():
            if name != msg.sender:
                broadcast_msg = AgentMessage(
                    type="broadcast",
                    sender=msg.sender,
                    recipient=name,
                    content=msg.content,
                    summary=msg.summary,
                    timestamp=msg.timestamp,
                )
                await mailbox.deliver(broadcast_msg)

        # Emit SSE event
        sse_event = SSEEventBuilder.team_agent_broadcast(
            team_id=self.team_id,
            sender=msg.sender,
            content=msg.content,
            summary=msg.summary,
            message_id=msg.message_id,
        )
        await self._put_sse(sse_event)

        logger.debug(
            f"[MessageBus:{self.team_id}] {msg.sender} broadcast: "
            f"{msg.summary or msg.content[:60]}"
        )

    async def notify_idle(self, agent_name: str):
        """Mark an agent as idle and emit an SSE event."""
        mailbox = self._mailboxes.get(agent_name)
        if mailbox:
            mailbox.is_idle = True

        sse_event = SSEEventBuilder.team_agent_idle(
            team_id=self.team_id,
            agent_name=agent_name,
        )
        await self._put_sse(sse_event)

    async def notify_shutdown(self, agent_name: str):
        """Emit an SSE event when an agent shuts down."""
        sse_event = SSEEventBuilder.team_agent_shutdown(
            team_id=self.team_id,
            agent_name=agent_name,
        )
        await self._put_sse(sse_event)
        self.unregister_agent(agent_name)

    async def get_sse_event(self, timeout: float = 15.0) -> Optional[str]:
        """Get the next SSE event for streaming, or None on timeout."""
        try:
            return await asyncio.wait_for(self._sse_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def emit_sse(self, event: str):
        """Directly push an SSE event string to the stream."""
        await self._put_sse(event)

    def get_message_history(self) -> List[Dict]:
        """Return all messages as dicts for the history API."""
        return [
            {
                "message_id": m.message_id,
                "type": m.type,
                "sender": m.sender,
                "recipient": m.recipient,
                "content": m.content,
                "summary": m.summary,
                "timestamp": m.timestamp,
            }
            for m in self._message_log
        ]


# Registry of active message buses per team
_team_buses: Dict[str, TeamMessageBus] = {}


def get_or_create_bus(team_id: str) -> TeamMessageBus:
    """Get or create a message bus for a team."""
    if team_id not in _team_buses:
        _team_buses[team_id] = TeamMessageBus(team_id)
    return _team_buses[team_id]


def get_bus(team_id: str) -> Optional[TeamMessageBus]:
    """Get an existing message bus for a team."""
    return _team_buses.get(team_id)


def remove_bus(team_id: str):
    """Remove a team's message bus."""
    _team_buses.pop(team_id, None)
