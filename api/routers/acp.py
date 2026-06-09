"""
ACP Router for FastAPI
External ACP agent management endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class AddAgentRequest(BaseModel):
    """Add ACP agent request"""
    name: str = Field(..., description="Agent name")
    transport: str = Field(default="stdio", description="Transport: stdio | http | websocket")
    command: Optional[str] = Field(default=None, description="Command to start agent (stdio)")
    args: List[str] = Field(default=[], description="Command arguments (stdio)")
    env: Dict[str, str] = Field(default={}, description="Environment variables")
    url: Optional[str] = Field(default=None, description="Agent URL (http/websocket)")
    auth: Dict[str, str] = Field(default={}, description="Auth config")
    description: str = Field(default="", description="Agent description")


class AgentResponse(BaseModel):
    """Agent operation response"""
    success: bool
    name: Optional[str] = None
    error: Optional[str] = None


class PromptRequest(BaseModel):
    """Direct prompt request"""
    prompt: str = Field(..., description="Prompt text to send")
    cwd: str = Field(default="/tmp", description="Working directory")
    timeout: float = Field(default=600, description="Timeout in seconds")
    session_id: Optional[str] = Field(default=None, description="Session ID to reuse for multi-turn context")


class TaskUpsertRequest(BaseModel):
    """Create or rename an ACP task (named long-running conversation)."""
    name: str = Field(..., description="Human-friendly task name, e.g. 'obo-demo'")
    agent_name: str = Field(..., description="Which configured ACP agent backs this task")
    description: str = Field(default="", description="Free-form description")
    cwd: str = Field(default="", description="Working directory for the agent")


class DispatchRequest(BaseModel):
    """Send a prompt to an agent or a named task, including Springo chat context.

    Either ``task`` (resume) or ``agent`` (start fresh) must be set. When both
    are present, ``task`` wins.
    """
    task: Optional[str] = Field(default=None, description="Existing task name to resume")
    agent: Optional[str] = Field(default=None, description="Agent name for a new task")
    prompt: str = Field(..., description="User-facing prompt for this turn")
    cwd: str = Field(default="/tmp", description="Working directory")
    timeout: float = Field(default=600, description="Timeout in seconds")
    springo_session_id: Optional[str] = Field(default=None, description="Calling Springo chat session")
    context_messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Recent main-chat messages to forward as context (role+text only)",
    )
    new_task_name: Optional[str] = Field(default=None, description="If provided, persist this dispatch as a named task")


# ============ Endpoints ============

@router.get("/acp/agents")
async def list_agents() -> Dict[str, Any]:
    """List all configured ACP agents"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        agents = manager.get_all_agents()
        return {
            "agents": agents,
            "total": len(agents),
            "running": sum(1 for a in agents if a.get("running")),
        }
    except Exception as e:
        logger.error(f"List ACP agents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acp/agents", response_model=AgentResponse)
async def add_agent(request: AddAgentRequest) -> AgentResponse:
    """Add and start an ACP agent"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        success = await manager.add_agent(
            name=request.name,
            transport=request.transport,
            command=request.command,
            args=request.args,
            env=request.env,
            url=request.url,
            auth=request.auth,
            description=request.description,
        )
        if success:
            return AgentResponse(success=True, name=request.name)
        return AgentResponse(success=False, name=request.name,
                            error="Failed to start agent")
    except Exception as e:
        logger.error(f"Add ACP agent error: {e}")
        return AgentResponse(success=False, error=str(e))


@router.delete("/acp/agents/{agent_name}", response_model=AgentResponse)
async def remove_agent(agent_name: str) -> AgentResponse:
    """Stop and remove an ACP agent"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        await manager.remove_agent(agent_name)
        return AgentResponse(success=True, name=agent_name)
    except Exception as e:
        logger.error(f"Remove ACP agent error: {e}")
        return AgentResponse(success=False, error=str(e))


@router.post("/acp/agents/{agent_name}/prompt")
async def prompt_agent(agent_name: str, request: PromptRequest) -> Dict[str, Any]:
    """Send a direct prompt to an ACP agent (bypass LLM)"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        result = await manager.prompt_agent(
            agent_name, request.prompt,
            cwd=request.cwd, timeout=request.timeout,
            session_id=request.session_id,
        )
        return result
    except Exception as e:
        logger.error(f"ACP prompt error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acp/agents/{agent_name}/refresh", response_model=AgentResponse)
async def refresh_agent(agent_name: str) -> AgentResponse:
    """Restart an ACP agent connection"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        success = await manager.refresh_agent(agent_name)
        if success:
            return AgentResponse(success=True, name=agent_name)
        return AgentResponse(success=False, name=agent_name,
                            error="Failed to refresh agent")
    except Exception as e:
        logger.error(f"Refresh ACP agent error: {e}")
        return AgentResponse(success=False, error=str(e))


@router.get("/acp/registry")
async def fetch_registry() -> Dict[str, Any]:
    """Fetch available agents from the ACP registry"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        agents = await manager.fetch_registry()
        return {
            "agents": agents,
            "total": len(agents),
        }
    except Exception as e:
        logger.error(f"Fetch ACP registry error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acp/registry/install", response_model=AgentResponse)
async def install_from_registry(agent_id: str) -> AgentResponse:
    """Install an agent from the ACP registry"""
    try:
        from ..services.acp_client import get_acp_client_manager
        manager = get_acp_client_manager()
        success = await manager.install_agent(agent_id)
        if success:
            return AgentResponse(success=True, name=agent_id)
        return AgentResponse(success=False, name=agent_id,
                            error="Agent not found in registry")
    except Exception as e:
        logger.error(f"Install ACP agent error: {e}")
        return AgentResponse(success=False, error=str(e))


# ============ Named tasks (long-running @mention threads) ============

@router.get("/acp/tasks")
async def list_tasks() -> Dict[str, Any]:
    """All named ACP tasks, most-recently-active first."""
    from ..services.acp_tasks import list_tasks as _list
    tasks = _list()
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/acp/tasks")
async def create_task(request: TaskUpsertRequest) -> Dict[str, Any]:
    """Create or rename a task. Idempotent — same name updates in place."""
    from ..services.acp_tasks import upsert_task
    task = upsert_task(
        request.name,
        agent_name=request.agent_name,
        description=request.description,
        cwd=request.cwd,
    )
    return {"success": True, "task": task}


@router.delete("/acp/tasks/{task_name}")
async def delete_task(task_name: str) -> Dict[str, Any]:
    from ..services.acp_tasks import delete_task as _delete
    ok = _delete(task_name)
    return {"success": ok, "name": task_name}


@router.post("/acp/dispatch")
async def dispatch(request: DispatchRequest) -> Dict[str, Any]:
    """High-level @mention dispatch. Handles three cases:

    1. ``task=<name>`` → resume the existing task's agent_session_id
    2. ``agent=<name>`` (no task) → start a fresh thread; persist as a task
       only if ``new_task_name`` is given
    3. ``agent=<name>`` + ``new_task_name`` → start a fresh thread AND name it

    Main-chat ``context_messages`` are prepended to the prompt so the @agent
    sees what was happening in the Springo conversation that called it.
    """
    from ..services.acp_client import get_acp_client_manager
    from ..services.acp_tasks import get_task, upsert_task, touch_task

    if not request.task and not request.agent:
        raise HTTPException(status_code=400, detail="Either 'task' or 'agent' is required")

    # Resolve agent + agent-side session id from the chosen path.
    agent_name: str
    agent_session_id: Optional[str] = None
    task_name: Optional[str] = request.task

    if request.task:
        task = get_task(request.task)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {request.task}")
        agent_name = task["agent_name"]
        agent_session_id = task.get("agent_session_id")
    else:
        agent_name = request.agent  # type: ignore[assignment]

    # Build the contextual prompt. Keep it short — the agent has its own
    # session memory once we resume, so we only need the *new* main-chat
    # turns the agent hasn't seen.
    contextual_prompt = _build_contextual_prompt(
        request.context_messages, request.prompt, include_header=not agent_session_id,
    )

    try:
        manager = get_acp_client_manager()
        result = await manager.prompt_agent(
            agent_name,
            contextual_prompt,
            cwd=request.cwd,
            timeout=request.timeout,
            session_id=agent_session_id,
        )
    except Exception as e:
        logger.error(f"ACP dispatch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # The client returns the agent-assigned session_id either as ``session_id``
    # or buried in ``updates[].sessionId``; pick the first one we find.
    new_agent_session_id = (
        result.get("session_id")
        or _extract_session_id_from_updates(result.get("updates") or [])
    )

    # Persist as a task if we have a name (existing task or freshly given).
    if task_name:
        touch_task(task_name, agent_session_id=new_agent_session_id)
    elif request.new_task_name:
        task = upsert_task(
            request.new_task_name,
            agent_name=agent_name,
            agent_session_id=new_agent_session_id,
            springo_session_id=request.springo_session_id,
            cwd=request.cwd,
        )
        task_name = task["name"]

    return {
        "success": True,
        "task": task_name,
        "agent": agent_name,
        "agent_session_id": new_agent_session_id,
        "text": result.get("text") or "",
        "stop_reason": result.get("stop_reason"),
        "updates": result.get("updates", []),
    }


def _build_contextual_prompt(
    context_messages: List[Dict[str, Any]],
    user_prompt: str,
    *,
    include_header: bool,
) -> str:
    """Prepend recent main-chat exchanges so the @agent has context.

    On the first turn (no agent session yet) we include a header explaining
    the situation. On resume we just stream the new user turn unprefixed —
    the agent already remembers prior context.
    """
    if not context_messages:
        return user_prompt
    lines: List[str] = []
    if include_header:
        lines.append(
            "[Context from the calling Springo conversation. The user is now "
            "asking you, an external agent, to take over a sub-task. Treat "
            "this context as background; the actual request follows the "
            "marker line.]",
        )
        lines.append("")
    for m in context_messages[-12:]:  # cap at last 12 turns to keep payload sane
        role = (m.get("role") or "").lower()
        text = (m.get("content") or "").strip()
        if not text:
            continue
        prefix = {"user": "User", "assistant": "Assistant"}.get(role, role.capitalize() or "Note")
        lines.append(f"{prefix}: {text}")
    if include_header:
        lines.append("")
        lines.append("--- end of Springo context ---")
        lines.append("")
        lines.append(f"User now asks: {user_prompt}")
    else:
        lines.append("")
        lines.append(user_prompt)
    return "\n".join(lines)


def _extract_session_id_from_updates(updates: List[Dict[str, Any]]) -> Optional[str]:
    for u in updates:
        sid = u.get("sessionId")
        if sid:
            return sid
    return None
