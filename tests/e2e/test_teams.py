"""
Springo E2E Tests - Agent Teams API
Agent 团队协作端点 E2E 测试
"""
import pytest
import httpx
import json

from .conftest import DEFAULT_TEST_MODEL


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_spawn(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/teams/spawn creates a team with agents.
    验证创建团队并返回 team_id 和 agents。
    """
    response = await fastapi_client.post(
        "/v1/teams/spawn",
        json={
            "user_request": "Explain the project structure of this codebase",
        },
        timeout=30,
    )

    assert response.status_code == 200

    data = response.json()
    assert "team_id" in data, "Response missing team_id"
    assert data["team_id"].startswith("team_"), f"team_id should start with 'team_', got: {data['team_id']}"
    assert "status" in data
    assert data["status"] == "created"
    assert "agents" in data
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) >= 1, "Team should have at least 1 agent (orchestrator)"
    assert "user_request" in data
    assert data["user_request"] == "Explain the project structure of this codebase"
    assert "created_at" in data

    # Verify orchestrator agent is present
    roles = [a["role"] for a in data["agents"]]
    assert "orchestrator" in roles, f"Expected orchestrator role, got: {roles}"

    # Verify agent structure
    agent = data["agents"][0]
    assert "agent_id" in agent
    assert "role" in agent
    assert "purpose" in agent
    assert "model" in agent
    assert "status" in agent
    assert agent["status"] == "idle"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_get_status(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: GET /v1/teams/{team_id} returns team details.
    验证获取团队状态。
    """
    # First spawn a team
    spawn_resp = await fastapi_client.post(
        "/v1/teams/spawn",
        json={"user_request": "List files in current directory"},
        timeout=30,
    )
    assert spawn_resp.status_code == 200
    team_id = spawn_resp.json()["team_id"]

    # Get team status
    response = await fastapi_client.get(f"/v1/teams/{team_id}", timeout=30)

    assert response.status_code == 200

    data = response.json()
    assert data["team_id"] == team_id
    assert "status" in data
    assert "user_request" in data
    assert "created_at" in data
    assert "agents" in data
    assert isinstance(data["agents"], list)
    assert "task_board" in data
    assert isinstance(data["task_board"], list)
    assert "total_tokens" in data
    assert "final_result" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_get_nonexistent(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: GET /v1/teams/{team_id} for non-existent team returns 404.
    验证获取不存在的团队返回 404。
    """
    response = await fastapi_client.get("/v1/teams/nonexistent_team_xyz", timeout=10)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_task_board(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: GET /v1/teams/{team_id}/task-board returns task board structure.
    验证任务板结构正确。
    """
    # Spawn a team
    spawn_resp = await fastapi_client.post(
        "/v1/teams/spawn",
        json={"user_request": "Analyze code quality"},
        timeout=30,
    )
    assert spawn_resp.status_code == 200
    team_id = spawn_resp.json()["team_id"]

    # Get task board (before execution, should be empty tasks)
    response = await fastapi_client.get(f"/v1/teams/{team_id}/task-board", timeout=30)

    assert response.status_code == 200

    data = response.json()
    assert "team_id" in data
    assert data["team_id"] == team_id
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
    # Before execution, task board should be empty since decomposition happens during execute
    assert len(data["tasks"]) == 0


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_task_board_nonexistent(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: GET /v1/teams/{team_id}/task-board for non-existent team returns 404.
    验证获取不存在的团队任务板返回 404。
    """
    response = await fastapi_client.get("/v1/teams/nonexistent_team_abc/task-board", timeout=10)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_execute_nonexistent(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/teams/{team_id}/execute for non-existent team returns 404.
    验证执行不存在的团队返回 404。
    """
    response = await fastapi_client.post(
        "/v1/teams/nonexistent_team_def/execute",
        json={"stream": False},
        timeout=10,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_execute_streaming(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/teams/{team_id}/execute with SSE streaming.
    验证团队执行返回 SSE 流事件。

    Note: This test requires Bedrock access and may be slow.
    """
    # Spawn a team
    spawn_resp = await fastapi_client.post(
        "/v1/teams/spawn",
        json={
            "user_request": "What is 2+2? Give a one-word answer.",
        },
        timeout=30,
    )
    assert spawn_resp.status_code == 200
    team_id = spawn_resp.json()["team_id"]

    try:
        async with fastapi_client.stream(
            "POST",
            f"/v1/teams/{team_id}/execute",
            json={"stream": True},
            timeout=120,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            events = []
            event_types = set()
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    event_types.add(event_type)
                elif line.startswith("data:") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[5:].strip())
                        events.append(data)
                    except json.JSONDecodeError:
                        pass

            # Should have received events
            assert len(events) >= 1, "Should receive at least some SSE events"

            # Verify expected event flow: team_spawned -> team_planning -> team_task_board -> ... -> team_complete
            assert "team_spawned" in event_types, \
                f"Missing team_spawned event. Got: {event_types}"

    except httpx.ReadTimeout:
        pytest.skip("Team execution timed out (may need Bedrock access)")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_spawn_with_context(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/teams/spawn with additional context.
    验证带上下文创建团队。
    """
    response = await fastapi_client.post(
        "/v1/teams/spawn",
        json={
            "user_request": "Review this function",
            "context": "The function is a sorting algorithm",
            "model": DEFAULT_TEST_MODEL,
        },
        timeout=30,
    )

    assert response.status_code == 200

    data = response.json()
    assert "team_id" in data
    assert data["status"] == "created"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teams_spawn_validation(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: POST /v1/teams/spawn with missing required field.
    验证缺少必填字段时返回 422。
    """
    # Missing user_request
    response = await fastapi_client.post(
        "/v1/teams/spawn",
        json={},
        timeout=10,
    )
    assert response.status_code == 422, \
        f"Expected 422 for missing user_request, got {response.status_code}"
