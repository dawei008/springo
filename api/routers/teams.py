"""
Springo Agent Teams Router
Agent 团队 API 路由 - /v1/teams/*
"""
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..models.teams import TeamSpawnRequest, TeamExecuteRequest
from ..services.agent_team_manager import get_team_manager
from ..utils.streaming import create_sse_response, SSEEventBuilder

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/teams/spawn")
async def spawn_team(request: TeamSpawnRequest):
    """
    Create a new agent team for a user request.
    The orchestrator will decompose the task when execute is called.
    """
    try:
        manager = get_team_manager()
        team = manager.spawn_team(request)

        return JSONResponse(content={
            "team_id": team.team_id,
            "status": team.status,
            "execution_mode": team.execution_mode,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "role": a.role.name,
                    "purpose": a.role.purpose,
                    "model": a.role.model,
                    "status": a.status,
                }
                for a in team.agents
            ],
            "user_request": team.user_request,
            "created_at": team.created_at,
        })

    except Exception as e:
        logger.error(f"Failed to spawn team: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/teams/{team_id}/execute")
async def execute_team(team_id: str, http_request: Request, request: TeamExecuteRequest = None):
    """
    Execute the agent team workflow with SSE streaming.
    Phases: planning -> parallel execution -> synthesis
    """
    try:
        manager = get_team_manager()
        team = manager.get_team(team_id)
        if not team:
            raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

        if request and request.stream:
            async def team_stream() -> AsyncGenerator[str, None]:
                try:
                    async for event in manager.execute_team(team_id):
                        yield event
                except GeneratorExit:
                    # Client disconnected — cancel running agent tasks
                    logger.warning(f"Team {team_id} SSE client disconnected, cleaning up")
                    manager.cancel_team(team_id)

            return create_sse_response(team_stream(), http_request)
        else:
            # Non-streaming: collect all events and return final result
            events = []
            async for event in manager.execute_team(team_id):
                events.append(event)

            team = manager.get_team(team_id)
            return JSONResponse(content={
                "team_id": team.team_id,
                "status": team.status,
                "final_result": team.final_result,
                "total_tokens": team.total_tokens,
                "task_board": [
                    {
                        "task_id": t.task_id,
                        "title": t.title,
                        "status": t.status,
                        "findings": t.findings[:200],
                    }
                    for t in team.task_board
                ],
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute team: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/teams/{team_id}/events")
async def stream_team_events(team_id: str, http_request: Request):
    """
    Reconnect-safe SSE event stream for an already-executing team.
    Use this instead of re-POSTing /execute when reconnecting.
    """
    try:
        manager = get_team_manager()
        team = manager.get_team(team_id)
        if not team:
            raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

        async def event_stream() -> AsyncGenerator[str, None]:
            async for event in manager.stream_team_events(team_id):
                yield event

        return create_sse_response(event_stream(), http_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream team events: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/teams/{team_id}")
async def get_team(team_id: str):
    """Get team status and details"""
    manager = get_team_manager()
    team = manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

    return JSONResponse(content={
        "team_id": team.team_id,
        "status": team.status,
        "user_request": team.user_request,
        "created_at": team.created_at,
        "completed_at": team.completed_at,
        "agents": [
            {
                "agent_id": a.agent_id,
                "role": a.role.name,
                "purpose": a.role.purpose,
                "status": a.status,
                "findings": a.findings[:200] if a.findings else "",
                "token_usage": a.token_usage,
            }
            for a in team.agents
        ],
        "task_board": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "description": t.description,
                "assigned_to": t.assigned_to,
                "status": t.status,
                "findings": t.findings[:200] if t.findings else "",
            }
            for t in team.task_board
        ],
        "total_tokens": team.total_tokens,
        "final_result": team.final_result[:500] if team.final_result else "",
    })


@router.get("/teams/{team_id}/task-board")
async def get_task_board(team_id: str):
    """Get the team's task board"""
    manager = get_team_manager()
    team = manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

    return JSONResponse(content={
        "team_id": team.team_id,
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "description": t.description,
                "assigned_to": t.assigned_to,
                "role": next(
                    (a.role.name for a in team.agents if a.agent_id == t.assigned_to),
                    "unknown"
                ),
                "status": t.status,
                "findings": t.findings,
            }
            for t in team.task_board
        ],
    })


# === Collaborative Mode Endpoints ===


class TeamMessageRequest(BaseModel):
    """Send a message to an agent in a collaborative team."""
    content: str = Field(..., description="Message content")
    recipient: str = Field(default="team-lead", description="Agent name to send to")


@router.post("/teams/{team_id}/message")
async def send_team_message(team_id: str, request: TeamMessageRequest):
    """
    Send a message from the user to an agent in a collaborative team.
    Typically used to communicate with the team lead.
    """
    try:
        manager = get_team_manager()
        team = manager.get_team(team_id)
        if not team:
            raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

        if team.execution_mode != "collaborative":
            raise HTTPException(
                status_code=400,
                detail={"error": "Message endpoint only available for collaborative teams"},
            )

        bus = manager.get_message_bus(team_id)
        if not bus:
            raise HTTPException(status_code=400, detail={"error": "Team message bus not active"})

        from ..services.message_bus import AgentMessage
        msg = AgentMessage(
            type="message",
            sender="user",
            recipient=request.recipient,
            content=request.content,
            summary=request.content[:50],
        )
        await bus.send_message(msg)

        return JSONResponse(content={
            "status": "sent",
            "message_id": msg.message_id,
            "recipient": request.recipient,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send team message: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/teams/{team_id}/shutdown")
async def shutdown_team(team_id: str):
    """
    Gracefully shut down a collaborative team.
    Sends shutdown requests to all active agents.
    """
    try:
        manager = get_team_manager()
        team = manager.get_team(team_id)
        if not team:
            raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

        if team.execution_mode != "collaborative":
            raise HTTPException(
                status_code=400,
                detail={"error": "Shutdown endpoint only available for collaborative teams"},
            )

        bus = manager.get_message_bus(team_id)
        if not bus:
            return JSONResponse(content={"status": "already_stopped", "team_id": team_id})

        from ..services.message_bus import AgentMessage
        for agent in team.agents:
            agent_name = agent.name or agent.agent_id
            msg = AgentMessage(
                type="shutdown_request",
                sender="user",
                recipient=agent_name,
                content="User requested team shutdown",
                summary="Shutdown request",
            )
            await bus.send_message(msg)

        return JSONResponse(content={
            "status": "shutdown_requested",
            "team_id": team_id,
            "agents_notified": [a.name or a.agent_id for a in team.agents],
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to shut down team: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/teams/{team_id}/messages")
async def get_team_messages(team_id: str):
    """
    Get the full message history for a collaborative team.
    """
    manager = get_team_manager()
    team = manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail={"error": f"Team {team_id} not found"})

    if team.execution_mode != "collaborative":
        raise HTTPException(
            status_code=400,
            detail={"error": "Messages endpoint only available for collaborative teams"},
        )

    bus = manager.get_message_bus(team_id)
    if not bus:
        return JSONResponse(content={"team_id": team_id, "messages": []})

    return JSONResponse(content={
        "team_id": team_id,
        "messages": bus.get_message_history(),
    })
