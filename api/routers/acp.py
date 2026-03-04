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
