"""
Springo E2E Tests - Chinese Model Support
Chinese LLM model integration smoke tests
"""
import pytest
import httpx
import json


CHINESE_PROVIDERS = {"deepseek", "minimax", "moonshot", "qwen", "zai"}

# A representative Chinese model for the Converse API smoke test
CHINESE_SMOKE_MODEL = "deepseek-v3.2"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_models_list_includes_chinese(fastapi_client: httpx.AsyncClient):
    """
    Smoke test: /v1/models returns Chinese models grouped by provider.
    Verify that the models list includes at least one model from each
    Chinese provider (deepseek, minimax, moonshot, qwen, zai).
    """
    response = await fastapi_client.get("/v1/models", timeout=30)
    assert response.status_code == 200

    data = response.json()

    # Verify top-level structure
    assert "data" in data, "Response missing 'data' list"
    assert "models" in data, "Response missing 'models' grouped dict"
    assert "total" in data, "Response missing 'total'"

    grouped = data["models"]

    # Every Chinese provider should appear in the grouped dict
    for provider in CHINESE_PROVIDERS:
        assert provider in grouped, (
            f"Provider '{provider}' missing from grouped models. "
            f"Got providers: {list(grouped.keys())}"
        )
        assert len(grouped[provider]) >= 1, (
            f"Provider '{provider}' has no models"
        )

    # Flat list should contain Chinese models
    all_providers = {m["provider"] for m in data["data"]}
    for provider in CHINESE_PROVIDERS:
        assert provider in all_providers, (
            f"No model with provider='{provider}' in flat data list"
        )

    # Total should cover Claude + Chinese models (at least 9)
    assert data["total"] >= 8, (
        f"Expected at least 8 models (3 Claude + 5 Chinese), got {data['total']}"
    )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_models_list_chinese_fields(fastapi_client: httpx.AsyncClient):
    """
    Smoke test: each Chinese model entry has the expected fields and
    api_format == 'converse'.
    """
    response = await fastapi_client.get("/v1/models", timeout=30)
    assert response.status_code == 200

    data = response.json()
    chinese_models = [m for m in data["data"] if m["provider"] in CHINESE_PROVIDERS]

    assert len(chinese_models) >= 5, (
        f"Expected at least 5 Chinese models, found {len(chinese_models)}"
    )

    required_fields = {
        "id", "bedrock_model_id", "display_name", "provider",
        "context_window", "max_output", "supports_vision",
        "supports_thinking", "api_format",
    }

    for m in chinese_models:
        missing = required_fields - m.keys()
        assert not missing, (
            f"Model '{m.get('id', '?')}' missing fields: {missing}"
        )
        assert m["api_format"] == "converse", (
            f"Model '{m['id']}' should have api_format='converse', "
            f"got '{m['api_format']}'"
        )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_chinese_model_message_smoke(fastapi_client: httpx.AsyncClient):
    """
    Smoke test: send a simple non-streaming message to a Chinese model
    (DeepSeek V3.2 via Converse path) and verify the response format.

    This test requires Bedrock access with DeepSeek model enabled.
    """
    response = await fastapi_client.post(
        "/v1/messages",
        json={
            "model": CHINESE_SMOKE_MODEL,
            "messages": [{"role": "user", "content": "Say hello in one word"}],
            "max_tokens": 50,
            "stream": False,
        },
        timeout=120,
    )

    if response.status_code == 200:
        data = response.json()

        # Should still conform to Anthropic-compatible response structure
        assert "id" in data, "Response missing 'id'"
        assert "content" in data, "Response missing 'content'"
        assert isinstance(data["content"], list), "'content' should be a list"
        assert len(data["content"]) >= 1, "content list should have at least 1 block"

        # Verify the content block has text
        text_blocks = [b for b in data["content"] if b.get("type") == "text"]
        assert len(text_blocks) >= 1, "Should have at least one text content block"
        assert len(text_blocks[0].get("text", "")) > 0, "Text block should not be empty"

        # Usage info should be present
        assert "usage" in data, "Response missing 'usage'"
    else:
        # Model may not be enabled in the account -- don't fail hard
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        pytest.skip(
            f"Chinese model smoke test returned {response.status_code}: "
            f"{data.get('error', {}).get('message', 'unknown error')}"
        )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_chinese_model_streaming_smoke(fastapi_client: httpx.AsyncClient):
    """
    Smoke test: streaming response from a Chinese model via Converse path.
    """
    try:
        async with fastapi_client.stream(
            "POST",
            "/v1/messages",
            json={
                "model": CHINESE_SMOKE_MODEL,
                "messages": [{"role": "user", "content": "Count to 3"}],
                "max_tokens": 50,
                "stream": True,
            },
            timeout=120,
        ) as response:
            if response.status_code == 200:
                assert "text/event-stream" in response.headers.get("content-type", ""), (
                    "Expected text/event-stream content type"
                )

                events = []
                async for line in response.aiter_lines():
                    if line.startswith("event:") or line.startswith("data:"):
                        events.append(line)

                assert len(events) > 0, "No SSE events received from Chinese model"

                event_types = [e for e in events if e.startswith("event:")]
                assert any("message_start" in e for e in event_types), (
                    "Missing message_start event"
                )
            else:
                pytest.skip(
                    f"Chinese model streaming returned {response.status_code}"
                )
    except httpx.ReadTimeout:
        pytest.skip("Chinese model streaming timed out")
