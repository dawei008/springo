"""
Springo Agent Teams Router
Agent 团队 API 路由 - /v1/teams/*
"""
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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
            "agents": [
                {
                    "agent_id": a.agent_id,
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
async def execute_team(team_id: str, request: TeamExecuteRequest = None):
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
                async for event in manager.execute_team(team_id):
                    yield event

            return create_sse_response(team_stream())
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
