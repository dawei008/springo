"""
Springo E2E Test Configuration
E2E 测试配置和 fixtures
"""
import pytest
import httpx
from typing import AsyncGenerator
import os

# Server URL
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8081")

# Default test model — single constant to change when switching models
DEFAULT_TEST_MODEL = os.getenv("TEST_MODEL", "claude-sonnet-4-5-20250929")


@pytest.fixture
def fastapi_url() -> str:
    """FastAPI server URL"""
    return FASTAPI_URL


@pytest.fixture
async def fastapi_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for FastAPI server"""
    async with httpx.AsyncClient(base_url=FASTAPI_URL, timeout=60) as client:
        yield client


# Pytest configuration
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Async test configuration
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy"""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
