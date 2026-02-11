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
