"""
Springo E2E Tests - Health Check
健康检查端点 E2E 测试
"""
import pytest
import httpx


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_health_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: FastAPI /health endpoint returns correct response.
    验证 FastAPI 健康检查端点工作正常。
    """
    response = await fastapi_client.get("/health")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data
    assert "framework" in data
    assert data["framework"] == "FastAPI"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_root_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: FastAPI root endpoint returns API info.
    验证 FastAPI 根端点返回 API 信息。
    """
    response = await fastapi_client.get("/")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "name" in data
    assert data["name"] == "Springo API"
    assert "version" in data
    assert "docs" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_openapi_schema(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: OpenAPI schema is accessible.
    验证 OpenAPI schema 可访问。
    """
    response = await fastapi_client.get("/openapi.json")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_docs_endpoint(fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Swagger docs endpoint is accessible.
    验证 Swagger 文档端点可访问。
    """
    response = await fastapi_client.get("/docs")
    
    # Should redirect or return HTML
    assert response.status_code in [200, 307]


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_health_comparison(flask_client: httpx.AsyncClient, fastapi_client: httpx.AsyncClient):
    """
    E2E Test: Compare Flask and FastAPI health endpoints.
    对比 Flask 和 FastAPI 健康检查端点响应。
    
    Note: This test requires both servers to be running.
    Skip if Flask server is not available.
    """
    try:
        flask_response = await flask_client.get("/health")
    except httpx.ConnectError:
        pytest.skip("Flask server not running")
        return
    
    fastapi_response = await fastapi_client.get("/health")
    
    # Both should return 200
    assert flask_response.status_code == 200
    assert fastapi_response.status_code == 200
    
    flask_data = flask_response.json()
    fastapi_data = fastapi_response.json()
    
    # Both should have status = healthy
    assert flask_data.get("status") == "healthy"
    assert fastapi_data.get("status") == "healthy"
    
    # FastAPI should indicate framework
    assert fastapi_data.get("framework") == "FastAPI"
