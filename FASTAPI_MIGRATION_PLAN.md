# Flask to FastAPI 重构计划

## 概述

将 Springo 后端从 Flask 迁移到 FastAPI，实现真正的异步处理，提升性能和代码质量。

---

## 阶段一：项目结构重组

### 目标目录结构

```
springo/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理
│   ├── dependencies.py         # 依赖注入
│   │
│   ├── routers/                # 路由模块
│   │   ├── __init__.py
│   │   ├── messages.py         # /v1/messages, /v1/messages-auto
│   │   ├── sessions.py         # /v1/sessions/*
│   │   ├── tools.py            # /v1/tools/*
│   │   ├── context.py          # /v1/context/*
│   │   ├── images.py           # /v1/images/*
│   │   ├── news.py             # /v1/news/*
│   │   └── health.py           # /health
│   │
│   ├── services/               # 业务逻辑
│   │   ├── __init__.py
│   │   ├── bedrock.py          # Bedrock API 客户端
│   │   ├── mcp_manager.py      # MCP 工具管理
│   │   ├── session_store.py    # 会话存储
│   │   ├── context_manager.py  # 上下文管理
│   │   └── news_agent.py       # News Agent
│   │
│   ├── models/                 # Pydantic 模型
│   │   ├── __init__.py
│   │   ├── requests.py         # 请求模型
│   │   ├── responses.py        # 响应模型
│   │   └── schemas.py          # 通用模型
│   │
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── streaming.py        # SSE 流处理
│       └── helpers.py          # 辅助函数
│
├── mcp_tools/                  # 保持现有结构
│   ├── __init__.py
│   ├── core.py
│   ├── schemas.py
│   └── handlers/
│
├── springo-app/                # Electron 前端（不变）
│
├── full_proxy_server.py        # 保留作为参考，最终删除
├── run.py                      # 新启动脚本
└── requirements.txt            # 更新依赖
```

---

## 阶段二：核心模块迁移

### 2.1 配置管理 (api/config.py)

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # AWS
    aws_region: str = "us-west-2"
    bedrock_model_id: str = "anthropic.claude-sonnet-4-20250514-v1:0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = True

    # Paths
    springo_config_dir: str = "~/.springo"
    session_storage_dir: str = "~/.springo/sessions"

    # MCP
    mcp_config_path: str = "~/.springo/mcp_servers.json"

    class Config:
        env_prefix = "SPRINGO_"
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 2.2 Bedrock 异步客户端 (api/services/bedrock.py)

```python
import aioboto3
from typing import AsyncGenerator
from botocore.config import Config

class BedrockService:
    def __init__(self, region: str = "us-west-2"):
        self.region = region
        self.session = aioboto3.Session()
        self.config = Config(
            read_timeout=300,
            retries={'max_attempts': 3}
        )

    async def invoke_model_stream(
        self,
        model_id: str,
        body: dict
    ) -> AsyncGenerator[dict, None]:
        """异步流式调用 Bedrock"""
        async with self.session.client(
            'bedrock-runtime',
            region_name=self.region,
            config=self.config
        ) as client:
            response = await client.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(body),
                contentType='application/json'
            )

            async for event in response['body']:
                if 'chunk' in event:
                    chunk_data = json.loads(event['chunk']['bytes'].decode())
                    yield chunk_data

    async def invoke_model(self, model_id: str, body: dict) -> dict:
        """异步非流式调用"""
        async with self.session.client(
            'bedrock-runtime',
            region_name=self.region,
            config=self.config
        ) as client:
            response = await client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType='application/json'
            )
            return json.loads(await response['body'].read())
```

### 2.3 SSE 流式响应 (api/utils/streaming.py)

```python
from fastapi import Response
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json

async def sse_generator(
    bedrock: BedrockService,
    model_id: str,
    request_body: dict
) -> AsyncGenerator[str, None]:
    """生成 SSE 格式的流式响应"""
    try:
        async for chunk in bedrock.invoke_model_stream(model_id, request_body):
            event_type = chunk.get('type', 'unknown')
            yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"

        yield "event: done\ndata: {}\n\n"

    except Exception as e:
        error_data = {"type": "error", "error": str(e)}
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

def create_sse_response(generator: AsyncGenerator) -> StreamingResponse:
    """创建 SSE 响应"""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

### 2.4 消息路由 (api/routers/messages.py)

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from ..services.bedrock import BedrockService
from ..services.mcp_manager import MCPManager
from ..models.requests import MessageRequest
from ..dependencies import get_bedrock, get_mcp_manager

router = APIRouter(prefix="/v1", tags=["messages"])

@router.post("/messages")
async def create_message(
    request: MessageRequest,
    bedrock: BedrockService = Depends(get_bedrock),
    mcp: MCPManager = Depends(get_mcp_manager)
):
    """流式消息接口 - 对应原 /v1/messages"""

    # 准备请求体
    body = await prepare_bedrock_body(request, mcp)

    if request.stream:
        # 流式响应
        async def generate():
            async for chunk in bedrock.invoke_model_stream(
                request.model,
                body
            ):
                # 处理工具调用
                if chunk.get('type') == 'tool_use':
                    tool_result = await mcp.execute_tool(chunk)
                    yield format_sse_event('tool_result', tool_result)
                else:
                    yield format_sse_event(chunk['type'], chunk)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    else:
        # 非流式响应
        result = await bedrock.invoke_model(request.model, body)
        return result

@router.post("/messages-auto")
async def create_message_auto(
    request: MessageRequest,
    bedrock: BedrockService = Depends(get_bedrock),
    mcp: MCPManager = Depends(get_mcp_manager)
):
    """自动工具循环接口 - 对应原 /v1/messages-auto"""

    messages = request.messages.copy()
    max_iterations = 50

    for _ in range(max_iterations):
        body = await prepare_bedrock_body_with_messages(request, messages, mcp)

        if request.stream:
            # 流式处理...
            pass
        else:
            result = await bedrock.invoke_model(request.model, body)

            # 检查是否有工具调用
            tool_uses = extract_tool_uses(result)
            if not tool_uses:
                return result

            # 并行执行所有工具
            tool_results = await asyncio.gather(*[
                mcp.execute_tool(tu) for tu in tool_uses
            ])

            # 添加到消息历史
            messages.append({"role": "assistant", "content": result['content']})
            messages.append({"role": "user", "content": tool_results})

    return {"error": "Max iterations reached"}
```

---

## 阶段三：MCP 工具异步化

### 3.1 MCP 管理器 (api/services/mcp_manager.py)

```python
import asyncio
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

class MCPManager:
    def __init__(self):
        self.tools: Dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)

    async def execute_tool(self, tool_use: dict) -> dict:
        """异步执行工具"""
        tool_name = tool_use['name']
        tool_input = tool_use['input']

        # MCP 工具可能是同步的，用线程池执行
        result = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self._execute_sync,
            tool_name,
            tool_input
        )

        return {
            "type": "tool_result",
            "tool_use_id": tool_use['id'],
            "content": result
        }

    def _execute_sync(self, tool_name: str, tool_input: dict) -> str:
        """同步执行工具（在线程池中运行）"""
        # 调用现有的 mcp_tools 处理逻辑
        from mcp_tools import execute_tool
        return execute_tool(tool_name, tool_input)

    async def execute_tools_parallel(
        self,
        tool_uses: List[dict]
    ) -> List[dict]:
        """并行执行多个工具"""
        return await asyncio.gather(*[
            self.execute_tool(tu) for tu in tool_uses
        ])
```

---

## 阶段四：Pydantic 模型定义

### 4.1 请求模型 (api/models/requests.py)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class MessageContent(BaseModel):
    type: str
    text: Optional[str] = None
    source: Optional[Dict[str, Any]] = None

class Message(BaseModel):
    role: str
    content: str | List[MessageContent]

class MessageRequest(BaseModel):
    model: str = "anthropic.claude-sonnet-4-20250514-v1:0"
    max_tokens: int = Field(default=4096, ge=1, le=200000)
    temperature: float = Field(default=0.7, ge=0, le=1)
    messages: List[Message]
    system: Optional[str] = None
    stream: bool = True
    tools: Optional[List[Dict[str, Any]]] = None

    # Springo 扩展字段
    session_id: Optional[str] = None
    compact_model: Optional[str] = None

class ToolExecuteRequest(BaseModel):
    name: str
    input: Dict[str, Any]
    session_id: Optional[str] = None
```

### 4.2 响应模型 (api/models/responses.py)

```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ToolResult(BaseModel):
    type: str = "tool_result"
    tool_use_id: str
    content: str | Dict[str, Any]

class MessageResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    content: List[Dict[str, Any]]
    model: str
    stop_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None

class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None
```

---

## 阶段五：迁移步骤

### Step 1: 环境准备 (Day 1)

```bash
# 安装依赖
pip install fastapi uvicorn aioboto3 pydantic-settings httpx

# 更新 requirements.txt
cat >> requirements.txt << EOF
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
aioboto3>=12.0.0
pydantic-settings>=2.0.0
httpx>=0.26.0
EOF
```

### Step 2: 创建基础结构 (Day 1)

1. 创建目录结构
2. 实现 config.py
3. 实现 main.py 基础框架
4. 添加 health 路由验证运行

### Step 3: 迁移核心路由 (Day 2-3)

按优先级迁移：

| 优先级 | 路由 | 复杂度 | 说明 |
|--------|------|--------|------|
| P0 | /health | 低 | 验证基础设施 |
| P0 | /v1/messages | 高 | 核心流式接口 |
| P0 | /v1/messages-auto | 高 | 自动工具循环 |
| P1 | /v1/tools/execute | 中 | MCP 工具执行 |
| P1 | /v1/sessions/* | 低 | 会话 CRUD |
| P2 | /v1/context/* | 中 | 上下文管理 |
| P2 | /v1/news/* | 中 | News Agent |
| P3 | /v1/images/* | 低 | 图片处理 |

### Step 4: 并行运行测试 (Day 4)

```python
# run.py - 开发时可同时运行两个服务
import uvicorn
from api.main import app

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8081,  # 新端口，与 Flask 8080 并存
        reload=True
    )
```

### Step 5: 前端切换 (Day 5)

```javascript
// springo-app/renderer/js/app.js
// 修改 BASE_URL
const BASE_URL = 'http://localhost:8081';  // FastAPI
// const BASE_URL = 'http://localhost:8080';  // Flask (备用)
```

### Step 6: 清理与优化 (Day 6)

1. 删除 full_proxy_server.py
2. 更新启动脚本
3. 性能测试
4. 文档更新

---

## 阶段六：测试策略

### 6.1 API 兼容性测试

```python
# tests/test_api_compatibility.py
import pytest
import httpx

FLASK_URL = "http://localhost:8080"
FASTAPI_URL = "http://localhost:8081"

@pytest.mark.asyncio
async def test_messages_endpoint_compatibility():
    """确保两个服务返回相同格式"""
    request_body = {
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": False
    }

    async with httpx.AsyncClient() as client:
        flask_resp = await client.post(f"{FLASK_URL}/v1/messages", json=request_body)
        fastapi_resp = await client.post(f"{FASTAPI_URL}/v1/messages", json=request_body)

        # 比较响应结构
        assert flask_resp.status_code == fastapi_resp.status_code
        assert set(flask_resp.json().keys()) == set(fastapi_resp.json().keys())
```

### 6.2 性能基准测试

```python
# tests/benchmark.py
import asyncio
import time
import httpx

async def benchmark_concurrent_requests(url: str, n: int = 10):
    """并发请求测试"""
    async with httpx.AsyncClient(timeout=60) as client:
        start = time.time()

        tasks = [
            client.post(f"{url}/v1/messages", json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": f"Count to {i}"}],
                "stream": False
            })
            for i in range(n)
        ]

        responses = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        print(f"{url}: {n} requests in {elapsed:.2f}s ({n/elapsed:.2f} req/s)")
        return elapsed

# 运行: python -m pytest tests/benchmark.py -v
```

---

## 风险与回滚

### 回滚策略

1. **Git Tag**: `pre-fastapi-refactor` 已创建
2. **并行运行**: 两个服务可同时运行在不同端口
3. **前端切换**: 只需修改 `BASE_URL` 即可切换

### 已知风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| aioboto3 不稳定 | 高 | 保留同步 boto3 回退方案 |
| SSE 格式差异 | 高 | 严格测试前端兼容性 |
| MCP 同步阻塞 | 中 | 使用线程池隔离 |
| 全局状态丢失 | 中 | 迁移到 Redis 或文件存储 |

---

## 时间估算

| 阶段 | 预计时间 | 说明 |
|------|----------|------|
| 项目结构 | 0.5 天 | 创建目录和基础文件 |
| 核心迁移 | 2 天 | messages, tools 路由 |
| 辅助迁移 | 1 天 | sessions, context, news |
| 测试验证 | 1 天 | 兼容性和性能测试 |
| 清理优化 | 0.5 天 | 删除旧代码，文档更新 |
| **总计** | **5 天** | |

---

## 执行进度

### Phase 1: Project Structure Setup - COMPLETED (2026-02-06 22:37)

### Phase 2: Core Module Migration - COMPLETED (2026-02-06 22:50)

| Task | Status | Notes |
|------|--------|-------|
| 2.1 Pydantic Models | DONE | requests.py, responses.py with all models |
| 2.2 Bedrock Service | DONE | Async client with aioboto3 |
| 2.3 SSE Streaming | DONE | streaming.py with SSEEventBuilder |
| 2.4 Messages Router | DONE | /v1/messages and /v1/messages-auto |
| 2.5 Request Validation | DONE | 422 errors for invalid requests |
| E2E Tests | DONE | 11/11 tests passed |

Files created:
- api/models/requests.py
- api/models/responses.py
- api/services/bedrock.py
- api/utils/streaming.py
- api/routers/messages.py
- tests/e2e/test_messages.py

| Task | Status | Notes |
|------|--------|-------|
| 1.1 Directory structure | DONE | api/routers/services/models/utils created |
| 1.2 config.py | DONE | Pydantic Settings with SPRINGO_* prefix |
| 1.3 main.py | DONE | FastAPI app with lifespan, CORS, health endpoint |
| 1.4 dependencies.py | DONE | Dependency injection framework |
| 1.5 requirements.txt | DONE | FastAPI, aioboto3, pytest dependencies |
| 1.6 E2E test infrastructure | DONE | tests/e2e/conftest.py, test_health.py |
| 1.7 Verify startup | DONE | uvicorn running on port 8081 |
| 1.8 E2E tests | DONE | 5/5 tests passed |

---

## 下一步

准备好开始后，执行以下命令：

```bash
# 创建新分支
git checkout -b feature/fastapi-migration

# 创建目录结构
mkdir -p api/{routers,services,models,utils}
touch api/__init__.py api/main.py api/config.py api/dependencies.py
```

要开始实施吗？
