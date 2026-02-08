"""
Springo E2E Tests - Secondary Routes
辅助路由端点 E2E 测试 (context, news, images, health)
"""
import pytest
import httpx


# ============ Context Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_context_add_and_get(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Add and get context items.
    测试添加和获取上下文。
    """
    # Add context
    add_response = await fastapi_client.post("/v1/context/add", json={
        "items": [
            {"type": "text", "content": "This is some context", "name": "test_context"}
        ]
    })
    
    assert add_response.status_code == 200
    add_data = add_response.json()
    assert add_data["success"] == True
    assert add_data["added"] == 1
    
    # Get context
    get_response = await fastapi_client.get("/v1/context")
    
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert "items" in get_data
    assert "total" in get_data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_context_clear(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Clear context.
    测试清除上下文。
    """
    # Add some context first
    await fastapi_client.post("/v1/context/add", json={
        "items": [{"type": "text", "content": "Test"}]
    })
    
    # Clear context
    clear_response = await fastapi_client.delete("/v1/context")
    
    assert clear_response.status_code == 200
    clear_data = clear_response.json()
    assert clear_data["success"] == True


# ============ News Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_news_search_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: News search endpoint exists.
    测试新闻搜索端点存在。
    """
    response = await fastapi_client.post("/v1/news/search", json={
        "query": "technology",
        "count": 5
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert "success" in data
    assert "query" in data
    assert "articles" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_news_search_get_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: News search GET endpoint.
    测试新闻搜索 GET 端点。
    """
    response = await fastapi_client.get("/v1/news/search?query=AI&count=5")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "query" in data
    assert data["query"] == "AI"


# ============ Images Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_images_search_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Image search endpoint exists.
    测试图片搜索端点存在。
    """
    response = await fastapi_client.post("/v1/images/search", json={
        "query": "cat",
        "count": 5
    })
    
    assert response.status_code == 200
    
    data = response.json()
    assert "success" in data
    assert "query" in data
    assert "images" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_images_upload_and_get(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Upload image (base64 JSON) then retrieve it.
    测试图片上传（base64）和获取端点。
    """
    import base64
    # Create a tiny 1x1 red PNG for testing
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )
    image_b64 = base64.b64encode(png_bytes).decode('utf-8')

    # Upload
    upload_resp = await fastapi_client.post("/v1/images/upload", json={
        "session_id": "test-session-images",
        "image_data": image_b64,
        "media_type": "image/png"
    })
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert "image_id" in upload_data
    assert "filename" in upload_data
    assert upload_data["media_type"] == "image/png"
    assert upload_data["size"] > 0

    # Retrieve as binary
    filename = upload_data["filename"]
    get_resp = await fastapi_client.get(f"/v1/images/test-session-images/{filename}")
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"] == "image/png"
    assert len(get_resp.content) == upload_data["size"]

    # Retrieve as base64
    get_b64_resp = await fastapi_client.get(f"/v1/images/test-session-images/{filename}?format=base64")
    assert get_b64_resp.status_code == 200
    b64_data = get_b64_resp.json()
    assert b64_data["media_type"] == "image/png"
    assert b64_data["data"] == image_b64

    # Non-existent image
    not_found = await fastapi_client.get("/v1/images/test-session-images/nonexistent.png")
    assert not_found.status_code == 404


# ============ Health Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_health_detailed_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Detailed health check endpoint.
    测试详细健康检查端点。
    """
    response = await fastapi_client.get("/health/detailed")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "system" in data
    assert data["status"] in ["healthy", "degraded"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_health_ready_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Readiness check endpoint.
    测试就绪检查端点。
    """
    response = await fastapi_client.get("/health/ready")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "ready" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_health_live_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Liveness check endpoint.
    测试存活检查端点。
    """
    response = await fastapi_client.get("/health/live")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "alive" in data
    assert data["alive"] == True


# ============ OpenAPI Schema Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_all_routes_in_openapi(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: All routes are documented in OpenAPI schema.
    测试所有路由都在 OpenAPI schema 中。
    """
    response = await fastapi_client.get("/openapi.json")
    
    assert response.status_code == 200
    
    data = response.json()
    paths = data.get("paths", {})
    
    # 验证关键路由存在
    expected_paths = [
        "/v1/messages",
        "/v1/messages-auto",
        "/v1/tools/execute",
        "/v1/tools",
        "/v1/sessions",
        "/v1/context",
        "/v1/context/add",
        "/v1/news/search",
        "/v1/images/search",
        "/health",
        "/health/detailed",
        "/v1/terminal/execute",
        "/v1/terminal/kill/{pid}",
        "/v1/teams/spawn",
        "/v1/teams/{team_id}",
        "/v1/teams/{team_id}/execute",
        "/v1/teams/{team_id}/task-board",
    ]
    
    for path in expected_paths:
        assert path in paths, f"Expected path {path} not found in OpenAPI schema"
