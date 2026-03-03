# Springo FastAPI - Project Guide

## Project Overview

This is the FastAPI version of Springo, an AI assistant backend powered by Amazon Bedrock and multi-vendor direct APIs.

## Multi-Vendor Architecture Principle

Springo supports multiple model API platforms (Amazon Bedrock, DeepSeek Direct, etc.) via `VendorRouter`. When fixing bugs or adding features, always determine whether the issue is:

1. **Vendor-specific** — only affects one API platform (e.g., DeepSeek's max_tokens limit of 8192, Bedrock's Converse API quirks). Place the fix in the vendor's own service file (`bedrock.py`, `deepseek.py`, etc.) or use vendor-specific logic gated by `get_vendor(model)`.
2. **Universal** — affects all vendors (e.g., message format handling, session management, UI rendering). Place the fix in shared code (`vendor_router.py`, `messages.py`, `model_registry.py`, etc.).

Key files in the multi-vendor stack:
- `api/services/model_registry.py` — `vendor` field determines routing; `vendor_model_id` for native API IDs
- `api/services/vendor_router.py` — dispatches to correct service based on model's vendor
- `api/services/bedrock.py` — Amazon Bedrock (Anthropic API + Converse API)
- `api/services/deepseek.py` — DeepSeek direct API (OpenAI-compatible)
- Each vendor service handles its own: request conversion, response format, parameter clamping, error handling, retry logic

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│  Routers                                                     │
│  ├── messages.py    → /v1/messages, /v1/messages-auto       │
│  ├── tools.py       → /v1/tools/*                           │
│  ├── sessions.py    → /v1/sessions/*                        │
│  ├── context.py     → /v1/context/*                         │
│  ├── news.py        → /v1/news/*                            │
│  ├── images.py      → /v1/images/*                          │
│  └── health.py      → /health/*                             │
├─────────────────────────────────────────────────────────────┤
│  Services                                                    │
│  ├── bedrock.py     → Async Bedrock client (aioboto3)       │
│  ├── tool_manager.py → Async tool execution              │
│  └── session_store.py → Session persistence                 │
├─────────────────────────────────────────────────────────────┤
│  Models (Pydantic)                                           │
│  ├── requests.py    → MessageRequest, ToolExecuteRequest    │
│  └── responses.py   → MessageResponse, SSE events           │
├─────────────────────────────────────────────────────────────┤
│  Utils                                                       │
│  └── streaming.py   → SSE generator, event builder          │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app entry point, lifespan management |
| `api/config.py` | Pydantic Settings configuration |
| `api/services/bedrock.py` | Async Bedrock API client |
| `api/services/tool_manager.py` | Async tool manager with ThreadPoolExecutor |
| `api/routers/messages.py` | Core message handling with SSE streaming |

## Development Patterns

### Async/Await
All I/O operations use async/await:
```python
async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    result = await tool_manager.execute_tool(tool_name, tool_input)
    return result
```

### Dependency Injection
Use FastAPI's Depends for services:
```python
@router.post("/tools/execute")
async def execute_tool(
    request: ToolExecuteRequest,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    ...
```

### Pydantic Models
All request/response use Pydantic:
```python
class MessageRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: int = 4096
    stream: bool = False
```

### SSE Streaming
Use StreamingResponse with async generator:
```python
async def stream_response():
    async for chunk in bedrock.invoke_model_stream(...):
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(stream_response(), media_type="text/event-stream")
```

## Running Tests

```bash
# All API tests (pytest)
pytest tests/e2e/ -v

# Specific test file
pytest tests/e2e/test_messages.py -v

# With output
pytest tests/e2e/ -v -s

# Benchmarks only
pytest tests/e2e/test_benchmark.py -v -s
```

**Note:** `tests/e2e/` 中的 pytest 测试是 API 级别的接口测试。真正的 E2E 测试是在 Electron 客户端中进行的实际业务流程测试（对话、工具调用、会话管理等完整用户场景）。代码变更后应在 Electron 中进行实际业务验证。

## Common Tasks

### Add a new endpoint
1. Create model in `api/models/`
2. Add route in `api/routers/`
3. Include router in `api/main.py`
4. Add E2E test in `tests/e2e/`

### Add a new service
1. Create service in `api/services/`
2. Add to `api/services/__init__.py`
3. Initialize in `api/main.py` lifespan
4. Inject via Depends

## Environment Variables

| Variable | Default |
|----------|---------|
| SPRINGO_AWS_REGION | us-west-2 |
| SPRINGO_BEDROCK_MODEL_ID | anthropic.claude-sonnet-4-20250514-v1:0 |
| SPRINGO_PORT | 8081 |
| SPRINGO_DEBUG | true |

## E2E Test Results

```
42 tests passed
- Health: 5 tests
- Messages: 6 tests
- Tools: 10 tests
- Sessions: 4 tests
- Secondary (context/news/images): 11 tests
- Benchmarks: 7 tests
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Health endpoint | ~1,000 req/s |
| Tools list | ~450 req/s |
| Tool execution | ~170 req/s |
| Health latency | ~1.2ms |
