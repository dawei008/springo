"""
Springo E2E Test Configuration
E2E 测试配置和 fixtures
"""
import pytest
import httpx
from typing import AsyncGenerator
import json
import os

# Server URLs
FLASK_URL = os.getenv("FLASK_URL", "http://localhost:8080")
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8081")

# Default test model — single constant to change when switching models
DEFAULT_TEST_MODEL = os.getenv("TEST_MODEL", "claude-sonnet-4-5-20250929")


@pytest.fixture
def flask_url() -> str:
    """Flask server URL"""
    return FLASK_URL


@pytest.fixture
def fastapi_url() -> str:
    """FastAPI server URL"""
    return FASTAPI_URL


@pytest.fixture
async def flask_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for Flask server"""
    async with httpx.AsyncClient(base_url=FLASK_URL, timeout=60) as client:
        yield client


@pytest.fixture
async def fastapi_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for FastAPI server"""
    async with httpx.AsyncClient(base_url=FASTAPI_URL, timeout=60) as client:
        yield client


@pytest.fixture
def compare_responses():
    """
    Factory fixture for comparing Flask and FastAPI responses.
    Ignores specified keys (like 'id', 'created' which vary between requests).
    """
    def _compare(flask_resp: httpx.Response, fastapi_resp: httpx.Response, ignore_keys: list = None):
        ignore_keys = ignore_keys or []
        
        # Compare status codes
        assert flask_resp.status_code == fastapi_resp.status_code, \
            f"Status code mismatch: Flask={flask_resp.status_code}, FastAPI={fastapi_resp.status_code}"
        
        # Compare JSON responses
        try:
            flask_json = flask_resp.json()
            fastapi_json = fastapi_resp.json()
        except json.JSONDecodeError:
            # If not JSON, compare raw content
            assert flask_resp.text == fastapi_resp.text
            return
        
        # Remove ignored keys
        def remove_keys(obj, keys):
            if isinstance(obj, dict):
                return {k: remove_keys(v, keys) for k, v in obj.items() if k not in keys}
            elif isinstance(obj, list):
                return [remove_keys(item, keys) for item in obj]
            return obj
        
        flask_json = remove_keys(flask_json, ignore_keys)
        fastapi_json = remove_keys(fastapi_json, ignore_keys)
        
        assert flask_json == fastapi_json, \
            f"Response mismatch:\nFlask: {json.dumps(flask_json, indent=2)}\nFastAPI: {json.dumps(fastapi_json, indent=2)}"
    
    return _compare


@pytest.fixture
def compare_sse_events():
    """
    Factory fixture for comparing SSE event streams.
    Compares event types and structure, not exact content (due to LLM variance).
    """
    def _compare(flask_events: list, fastapi_events: list):
        # Filter out empty lines and [DONE] markers
        def parse_events(events):
            parsed = []
            for event in events:
                if event.startswith("data:") and event != "data: [DONE]":
                    try:
                        data = json.loads(event[5:].strip())
                        parsed.append(data)
                    except json.JSONDecodeError:
                        pass
            return parsed
        
        flask_parsed = parse_events(flask_events)
        fastapi_parsed = parse_events(fastapi_events)
        
        # Compare event count and types
        assert len(flask_parsed) > 0, "Flask returned no events"
        assert len(fastapi_parsed) > 0, "FastAPI returned no events"
        
        # Compare event types
        flask_types = [e.get("type") for e in flask_parsed if "type" in e]
        fastapi_types = [e.get("type") for e in fastapi_parsed if "type" in e]
        
        # Event types should match (order may vary slightly due to async)
        assert set(flask_types) == set(fastapi_types), \
            f"Event types mismatch:\nFlask: {flask_types}\nFastAPI: {fastapi_types}"
    
    return _compare


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
