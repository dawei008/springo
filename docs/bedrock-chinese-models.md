# Amazon Bedrock 国产大模型一览

> 更新时间：2026-02-10 | 数据来源：`aws bedrock list-foundation-models` (us-west-2) + 官方文档

## 模型总览

| 厂商 | 模型名称 | Model ID | 上下文窗口 | 最大输出 | 输入模态 | 架构 | 推理类型 |
|---|---|---|---|---|---|---|---|
| **DeepSeek** | DeepSeek V3.2 | `deepseek.v3.2` | 128K | 64K | 文本 | 671B MoE (37B active) | ON_DEMAND |
| **DeepSeek** | DeepSeek V3.1 | `deepseek.v3-v1:0` | 128K | 32K | 文本 | 671B MoE (37B active) | ON_DEMAND |
| **DeepSeek** | DeepSeek R1 | `deepseek.r1-v1:0` | 128K | 32K (建议≤8K) | 文本 | 671B MoE (37B active) | INFERENCE_PROFILE |
| **MiniMax** | MiniMax M2.1 | `minimax.minimax-m2.1` | 200K | ~200K | 文本 | 230B MoE (10B active) | ON_DEMAND |
| **MiniMax** | MiniMax M2 | `minimax.minimax-m2` | 204K | ~204K | 文本 | 230B MoE (10B active) | ON_DEMAND |
| **Moonshot AI** | Kimi K2.5 | `moonshotai.kimi-k2.5` | 256K | - | 文本+图片 | 1T MoE (32B active) | ON_DEMAND |
| **Moonshot AI** | Kimi K2 Thinking | `moonshot.kimi-k2-thinking` | 256K | - | 文本 | 1T MoE (32B active) | ON_DEMAND |
| **Qwen** | Qwen3 Coder 480B | `qwen.qwen3-coder-480b-a35b-v1:0` | 256K (可扩展至1M) | - | 文本 | 480B MoE (35B active) | ON_DEMAND |
| **Qwen** | Qwen3 235B A22B | `qwen.qwen3-235b-a22b-2507-v1:0` | 32K (可扩展至1M) | - | 文本 | 235B MoE (22B active) | ON_DEMAND |
| **Qwen** | Qwen3 VL 235B | `qwen.qwen3-vl-235b-a22b` | 32K | - | 文本+图片 | 235B MoE (22B active) | ON_DEMAND |
| **Qwen** | Qwen3 Next 80B | `qwen.qwen3-next-80b-a3b` | 256K | - | 文本 | 80B MoE (3B active) | ON_DEMAND |
| **Qwen** | Qwen3 Coder 30B | `qwen.qwen3-coder-30b-a3b-v1:0` | 256K | - | 文本 | 30B MoE (3B active) | ON_DEMAND |
| **Qwen** | Qwen3 32B (dense) | `qwen.qwen3-32b-v1:0` | 32K | - | 文本 | 32B Dense | ON_DEMAND |
| **Z.AI (智谱)** | GLM 4.7 | `zai.glm-4.7` | 200K | 128K | 文本 | 358B MoE | ON_DEMAND |
| **Z.AI (智谱)** | GLM 4.7 Flash | `zai.glm-4.7-flash` | 200K | 128K | 文本 | 轻量版 | ON_DEMAND |

> **注**：所有模型均支持 Streaming，状态均为 ACTIVE。us-east-1 额外支持 `qwen.qwen3-coder-next`。

## 区域可用性 (us-west-2)

| 模型 | 单区域支持 | 跨区域推理 |
|---|---|---|
| DeepSeek V3.2 | us-west-2 等多个区域 | - |
| DeepSeek V3.1 | us-west-2, us-east-2, ap-northeast-1 等 | - |
| DeepSeek R1 | - | us-east-1, us-east-2, us-west-2 |
| MiniMax M2 / M2.1 | us-west-2, us-east-1, us-east-2 等 | - |
| Kimi K2.5 | us-west-2 等（新增） | - |
| Kimi K2 Thinking | us-west-2, us-east-1, us-east-2 等 | - |
| Qwen3 系列 | us-west-2, us-east-2, ap-northeast-1 等 | - |
| GLM 4.7 / Flash | us-west-2 等（新增） | - |

## API 调用方式

所有模型均支持两种 API：

### 1. Converse API（推荐，统一格式）

```python
import boto3

client = boto3.client("bedrock-runtime", region_name="us-west-2")

response = client.converse(
    modelId="deepseek.v3.2",  # 直接使用 model ID
    system=[{"text": "你是一个有帮助的助手"}],
    messages=[
        {
            "role": "user",
            "content": [{"text": "你好，请介绍一下你自己"}]
        }
    ],
    inferenceConfig={
        "temperature": 0.7,
        "topP": 0.9,
        "maxTokens": 4096,
    }
)

# 输出
output = response["output"]["message"]["content"]
for block in output:
    if "text" in block:
        print(block["text"])
    if "reasoningContent" in block:  # DeepSeek R1 / Kimi K2 Thinking
        print("思考过程:", block["reasoningContent"]["reasoningText"])

# Token 用量
usage = response["usage"]
print(f"输入: {usage['inputTokens']}, 输出: {usage['outputTokens']}")
```

**Streaming 版本：**

```python
response = client.converse_stream(
    modelId="deepseek.v3.2",
    messages=[{"role": "user", "content": [{"text": "你好"}]}],
    inferenceConfig={"maxTokens": 4096}
)

for event in response["stream"]:
    if "contentBlockDelta" in event:
        delta = event["contentBlockDelta"]["delta"]
        if "text" in delta:
            print(delta["text"], end="", flush=True)
```

### 2. InvokeModel API（原生格式，模型特定）

```python
import json

# DeepSeek 原生格式
body = json.dumps({
    "prompt": "<｜begin▁of▁sentence｜><｜User｜>你好<｜Assistant｜>",
    "max_tokens": 4096,
    "temperature": 0.7,
    "top_p": 0.9,
})

response = client.invoke_model(modelId="deepseek.v3.2", body=body)
result = json.loads(response["body"].read())
print(result["choices"][0]["text"])
```

### 3. 跨区域推理（DeepSeek R1 必须使用）

```python
# DeepSeek R1 仅支持 INFERENCE_PROFILE，需要加区域前缀
response = client.converse(
    modelId="us.deepseek.r1-v1:0",  # 注意 "us." 前缀
    messages=[{"role": "user", "content": [{"text": "证明根号2是无理数"}]}],
    inferenceConfig={"maxTokens": 8192}
)
```

## 多模态模型（图片输入）

支持图片输入的模型：**Kimi K2.5** 和 **Qwen3 VL 235B**

```python
import base64

with open("image.jpg", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.converse(
    modelId="moonshotai.kimi-k2.5",
    messages=[{
        "role": "user",
        "content": [
            {"image": {"format": "jpeg", "source": {"bytes": image_data}}},
            {"text": "描述这张图片的内容"}
        ]
    }],
    inferenceConfig={"maxTokens": 4096}
)
```

## 推理/思考模型

具有推理能力（thinking）的模型：**DeepSeek R1** 和 **Kimi K2 Thinking**

这些模型的响应会包含 `reasoningContent` 块，展示模型的推理过程：

```python
response = client.converse(
    modelId="moonshot.kimi-k2-thinking",
    messages=[{"role": "user", "content": [{"text": "9.11和9.9哪个大"}]}],
    inferenceConfig={"maxTokens": 8192}
)

for block in response["output"]["message"]["content"]:
    if "reasoningContent" in block:
        print("[思考]", block["reasoningContent"]["reasoningText"])
    elif "text" in block:
        print("[回答]", block["text"])
```

> **DeepSeek R1 注意事项**：虽然 API 接受最大 32,768 tokens 输出，但官方建议 `max_tokens` 不超过 8,192，超出后质量明显下降。

## 编程专用模型

| 模型 | SWE-bench | 特点 |
|---|---|---|
| Qwen3 Coder 480B | ~61.8% | 最强编程 MoE，256K 上下文，支持 agentic coding |
| Qwen3 Coder 30B | - | 轻量编程模型，适合成本敏感场景 |
| GLM 4.7 | ~73.8% | 原生 Deep Thinking，"Vibe Coding" |
| MiniMax M2.1 | ~74% | 10B active 参数，性价比极高 |
| Kimi K2.5 | - | 多模态 + Agent，支持 Swarm Mode |

## 依赖配置

```bash
pip install boto3>=1.35.0
```

```python
# 确保 AWS 凭证已配置
# 方式 1: 环境变量
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_DEFAULT_REGION=us-west-2

# 方式 2: AWS CLI profile
aws configure --profile bedrock
```

---

## Springo 中 Claude 模型强绑定分析

当前 springo 代码库**深度绑定 Claude/Anthropic 模型**，若要接入上述国产模型需要逐一解耦。以下是全部绑定点：

### 1. 默认模型 ID 硬编码

| 文件 | 行号 | 硬编码值 | 说明 |
|---|---|---|---|
| `api/config.py` | 18 | `anthropic.claude-sonnet-4-20250514-v1:0` | 后端全局默认模型 |
| `api/models/requests.py` | 69 | `claude-opus-4-6` | 消息请求默认模型 |
| `api/services/bedrock.py` | 422 | `claude-opus-4-6` | Bedrock 请求转换 fallback |
| `api/models/teams.py` | 15 | `claude-haiku-4-5-20251001` | Agent 角色默认模型 |
| `api/models/teams.py` | 62 | `claude-sonnet-4-5-20250929` | Team Orchestrator 模型 |
| `api/models/teams.py` | 75-125 | 多个 Claude 模型 | 5 个预定义角色各自硬编码 |

### 2. MODEL_REGISTRY 仅包含 Claude 模型

**`api/services/bedrock.py:31-108`** — 模型注册表只有 12 个 Anthropic 模型：

```
claude-opus-4-6          → us.anthropic.claude-opus-4-6-v1
claude-opus-4-5-20251101 → us.anthropic.claude-opus-4-5-20251101-v1:0
claude-sonnet-4-5-20250929 → us.anthropic.claude-sonnet-4-5-20250929-v1:0
claude-haiku-4-5-20251001  → us.anthropic.claude-haiku-4-5-20251001-v1:0
... (共 12 个，全部是 Claude)
```

**不包含任何国产模型**。需要扩展注册表加入 DeepSeek、Qwen、Kimi 等。

### 3. 前端 UI 模型选择 — 仅暴露 Claude

**`api/routers/models.py:17-22`**:

```python
_UI_MODELS = [
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]
```

用户在 UI 只能选择这 4 个 Claude 模型。

### 4. Fallback 逻辑假定 Anthropic 命名

| 文件 | 行号 | 代码 |
|---|---|---|
| `api/services/bedrock.py` | 407 | `f"us.anthropic.{model}-v1:0"` |
| `api/services/context_manager.py` | 626 | `f"us.anthropic.{_compact_model_id}-v1:0"` |

未知模型名会被拼接成 `us.anthropic.xxx` 格式，国产模型 ID 传入会生成无效的 Bedrock model ID。

### 5. `anthropic_version` 硬编码

以下位置硬编码了 Anthropic 专有的 API 版本参数：

| 文件 | 行号 | 值 |
|---|---|---|
| `api/services/bedrock.py` | 426 | `"bedrock-2023-05-31"` |
| `api/routers/terminal.py` | 192 | `"bedrock-2023-05-31"` |
| `api/routers/news.py` | 175, 255 | `"2023-06-01"` / `"bedrock-2023-05-31"` |
| `api/services/agent_team_manager.py` | 330, 432, 505, 566, 620 | `"bedrock-2023-05-31"` (5 处) |
| `springo-app/renderer/js/app.js` | 4754 | `'2023-06-01'` |

国产模型不使用 `anthropic_version` 参数。直接传入会导致请求格式不兼容。

### 6. 各路由硬编码特定 Claude 模型

| 文件 | 行号 | 硬编码模型 | 用途 |
|---|---|---|---|
| `api/routers/news.py` | 250 | `us.anthropic.claude-sonnet-4-5-*` | 新闻格式化 |
| `api/routers/terminal.py` | 203 | `us.anthropic.claude-3-5-haiku-*` | NL→命令解析 |
| `api/services/context_manager.py` | 622 | `us.anthropic.claude-haiku-4-5-*` | 上下文压缩 |

### 7. 前端 13+ 处硬编码

**`springo-app/renderer/js/app.js`**:

| 行号 | 值 | 用途 |
|---|---|---|
| 1266, 1350, 1721, 4612, 5551, 5634, 5664, 7047 | `'claude-opus-4-6'` | 默认对话模型 |
| 4734, 5556, 5665 | `'claude-haiku-4-5-20251001'` | 上下文压缩模型 |
| 5600-5609 | 迁移逻辑 | 旧 Claude 模型名 → 新模型名 |

### 8. System Prompt 假定 Claude 行为

**`api/services/bedrock.py:134-347`** — 200+ 行默认 system prompt 按 Claude 行为设计，包含：
- Claude 特有的 emoji 使用规则
- Claude Code 风格的工具选择指南
- Claude 特有的 task/skill 格式

### 9. 测试用例硬编码

| 文件 | 硬编码模型 |
|---|---|
| `tests/e2e/test_messages.py` (7 处) | `claude-sonnet-4-5-20250929` |
| `tests/e2e/test_benchmark.py` (1 处) | `claude-sonnet-4-5-20250929` |
| `tests/e2e/test_teams.py` (1 处) | `claude-sonnet-4-5-20250929` |

### 绑定总结

| 类别 | 绑定数量 | 影响范围 |
|---|---|---|
| 默认模型 ID | ~10 处 | 后端 config / models / services |
| MODEL_REGISTRY | 12 个模型 | 仅 Claude，无国产模型 |
| UI 模型列表 | 4 个模型 | 用户无法选择其他模型 |
| anthropic_version | ~10 处 | 请求格式不兼容非 Claude 模型 |
| Fallback 逻辑 | 2 处 | 国产模型 ID 会被错误拼接 |
| 路由硬编码 | 3 处 | news/terminal/context 强绑定 |
| 前端硬编码 | 13+ 处 | app.js 多处默认值 |
| System Prompt | 1 处 (200+ 行) | 假定 Claude 行为模式 |
| 测试 | 9 处 | 所有测试仅测 Claude |

**接入国产模型的最小改动路径**：扩展 `MODEL_REGISTRY` → 修改 `_UI_MODELS` → 修改 fallback 逻辑 → 条件化 `anthropic_version` 参数 → 为非 Claude 模型跳过 Claude 特有 system prompt 注入。
