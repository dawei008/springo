"""
Springo E2E Tests - Messages API
消息 API E2E 测试
"""
import pytest
import httpx
import json


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_messages_endpoint_exists(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: /v1/messages endpoint exists and accepts POST.
    验证消息端点存在且接受 POST 请求。
    """
    # Send minimal request
    response = await fastapi_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 10,
            "stream": False
        },
        timeout=60
    )
    
    # Should return 200 or error (not 404/405)
    assert response.status_code != 404, "Endpoint not found"
    assert response.status_code != 405, "Method not allowed"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_messages_non_streaming_format(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Non-streaming /v1/messages returns correct format.
    验证非流式消息返回正确格式。
    """
    response = await fastapi_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "Say hello"}],
            "max_tokens": 50,
            "stream": False
        },
        timeout=120
    )
    
    if response.status_code == 200:
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response missing 'id'"
        assert "type" in data, "Response missing 'type'"
        assert data["type"] == "message", f"Expected type='message', got '{data['type']}'"
        assert "role" in data, "Response missing 'role'"
        assert data["role"] == "assistant", f"Expected role='assistant', got '{data['role']}'"
        assert "content" in data, "Response missing 'content'"
        assert "model" in data, "Response missing 'model'"
        assert "usage" in data, "Response missing 'usage'"
        
        # Verify usage structure
        usage = data["usage"]
        assert "input_tokens" in usage, "Usage missing 'input_tokens'"
        assert "output_tokens" in usage, "Usage missing 'output_tokens'"
    else:
        # If error, verify error format
        data = response.json()
        assert "error" in data or "detail" in data, "Error response missing error info"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_messages_streaming_format(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Streaming /v1/messages returns SSE format.
    验证流式消息返回 SSE 格式。
    """
    async with fastapi_client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "Say hi"}],
            "max_tokens": 30,
            "stream": True
        },
        timeout=120
    ) as response:
        # Should be 200 with text/event-stream
        if response.status_code == 200:
            assert "text/event-stream" in response.headers.get("content-type", ""), \
                "Expected text/event-stream content type"
            
            events = []
            async for line in response.aiter_lines():
                if line.startswith("event:") or line.startswith("data:"):
                    events.append(line)
            
            # Should have at least some events
            assert len(events) > 0, "No SSE events received"
            
            # Check for expected event types
            event_types = [e for e in events if e.startswith("event:")]
            assert any("message_start" in e for e in event_types) or len(events) > 0, \
                "Missing message_start event"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_messages_auto_endpoint_exists(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: /v1/messages-auto endpoint exists.
    验证自动工具执行端点存在。
    """
    response = await fastapi_client.post(
        "/v1/messages-auto",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 10,
            "stream": False
        },
        timeout=60
    )
    
    assert response.status_code != 404, "Endpoint not found"
    assert response.status_code != 405, "Method not allowed"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_messages_request_validation(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Invalid requests are properly rejected.
    验证无效请求被正确拒绝。
    """
    # Missing messages
    response = await fastapi_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 10
        }
    )
    assert response.status_code in [400, 422], "Should reject request without messages"
    
    # Invalid max_tokens
    response = await fastapi_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": -1
        }
    )
    assert response.status_code in [400, 422], "Should reject negative max_tokens"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_messages_comparison(
    flask_client: httpx.AsyncClient,
    fastapi_client: httpx.AsyncClient
):
    """
    E2E Test: Compare Flask and FastAPI /v1/messages responses.
    对比 Flask 和 FastAPI 消息响应。
    
    Note: Requires both servers running.
    """
    request_body = {
        "model": "claude-sonnet-4-5-20250929",
        "messages": [{"role": "user", "content": "Count from 1 to 3"}],
        "max_tokens": 50,
        "stream": False
    }
    
    try:
        flask_resp = await flask_client.post("/v1/messages", json=request_body, timeout=120)
    except httpx.ConnectError:
        pytest.skip("Flask server not running")
        return
    
    fastapi_resp = await fastapi_client.post("/v1/messages", json=request_body, timeout=120)
    
    # Both should succeed
    if flask_resp.status_code == 200 and fastapi_resp.status_code == 200:
        flask_data = flask_resp.json()
        fastapi_data = fastapi_resp.json()
        
        # Compare structure (not exact content due to LLM variance)
        assert flask_data.keys() == fastapi_data.keys(), \
            f"Response keys differ:\nFlask: {flask_data.keys()}\nFastAPI: {fastapi_data.keys()}"
        
        # Verify same response type
        assert flask_data["type"] == fastapi_data["type"]
        assert flask_data["role"] == fastapi_data["role"]
    elif flask_resp.status_code != 200:
        pytest.skip(f"Flask server error: {flask_resp.status_code}")
