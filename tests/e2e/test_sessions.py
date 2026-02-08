"""
Springo E2E Tests - Sessions API
会话管理端点 E2E 测试
"""
import pytest
import httpx
import uuid


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sessions_list_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: /v1/sessions endpoint returns session list.
    验证会话列表端点工作正常。
    """
    response = await fastapi_client.get("/v1/sessions")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "sessions" in data
    assert "total" in data
    assert isinstance(data["sessions"], list)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sessions_crud(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Session CRUD operations.
    测试会话的创建、读取、更新、删除。
    """
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    
    # Create session
    create_response = await fastapi_client.post(f"/v1/sessions/{session_id}", json={
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ],
        "metadata": {"title": "Test Session"}
    })
    
    assert create_response.status_code == 200
    create_data = create_response.json()
    assert create_data["success"] == True
    assert create_data["session_id"] == session_id
    assert create_data["message_count"] == 2
    
    # Read session
    read_response = await fastapi_client.get(f"/v1/sessions/{session_id}")
    
    assert read_response.status_code == 200
    read_data = read_response.json()
    assert read_data["session_id"] == session_id
    assert len(read_data["messages"]) == 2
    
    # Delete session
    delete_response = await fastapi_client.delete(f"/v1/sessions/{session_id}")
    
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["success"] == True
    
    # Verify deleted
    verify_response = await fastapi_client.get(f"/v1/sessions/{session_id}")
    assert verify_response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sessions_hash_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Session hash generation.
    测试会话哈希生成。
    """
    response = await fastapi_client.post("/v1/sessions/hash", json={
        "working_dir": "/Users/test/project"
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert "hash" in data
    assert "working_dir" in data
    assert len(data["hash"]) == 12  # MD5 前 12 位


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sessions_not_found(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Non-existent session returns 404.
    测试访问不存在的会话返回 404。
    """
    response = await fastapi_client.get("/v1/sessions/nonexistent_session_12345")
    
    assert response.status_code == 404
