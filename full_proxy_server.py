#!/usr/bin/env python3
"""
Claude Web Application with AWS Bedrock Backend
================================================

独立的 Claude Web 应用，使用 AWS Bedrock 作为后端。
包含完整的 MCP 工具支持、上下文管理、浏览器自动化等功能。

功能特性:
- AWS Bedrock Claude 模型调用
- 28+ MCP 工具 (文件系统、Git、Web搜索、浏览器自动化)
- 上下文管理和 Token 计数
- 外部 MCP 服务器支持
- Web 聊天界面

使用方法:
1. 配置 AWS 认证: http://127.0.0.1:8080/config
2. 访问聊天界面: http://127.0.0.1:8080/chat
"""

import json
import time
import uuid
import logging
import os
from datetime import datetime
from typing import Generator
from flask import Flask, request, Response, stream_with_context
import boto3
from botocore.config import Config

# 认证模块
from auth.config_manager import AuthConfigManager
from ui.routes import config_bp

# MCP 工具模块
from mcp_tools import get_tool_definitions, execute_tool, set_working_dir, get_working_dir
from mcp_tools.session import consume_active_skill
# NOTE: set_search_config, get_search_config removed - use MCP web-search server instead

# 上下文管理模块
from context_manager import get_context_manager, get_stats as get_context_stats

# MCP 服务器客户端
from mcp_client import get_mcp_manager, initialize_mcp_servers, get_mcp_tools, call_mcp_tool, shutdown_mcp_servers

# Skill 加载器
from skill_loader import get_skill_loader

# 错误处理模块
from error_handler import format_error_response, get_user_friendly_message, should_retry, get_http_status

# Memory 同步模块
from memory_sync import init_memory_sync, shutdown_memory_sync
# S3 同步模块
from s3_sync import init_s3_sync, shutdown_s3_sync, get_s3_manager, get_s3_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'ui', 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

# CORS configuration - restrict to local origins only
ALLOWED_ORIGINS = ['http://127.0.0.1:8080', 'http://localhost:8080', 'file://']

@app.after_request
def add_cors_headers(response):
    """Add CORS headers with restricted origins"""
    origin = request.headers.get('Origin', '')
    # Only allow local origins
    if origin in ALLOWED_ORIGINS or origin.startswith('file://'):
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:8080'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Api-Key'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

# 注册配置 UI Blueprint
app.register_blueprint(config_bp)

# MCP auto-initialization flag
_mcp_initialized = False

# Image media type mappings (used across multiple endpoints)
MEDIA_TYPE_TO_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp'
}
EXT_TO_MEDIA_TYPE = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp'
}

@app.before_request
def ensure_mcp_initialized():
    """Auto-initialize MCP servers on first request"""
    global _mcp_initialized
    if not _mcp_initialized:
        try:
            initialize_mcp_servers()
            _mcp_initialized = True
        except Exception as e:
            logger.warning(f"MCP auto-init on request failed: {e}")

# 认证配置管理器
auth_manager = AuthConfigManager()

# AWS Bedrock 配置
AWS_REGION = "us-east-1"

BEDROCK_MODEL_MAPPING = {
    "claude-3-5-sonnet-20241022": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-5-haiku-20241022": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "claude-3-opus-20240229": "us.anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet-20240229": "us.anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku-20240307": "us.anthropic.claude-3-haiku-20240307-v1:0",
    "claude-3-7-sonnet-20250219": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "claude-sonnet-4-20250514": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "claude-opus-4-20250514": "us.anthropic.claude-opus-4-20250514-v1:0",
    "claude-opus-4-5-20251101": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "claude-haiku-4-5-20251001": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
}


def get_bedrock_client():
    """获取 Bedrock 客户端 - 使用认证配置管理器"""
    try:
        return auth_manager.get_bedrock_client()
    except Exception as e:
        logger.warning(f"Failed to get configured client, falling back to default: {e}")
        config = Config(
            region_name=AWS_REGION,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            connect_timeout=60,
            read_timeout=600  # 10 分钟 - 支持长时间 tool use
        )
        return boto3.client('bedrock-runtime', config=config)


# Default system prompt with tool usage guidelines
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

## Communication Style

**IMPORTANT: Do NOT use emojis in your responses or generated files.** Keep all output clean and text-based. No emoticons, no unicode symbols like checkmarks or crosses.

## CRITICAL: Always Use Absolute Paths

**For ALL tool calls that accept file or directory paths, you MUST use absolute paths.**

- Correct: `/Users/name/project/file.txt`
- Correct: `~/.springo/skills/pptx/script.py` (~ expands to home directory)
- Wrong: `file.txt` (relative path)
- Wrong: `./project/file.txt` (relative path)
- Wrong: `workspace/file.txt` (relative path)

The working directory will be provided below. Use it to construct absolute paths.

## Tool Selection Guidelines

| Task | Best Tool | Avoid |
|------|-----------|-------|
| Find files by pattern | `glob` | bash find/ls |
| Search file content | `grep` | bash grep/rg |
| Read single file | `read_file` | bash cat |
| Read multiple files | `read_files` | multiple read_file calls |
| Edit existing file | `edit` | write_file (unless rewriting) |
| Execute commands | `execute_command` | - |
| Long-running tasks | `execute_command` with run_in_background=true | - |
| Track complex tasks | `todo_write` | - |
| Ask user questions | `ask_user` | - |
| Plan before coding | `enter_plan_mode` | - |

## Task Management (Important!)

Use `todo_write` to track progress on complex, multi-step tasks:
- Break down tasks into clear steps
- Mark tasks as "in_progress" when starting, "completed" when done
- This helps the user see what you're doing
- Example: When creating a PPT, create todos for each slide

```
todo_write({
  "todos": [
    {"content": "Search for GPU news", "status": "in_progress", "activeForm": "Searching GPU news"},
    {"content": "Create slide 1", "status": "pending", "activeForm": "Creating slide 1"},
    {"content": "Create slide 2", "status": "pending", "activeForm": "Creating slide 2"}
  ]
})
```

## User Questions

Use `ask_user` when you need clarification:
- Present clear options for the user to choose from
- Include descriptions for each option
- Allow custom input when appropriate

```
ask_user({
  "question": "What style do you prefer for the presentation?",
  "options": [
    {"label": "Business", "description": "Clean, professional look"},
    {"label": "Creative", "description": "Colorful and playful"},
    {"label": "Minimal", "description": "Simple and elegant"}
  ]
})
```

## Plan Mode

For complex tasks, use `enter_plan_mode` first:
1. Enter plan mode to analyze requirements
2. Explore the codebase without making changes
3. Create a plan with `exit_plan_mode`
4. Wait for user approval before implementing

## Best Practices

1. **Use parallel tool calls** when operations are independent:
   - Reading multiple unrelated files
   - Searching in different directories
   - Running independent commands
   - IMPORTANT: Call multiple tools in the same response when they don't depend on each other

2. **Prefer specialized tools** over bash commands:
   - `glob` for file pattern matching (sorted by modification time)
   - `grep` for content search (supports output_mode: files_with_matches, content, count)
   - `edit` for precise string replacement (safer than write_file)
   - `read_files` for batch file reading

3. **Background tasks** for long operations:
   - Use `run_in_background=true` for builds, tests, servers
   - Check status with `get_task_status`
   - List all with `list_background_tasks`

4. **Edit vs Write**:
   - Use `edit` when modifying specific parts of a file
   - Use `write_file` only when creating new files or complete rewrites

5. **Reduce round trips**:
   - Chain related bash commands with && when they must run sequentially
   - Use `read_files` instead of multiple `read_file` calls

6. **Avoid truncation errors**:
   - When writing files, keep content under 500 lines per file
   - For large content, split into multiple smaller files
   - When generating HTML/code files, keep them focused and modular
   - If creating multiple files, do them in separate tool calls, not all at once

7. **Web search (MCP only)**:
   - Use MCP tool: web-search__brave_web_search (built-in web_search removed)
   - **IMPORTANT**: When user asks for "最新"/"latest"/"recent" content, ALWAYS use freshness parameter:
     - freshness="pd" (past day) - for breaking news
     - freshness="pw" (past week) - RECOMMENDED for "最新" queries
     - freshness="pm" (past month) - for broader recent content
     - freshness="py" (past year) - for annual content
   - Use ENGLISH keywords in query, include current year for recent content
   - Use count=5-10 for initial exploration
   - For news: use web-search__brave_news_search

8. **Specialized agents** with `task` tool:
   - Use agent_type="explore" for code exploration
   - Use agent_type="research" for web research
   - Use agent_type="implement" for code implementation

## Safety

- Commands are checked for dangerous patterns
- Sensitive files (.env, credentials, etc.) require confirmation
- File operations are restricted to allowed directories
"""


def convert_anthropic_to_bedrock(anthropic_request: dict, include_tools: bool = True) -> tuple[str, dict]:
    """将 Anthropic API 格式转换为 Bedrock 格式"""
    model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
    bedrock_model_id = BEDROCK_MODEL_MAPPING.get(model, f"us.anthropic.{model}-v1:0")

    bedrock_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": anthropic_request.get("max_tokens", 16384),  # Increased for large tool outputs
        "messages": anthropic_request.get("messages", []),
    }

    for key in ["system", "temperature", "top_p", "top_k", "stop_sequences", "tools", "tool_choice"]:
        if key in anthropic_request:
            bedrock_body[key] = anthropic_request[key]

    # Add default system prompt with tool guidelines if not provided
    # NOTE: System prompt is kept static for KV cache efficiency
    # Dynamic context (time) is injected into the first user message instead
    current_working_dir = get_working_dir()

    # Static working directory info (changes infrequently, acceptable in system prompt)
    working_dir_info = ""
    if current_working_dir:
        working_dir_info = f"""

## Working Directory
- **Path**: `{current_working_dir}`
- All file operations should use absolute paths based on this directory
"""

    if "system" not in bedrock_body:
        bedrock_body["system"] = DEFAULT_SYSTEM_PROMPT + working_dir_info
    else:
        # Append working dir info to existing system prompt
        bedrock_body["system"] = bedrock_body["system"] + working_dir_info

    # Inject dynamic time into the LAST user message (preserves KV cache for system prompt)
    # This ensures each new request has current time, even in long-running sessions
    if bedrock_body.get("messages"):
        now = datetime.now()
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday = weekday_names[now.weekday()]
        time_str = now.strftime('%Y-%m-%d %H:%M')
        time_prefix = f"[Current time: {time_str} ({weekday})]\n\n"

        # Find the LAST user message and prepend time
        for i in range(len(bedrock_body["messages"]) - 1, -1, -1):
            msg = bedrock_body["messages"][i]
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    bedrock_body["messages"][i]["content"] = time_prefix + content
                elif isinstance(content, list) and len(content) > 0:
                    # Handle array content format
                    if content[0].get("type") == "text":
                        content[0]["text"] = time_prefix + content[0].get("text", "")
                break  # Only modify the last user message

    # 自动添加 MCP 工具 (动态生成，包含技能列表)
    # Check for empty tools array too - frontend may send tools: [] on fetch failure
    if include_tools and not bedrock_body.get("tools"):
        bedrock_body["tools"] = get_tool_definitions()
        logger.info(f"[TOOLS] Auto-added {len(bedrock_body['tools'])} tools (request had none or empty)")

    return bedrock_model_id, bedrock_body


def handle_streaming_response(bedrock_client, model_id: str, body: dict, original_model: str) -> Generator:
    """处理流式响应，支持文本和工具调用"""
    try:
        response = bedrock_client.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json"
        )

        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        current_block_index = -1
        started_message = False

        for event in response.get("body", []):
            chunk = json.loads(event.get("chunk", {}).get("bytes", b"{}"))
            chunk_type = chunk.get("type")

            if chunk_type == "message_start":
                started_message = True
                msg = chunk.get("message", {})
                msg["model"] = original_model
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"

            elif chunk_type == "content_block_start":
                current_block_index = chunk.get("index", 0)
                content_block = chunk.get("content_block", {})
                yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': content_block})}\n\n"

            elif chunk_type == "content_block_delta":
                index = chunk.get("index", current_block_index)
                delta = chunk.get("delta", {})
                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': index, 'delta': delta})}\n\n"

            elif chunk_type == "content_block_stop":
                index = chunk.get("index", current_block_index)
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index})}\n\n"

            elif chunk_type == "message_delta":
                delta_data = {
                    'type': 'message_delta',
                    'delta': chunk.get('delta', {}),
                    'usage': chunk.get('usage', {})
                }
                yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"

            elif chunk_type == "message_stop":
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        if not started_message:
            yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': message_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': original_model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        # 使用错误处理模块解析并格式化错误
        error_response = format_error_response(e, lang="zh")
        yield f"event: error\ndata: {json.dumps(error_response)}\n\n"


# ==================== 核心 API 端点 ====================

@app.route('/v1/messages', methods=['POST'])
def messages_api():
    """Claude Messages API - 调用 Bedrock"""
    try:
        anthropic_request = request.get_json()
        logger.info(f"Messages API: model={anthropic_request.get('model')}, stream={anthropic_request.get('stream', False)}")

        model_id, bedrock_body = convert_anthropic_to_bedrock(anthropic_request)
        original_model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
        bedrock_client = get_bedrock_client()
        is_streaming = anthropic_request.get("stream", False)

        if is_streaming:
            return Response(
                stream_with_context(handle_streaming_response(
                    bedrock_client, model_id, bedrock_body, original_model
                )),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            response = bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(bedrock_body),
                contentType="application/json",
                accept="application/json"
            )

            bedrock_response = json.loads(response['body'].read())

            anthropic_response = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": bedrock_response.get("content", []),
                "model": original_model,
                "stop_reason": bedrock_response.get("stop_reason"),
                "stop_sequence": bedrock_response.get("stop_sequence"),
                "usage": {
                    "input_tokens": bedrock_response.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": bedrock_response.get("usage", {}).get("output_tokens", 0),
                }
            }

            return Response(
                json.dumps(anthropic_response),
                mimetype='application/json',
                headers={'x-request-id': str(uuid.uuid4())}
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        # 使用错误处理模块解析并格式化错误
        error_response = format_error_response(e, lang="zh")
        http_status = get_http_status(e)
        return Response(
            json.dumps(error_response),
            status=http_status,
            mimetype='application/json'
        )


# ==================== 服务端自动工具执行 (性能优化) ====================

@app.route('/v1/messages-auto', methods=['POST'])
def messages_auto_api():
    """
    自动工具执行 API - 消除前端往返延迟

    工作流程:
    1. 调用 Bedrock API
    2. 如果返回 tool_use，在服务端直接执行工具
    3. 将 tool_result 发送回 Bedrock
    4. 重复直到没有更多 tool_use 或达到最大迭代次数
    5. 返回最终响应

    优势: 消除每个工具的前端往返延迟 (每个工具节省 ~1-3秒)
    """
    try:
        anthropic_request = request.get_json()
        is_streaming = anthropic_request.get("stream", False)
        # Claude Code 风格：基于 context 窗口，而非固定迭代次数
        # 1000 仅作为安全上限，正常情况下由 context compact 控制
        max_tool_iterations = anthropic_request.pop("max_tool_iterations", 1000)
        # Context compact 使用的模型 (默认 Haiku 4.5，更快更便宜)
        compact_model = anthropic_request.pop("compact_model", "claude-haiku-4-5-20251001")

        logger.info(f"Messages-Auto API: model={anthropic_request.get('model')}, stream={is_streaming}, compact_model={compact_model}")

        if is_streaming:
            return Response(
                stream_with_context(handle_auto_streaming(anthropic_request, max_tool_iterations, compact_model)),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            result = handle_auto_nonstreaming(anthropic_request, max_tool_iterations)
            return Response(json.dumps(result), mimetype='application/json')

    except Exception as e:
        logger.error(f"Messages-Auto Error: {e}")
        error_response = format_error_response(e, lang="zh")
        http_status = get_http_status(e)
        return Response(json.dumps(error_response), status=http_status, mimetype='application/json')


def handle_auto_streaming(anthropic_request: dict, max_iterations: int = 1000, compact_model: str = "claude-haiku-4-5-20251001") -> Generator:
    """处理流式响应并自动执行工具

    Claude Code 风格：不限制迭代次数，基于 context 窗口自动 compact
    max_iterations 仅作为安全上限，正常情况下不会触发
    compact_model: 用于 context 压缩的模型 (默认 Haiku 4.5，更快更便宜)
    """
    from mcp_tools import execute_tool

    bedrock_client = get_bedrock_client()
    ctx_manager = get_context_manager()
    original_model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
    messages = list(anthropic_request.get("messages", []))  # Make a copy
    tools = anthropic_request.get("tools", [])
    system = anthropic_request.get("system", "")

    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Claude Code style: inject active skill into system prompt
        active_skill = consume_active_skill()
        if active_skill:
            skill_injection = f"""

<skill name="{active_skill['name']}">
{active_skill['instructions']}
</skill>

IMPORTANT: You have activated the '{active_skill['name']}' skill.
Please follow the skill instructions above to complete the user's request.
User's original request: {active_skill.get('user_request', '(not specified)')}
"""
            system = system + skill_injection
            logger.info(f"Injected skill '{active_skill['name']}' into system prompt")
            yield f"event: skill_injected\ndata: {json.dumps({'type': 'skill_injected', 'skill_name': active_skill['name']})}\n\n"

        # Get session_id for persistence (Claude Code style: persist changes)
        session_id = anthropic_request.get('session_id')
        messages_modified = False

        # Step 1: Truncate old tool results to prevent context overflow (Claude Code style)
        # This is CRITICAL to prevent tool results from consuming too much context
        before_truncation = ctx_manager.count_messages_tokens(messages)
        messages = ctx_manager.prepare_messages_for_api(messages, keep_recent=3)
        after_truncation = ctx_manager.count_messages_tokens(messages)
        if before_truncation != after_truncation:
            logger.info(f"Tool results truncated: {before_truncation:,} -> {after_truncation:,} tokens")
            messages_modified = True

        # Step 2: Context 检查和自动 compact (Claude Code 风格)
        current_token_count = ctx_manager.count_messages_tokens(messages)
        logger.info(f"[Compact Check] iteration={iteration}, tokens={current_token_count:,}, threshold={ctx_manager.SUMMARY_THRESHOLD:,}, should_compact={current_token_count > ctx_manager.SUMMARY_THRESHOLD}")
        if ctx_manager.should_summarize(messages):
            logger.info(f"Context approaching limit ({ctx_manager.count_messages_tokens(messages):,} tokens), compacting with {compact_model}... (iteration {iteration})")
            yield f"event: context_compact\ndata: {json.dumps({'type': 'context_compact', 'reason': 'approaching_limit', 'model': compact_model, 'tokens_before': ctx_manager.count_messages_tokens(messages)})}\n\n"
            try:
                original_count = len(messages)
                messages = ctx_manager.summarize_messages(messages, model=compact_model)
                new_token_count = ctx_manager.count_messages_tokens(messages)
                logger.info(f"Context compacted: {original_count} -> {len(messages)} messages, {new_token_count:,} tokens")
                messages_modified = True
                yield f"event: context_compact_done\ndata: {json.dumps({'type': 'context_compact_done', 'messages_before': original_count, 'messages_after': len(messages), 'tokens_after': new_token_count})}\n\n"
            except Exception as e:
                logger.error(f"Context compact failed: {e}", exc_info=True)
                # Even if compact fails, continue with truncated tool results
                yield f"event: context_compact_failed\ndata: {json.dumps({'type': 'context_compact_failed', 'error': str(e)})}\n\n"

        # Step 3: Final check - if still over limit, force truncation
        current_tokens = ctx_manager.count_messages_tokens(messages)
        if current_tokens > ctx_manager.MAX_TOKENS * 0.95:  # 95% threshold
            logger.warning(f"Context still critical ({current_tokens:,} tokens), forcing aggressive truncation")
            # Force aggressive truncation on ALL tool results
            messages = ctx_manager.truncate_tool_results(messages, max_size=2048)  # 2KB limit
            final_tokens = ctx_manager.count_messages_tokens(messages)
            logger.info(f"After aggressive truncation: {final_tokens:,} tokens")
            messages_modified = True

        # Step 4: Persist changes and notify frontend (Claude Code style)
        # This ensures truncated/compacted messages are saved and frontend stays in sync
        if messages_modified and session_id:
            try:
                # Save updated messages to JSONL (overwrite with compacted version)
                ctx_manager.save_session_complete(session_id, messages, metadata={
                    'compacted': True,
                    'tokens': ctx_manager.count_messages_tokens(messages)
                })
                logger.info(f"Session {session_id} updated with compacted messages")
                # Notify frontend to reload messages
                yield f"event: messages_updated\ndata: {json.dumps({'type': 'messages_updated', 'session_id': session_id, 'messages': messages, 'token_count': ctx_manager.count_messages_tokens(messages)})}\n\n"
            except Exception as e:
                logger.error(f"Failed to persist compacted messages: {e}")

        # Step 5: Repair orphaned tool_use blocks (critical for Bedrock API)
        # This handles the case where user interrupts mid-turn, leaving tool_use without tool_result
        messages = ctx_manager.repair_orphan_tool_uses(messages)

        # 构建请求
        logger.info(f"[DEBUG] Building request - tools count: {len(tools)}, messages count: {len(messages)}")
        if tools:
            logger.info(f"[DEBUG] First 3 tools: {[t.get('name', '?') for t in tools[:3]]}")
        else:
            logger.warning(f"[DEBUG] NO TOOLS in request! This will cause hallucination.")

        model_id, bedrock_body = convert_anthropic_to_bedrock({
            "model": original_model,
            "messages": messages,
            "tools": tools,
            "system": system,
            "max_tokens": anthropic_request.get("max_tokens", 8192),
            "stream": True
        })

        # Verify tools are in bedrock_body
        bedrock_tools = bedrock_body.get("tools", [])
        logger.info(f"[DEBUG] Bedrock body tools count: {len(bedrock_tools)}")

        # 调用 Bedrock 流式 API
        try:
            response = bedrock_client.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(bedrock_body),
                contentType="application/json",
                accept="application/json"
            )
        except Exception as e:
            logger.error(f"Bedrock API error: {e}")
            error_response = format_error_response(e, lang="zh")
            yield f"event: error\ndata: {json.dumps(error_response)}\n\n"
            return

        # 收集完整响应
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        content_blocks = []
        current_block = None
        current_block_index = -1
        stop_reason = None
        usage = {"input_tokens": 0, "output_tokens": 0}

        for event in response.get("body", []):
            chunk = json.loads(event.get("chunk", {}).get("bytes", b"{}"))
            chunk_type = chunk.get("type")

            if chunk_type == "message_start":
                msg = chunk.get("message", {})
                msg["model"] = original_model
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"

            elif chunk_type == "content_block_start":
                current_block_index = chunk.get("index", 0)
                current_block = chunk.get("content_block", {})
                content_blocks.append(current_block.copy())
                yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': current_block})}\n\n"

            elif chunk_type == "content_block_delta":
                index = chunk.get("index", current_block_index)
                delta = chunk.get("delta", {})

                # 累积内容
                if index < len(content_blocks):
                    block = content_blocks[index]
                    if "text" in delta:
                        block["text"] = block.get("text", "") + delta["text"]
                    if "partial_json" in delta:
                        # 使用单独字段累积 JSON 字符串，避免类型冲突
                        if "_input_json" not in block:
                            block["_input_json"] = ""
                        block["_input_json"] = block["_input_json"] + delta["partial_json"]

                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': index, 'delta': delta})}\n\n"

            elif chunk_type == "content_block_stop":
                index = chunk.get("index", current_block_index)

                # 解析 tool_use 的 input
                if index < len(content_blocks):
                    block = content_blocks[index]
                    if block.get("type") == "tool_use":
                        # 从累积的 JSON 字符串解析
                        if "_input_json" in block:
                            try:
                                block["input"] = json.loads(block["_input_json"])
                            except:
                                block["input"] = {}
                            del block["_input_json"]
                        # 兜底：如果 input 仍是字符串
                        elif isinstance(block.get("input"), str):
                            try:
                                block["input"] = json.loads(block["input"])
                            except:
                                block["input"] = {}

                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': index})}\n\n"

            elif chunk_type == "message_delta":
                delta = chunk.get("delta", {})
                stop_reason = delta.get("stop_reason", stop_reason)
                usage = chunk.get("usage", usage)
                yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': delta, 'usage': usage})}\n\n"

            elif chunk_type == "message_stop":
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        # 检查是否需要执行工具
        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]

        # Debug: log stop_reason and tool_uses
        logger.info(f"[DEBUG] Response stop_reason: {stop_reason}")
        logger.info(f"[DEBUG] Content blocks: {len(content_blocks)}, tool_uses: {len(tool_uses)}")
        if tool_uses:
            logger.info(f"[DEBUG] Tool uses: {[t.get('name') for t in tool_uses]}")

        if not tool_uses or stop_reason != "tool_use":
            # 没有工具调用，完成
            logger.info(f"[DEBUG] No tool execution - stop_reason={stop_reason}, tool_uses={len(tool_uses)}")
            return

        # 执行工具并发送进度更新 (include input for frontend display)
        tools_for_event = [{'id': t['id'], 'name': t['name'], 'input': t.get('input', {})} for t in tool_uses]
        yield f"event: tool_execution_start\ndata: {json.dumps({'type': 'tool_execution_start', 'tools': tools_for_event})}\n\n"

        tool_results = []
        for tool_use in tool_uses:
            tool_id = tool_use.get("id")
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})

            # Log search tool calls for debugging
            if 'search' in tool_name.lower():
                logger.info(f"🔍 SEARCH TOOL CALL: {tool_name}")
                logger.info(f"   Query: {tool_input.get('query', 'N/A')}")
                logger.info(f"   Freshness: {tool_input.get('freshness', 'NOT SET')}")
                logger.info(f"   Full params: {json.dumps(tool_input)}")

            # 发送工具开始执行事件
            yield f"event: tool_executing\ndata: {json.dumps({'type': 'tool_executing', 'id': tool_id, 'name': tool_name})}\n\n"

            # 执行工具
            try:
                result = execute_tool(tool_name, tool_input)
            except Exception as e:
                result = {"error": str(e)}

            # Handle large tool results (like Claude Code)
            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
            result_size = len(result_str.encode('utf-8'))

            # If result exceeds 64KB, save to file and return reference
            if result_size > ctx_manager.MAX_INLINE_OUTPUT_SIZE:
                # Get session_id from request context or generate one
                session_id = anthropic_request.get('session_id', f"auto_{uuid.uuid4().hex[:8]}")
                result_info = ctx_manager.save_tool_result(session_id, tool_id, result_str, tool_name)
                logger.info(f"Large tool result saved: {tool_name} ({result_size:,} bytes) -> {result_info.get('file_path', 'inline')}")

                # Use truncated content for API, but full result for frontend event
                if not result_info.get('inline'):
                    result_str = json.dumps({
                        "result_truncated": True,
                        "file_path": result_info.get('file_path'),
                        "size": result_size,
                        "preview": result_info.get('preview', result_str[:500]),
                        "message": f"Result saved to file ({result_size:,} bytes). Use /v1/tool-results/{session_id}/{tool_id} to retrieve full content."
                    })

            # 发送工具完成事件 (use tool_use_id and tool_name for consistency with api/messages.py)
            yield f"event: tool_result\ndata: {json.dumps({'type': 'tool_result', 'tool_use_id': tool_id, 'tool_name': tool_name, 'result': result})}\n\n"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_str
            })

        yield f"event: tool_execution_complete\ndata: {json.dumps({'type': 'tool_execution_complete', 'count': len(tool_results)})}\n\n"

        # 清理临时字段，避免发送给 Bedrock API
        cleaned_blocks = []
        for block in content_blocks:
            clean_block = {k: v for k, v in block.items() if not k.startswith("_")}
            cleaned_blocks.append(clean_block)

        # 更新消息历史，继续对话
        messages.append({
            "role": "assistant",
            "content": cleaned_blocks
        })
        messages.append({
            "role": "user",
            "content": tool_results
        })

    # 达到最大迭代次数
    yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'message': f'Reached maximum tool iterations ({max_iterations})'}})}\n\n"


def handle_auto_nonstreaming(anthropic_request: dict, max_iterations: int = 1000) -> dict:
    """处理非流式响应并自动执行工具"""
    from mcp_tools import execute_tool

    bedrock_client = get_bedrock_client()
    ctx_manager = get_context_manager()
    original_model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
    messages = list(anthropic_request.get("messages", []))  # Make a copy
    tools = anthropic_request.get("tools", [])
    system = anthropic_request.get("system", "")

    # Repair orphaned tool_use blocks (critical for Bedrock API)
    messages = ctx_manager.repair_orphan_tool_uses(messages)

    iteration = 0
    final_response = None

    while iteration < max_iterations:
        iteration += 1

        # Claude Code style: inject active skill into system prompt
        active_skill = consume_active_skill()
        if active_skill:
            skill_injection = f"""

<skill name="{active_skill['name']}">
{active_skill['instructions']}
</skill>

IMPORTANT: You have activated the '{active_skill['name']}' skill.
Please follow the skill instructions above to complete the user's request.
User's original request: {active_skill.get('user_request', '(not specified)')}
"""
            system = system + skill_injection
            logger.info(f"Injected skill '{active_skill['name']}' into system prompt (non-streaming)")

        model_id, bedrock_body = convert_anthropic_to_bedrock({
            "model": original_model,
            "messages": messages,
            "tools": tools,
            "system": system,
            "max_tokens": anthropic_request.get("max_tokens", 8192),
            "stream": False
        })

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(bedrock_body),
            contentType="application/json",
            accept="application/json"
        )

        bedrock_response = json.loads(response['body'].read())
        content = bedrock_response.get("content", [])
        stop_reason = bedrock_response.get("stop_reason")

        final_response = {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": content,
            "model": original_model,
            "stop_reason": stop_reason,
            "usage": bedrock_response.get("usage", {})
        }

        # 检查是否需要执行工具
        tool_uses = [b for b in content if b.get("type") == "tool_use"]

        if not tool_uses or stop_reason != "tool_use":
            return final_response

        # 执行工具
        tool_results = []
        for tool_use in tool_uses:
            tool_id = tool_use.get("id")
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})

            try:
                result = execute_tool(tool_name, tool_input)
            except Exception as e:
                result = {"error": str(e)}

            # Handle large tool results (like Claude Code)
            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
            result_size = len(result_str.encode('utf-8'))

            # If result exceeds 64KB, save to file and return reference
            if result_size > ctx_manager.MAX_INLINE_OUTPUT_SIZE:
                session_id = anthropic_request.get('session_id', f"auto_{uuid.uuid4().hex[:8]}")
                result_info = ctx_manager.save_tool_result(session_id, tool_id, result_str, tool_name)
                logger.info(f"Large tool result saved: {tool_name} ({result_size:,} bytes)")

                if not result_info.get('inline'):
                    result_str = json.dumps({
                        "result_truncated": True,
                        "file_path": result_info.get('file_path'),
                        "size": result_size,
                        "preview": result_info.get('preview', result_str[:500]),
                        "message": f"Result saved to file ({result_size:,} bytes)."
                    })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_str
            })

        # 更新消息历史
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": tool_results})

    return final_response or {"error": f"Reached maximum iterations ({max_iterations})"}


@app.route('/v1/models', methods=['GET'])
def list_models():
    """列出可用的模型"""
    models = [
        {"id": model, "created": int(time.time()), "object": "model"}
        for model in BEDROCK_MODEL_MAPPING.keys()
    ]
    return Response(json.dumps({"data": models, "object": "list"}), mimetype='application/json')


@app.route('/health', methods=['GET'])
def health():
    """健康检查端点"""
    return Response(json.dumps({"status": "healthy", "backend": "bedrock"}), mimetype='application/json')


@app.route('/v1/warmup', methods=['POST'])
def warmup():
    """Warmup endpoint to prevent cold starts.

    Call this periodically (e.g., every 30s) to keep the system ready:
    - Pre-loads skill definitions
    - Checks MCP server health (removes dead servers)
    - Keeps Bedrock client connection warm
    """
    import time
    start = time.time()
    results = {
        "skills": None,
        "mcp_servers": None,
        "bedrock_client": None
    }

    try:
        # 1. Pre-load skills (uses cache, fast)
        loader = get_skill_loader()
        loader.reload()  # Uses cache TTL, won't re-scan if fresh
        results["skills"] = {"count": len(loader.skills), "cached": True}
    except Exception as e:
        results["skills"] = {"error": str(e)}

    try:
        # 2. Check MCP server health
        manager = get_mcp_manager()
        health_results = manager.health_check_all()
        results["mcp_servers"] = {
            "checked": len(health_results),
            "healthy": sum(1 for v in health_results.values() if v),
            "dead_cleaned": sum(1 for v in health_results.values() if not v)
        }
    except Exception as e:
        results["mcp_servers"] = {"error": str(e)}

    try:
        # 3. Keep Bedrock client alive (just get client, don't make API call)
        client = get_bedrock_client()
        results["bedrock_client"] = {"ready": client is not None}
    except Exception as e:
        results["bedrock_client"] = {"error": str(e)}

    elapsed = time.time() - start
    results["elapsed_ms"] = round(elapsed * 1000, 2)

    return Response(json.dumps(results), mimetype='application/json')


# ==================== 上下文管理端点 ====================

@app.route('/v1/context/stats', methods=['POST'])
def context_stats():
    """获取消息的上下文统计信息"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        stats = get_context_stats(messages)
        return Response(json.dumps(stats), mimetype='application/json')
    except Exception as e:
        logger.error(f"Context stats error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/context/breakdown', methods=['POST'])
def context_breakdown():
    """获取详细的上下文分类统计（类似 Claude Code 的 /context 命令）"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        system_prompt = data.get('system', '')
        tools = data.get('tools', [])
        skills = data.get('skills', [])
        memory_files = data.get('memory_files', [])
        ctx_manager = get_context_manager()
        breakdown = ctx_manager.get_context_breakdown(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            skills=skills,
            memory_files=memory_files
        )
        return Response(json.dumps(breakdown), mimetype='application/json')
    except Exception as e:
        logger.error(f"Context breakdown error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/context/summarize', methods=['POST'])
def context_summarize():
    """使用 Haiku 模型自动总结对话上下文"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])

        if not messages:
            return Response(json.dumps({"error": "No messages provided"}), status=400, mimetype='application/json')

        # 获取上下文管理器
        ctx_manager = get_context_manager()

        # 检查是否需要总结
        stats = ctx_manager.get_context_stats(messages)
        if not stats['needs_summarization']:
            return Response(json.dumps({
                "summarized": False,
                "reason": "Context size is within limits",
                "stats": stats
            }), mimetype='application/json')

        # 分割消息
        old_messages, recent_messages = ctx_manager.split_messages_for_summary(messages)

        if not old_messages:
            return Response(json.dumps({
                "summarized": False,
                "reason": "No old messages to summarize",
                "stats": stats
            }), mimetype='application/json')

        # 准备总结提示
        summary_prompt = ctx_manager.prepare_summary_prompt(old_messages)

        # 使用 Haiku 生成总结
        haiku_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
        bedrock_client = get_bedrock_client()

        summary_request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": summary_prompt}]
        }

        logger.info(f"Summarizing {len(old_messages)} messages using Haiku...")

        response = bedrock_client.invoke_model(
            modelId=haiku_model_id,
            body=json.dumps(summary_request),
            contentType="application/json",
            accept="application/json"
        )

        bedrock_response = json.loads(response['body'].read())
        summary_content = bedrock_response.get("content", [])

        # 提取文本摘要
        summary_text = ""
        for block in summary_content:
            if isinstance(block, dict) and block.get("type") == "text":
                summary_text += block.get("text", "")

        if not summary_text:
            return Response(json.dumps({
                "summarized": False,
                "reason": "Failed to generate summary",
                "stats": stats
            }), mimetype='application/json')

        # 创建新的消息列表
        new_messages = ctx_manager.create_summary_messages(summary_text, recent_messages)
        new_stats = ctx_manager.get_context_stats(new_messages)

        logger.info(f"Summarization complete: {stats['total_tokens']} -> {new_stats['total_tokens']} tokens")

        return Response(json.dumps({
            "summarized": True,
            "messages": new_messages,
            "summary": summary_text,
            "old_stats": stats,
            "new_stats": new_stats,
            "messages_removed": len(old_messages),
            "messages_kept": len(recent_messages)
        }), mimetype='application/json')

    except Exception as e:
        logger.error(f"Summarization error: {e}")
        import traceback
        traceback.print_exc()
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/context/auto-check', methods=['POST'])
def context_auto_check():
    """
    检查是否需要自动摘要，如果需要则执行摘要。
    Claude Code 风格：自动检测并执行，用户无感知。
    """
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        session_id = data.get('session_id')

        ctx_manager = get_context_manager()

        # 检查是否需要摘要
        auto_summary_data = ctx_manager.check_and_prepare_auto_summary(messages)

        if not auto_summary_data:
            # 不需要摘要，返回当前统计
            stats = ctx_manager.get_context_stats(messages)
            return Response(json.dumps({
                "action": "none",
                "stats": stats
            }), mimetype='application/json')

        # 需要摘要，执行自动摘要
        haiku_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
        bedrock_client = get_bedrock_client()

        summary_request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": auto_summary_data["summary_prompt"]}]
        }

        logger.info(f"Auto-summarizing {auto_summary_data['old_messages_count']} messages...")

        response = bedrock_client.invoke_model(
            modelId=haiku_model_id,
            body=json.dumps(summary_request),
            contentType="application/json",
            accept="application/json"
        )

        bedrock_response = json.loads(response['body'].read())
        summary_content = bedrock_response.get("content", [])

        summary_text = ""
        for block in summary_content:
            if isinstance(block, dict) and block.get("type") == "text":
                summary_text += block.get("text", "")

        if not summary_text:
            return Response(json.dumps({
                "action": "failed",
                "reason": "Failed to generate summary"
            }), status=500, mimetype='application/json')

        # 创建新的消息列表
        new_messages = ctx_manager.create_summary_messages(
            summary_text,
            auto_summary_data["recent_messages"]
        )

        # 如果有 session_id，保存摘要事件
        if session_id:
            ctx_manager.save_summary_event(
                session_id,
                summary_text,
                auto_summary_data["old_messages_count"],
                len(new_messages)
            )

        new_stats = ctx_manager.get_context_stats(new_messages)
        old_stats = ctx_manager.get_context_stats(messages)

        logger.info(f"Auto-summarization complete: {old_stats['total_tokens']} -> {new_stats['total_tokens']} tokens")

        return Response(json.dumps({
            "action": "summarized",
            "messages": new_messages,
            "summary": summary_text,
            "old_stats": old_stats,
            "new_stats": new_stats,
            "structured_info": auto_summary_data.get("structured_info", {})
        }), mimetype='application/json')

    except Exception as e:
        logger.error(f"Auto-check error: {e}")
        import traceback
        traceback.print_exc()
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


# ==================== 会话持久化端点 ====================

@app.route('/v1/sessions', methods=['GET'])
def list_sessions():
    """列出所有保存的会话"""
    try:
        working_dir = request.args.get('working_dir')
        ctx_manager = get_context_manager()
        sessions = ctx_manager.list_sessions(working_dir)
        return Response(json.dumps({"sessions": sessions}), mimetype='application/json')
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取指定会话的消息"""
    try:
        ctx_manager = get_context_manager()
        messages = ctx_manager.load_session(session_id)
        return Response(json.dumps({
            "session_id": session_id,
            "messages": messages,
            "count": len(messages)
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Get session error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/sessions/by-number/<int:number>', methods=['GET'])
def get_session_by_number(number):
    """通过前端显示编号获取会话 (如 #168)

    前端显示逻辑: sessionNumber = totalCount - index (最新的是最大号)
    所以 #N 对应 sessions[totalCount - N]
    """
    try:
        ctx_manager = get_context_manager()
        sessions = ctx_manager.list_sessions()
        total_count = len(sessions)

        if number < 1 or number > total_count:
            return Response(json.dumps({
                "error": f"Session #{number} not found. Valid range: #1 - #{total_count}"
            }), status=404, mimetype='application/json')

        # #N 对应 sessions[total_count - N] (因为 sessions 是按时间倒序)
        index = total_count - number
        session_info = sessions[index]
        session_id = session_info.get('session_id')

        # 加载消息
        messages = ctx_manager.load_session(session_id)

        return Response(json.dumps({
            "display_number": number,
            "session_id": session_id,
            "title": session_info.get('metadata', {}).get('title', ''),
            "messages": messages,
            "count": len(messages),
            "total_sessions": total_count
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Get session by number error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/sessions/<session_id>', methods=['POST'])
def save_session_messages(session_id):
    """保存消息到会话（完整覆盖，类似 Claude Code 的 JSONL 格式）"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        metadata = data.get('metadata', {})
        ctx_manager = get_context_manager()

        # Save complete session (overwrite mode for full sync)
        ctx_manager.save_session_complete(session_id, messages, metadata)

        return Response(json.dumps({
            "success": True,
            "session_id": session_id,
            "saved_count": len(messages) if isinstance(messages, list) else 1
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Save session error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除会话"""
    try:
        ctx_manager = get_context_manager()
        success = ctx_manager.delete_session(session_id)
        return Response(json.dumps({
            "success": success,
            "session_id": session_id
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/sessions/hash', methods=['POST'])
def get_session_hash():
    """根据工作目录生成会话哈希（用于项目级会话管理）"""
    try:
        data = request.get_json()
        working_dir = data.get('working_dir', '')
        ctx_manager = get_context_manager()
        hash_value = ctx_manager.get_session_hash(working_dir)
        return Response(json.dumps({
            "working_dir": working_dir,
            "hash": hash_value
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Session hash error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


# ==================== Image Storage API (Optimized - avoid base64 in JSONL) ====================

@app.route('/v1/images/upload', methods=['POST'])
def upload_image():
    """
    上传图片并存储为文件，返回图片引用 ID

    避免 base64 直接存入 JSONL，优化存储空间和加载速度
    图片存储位置: ~/.springo/sessions/{session_id}/images/{image_id}.{ext}
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        image_data = data.get('image_data')  # base64 encoded
        media_type = data.get('media_type', 'image/png')
        filename = data.get('filename', '')

        if not session_id or not image_data:
            return Response(json.dumps({"error": "session_id and image_data required"}),
                          status=400, mimetype='application/json')

        # Determine file extension from media type
        ext = MEDIA_TYPE_TO_EXT.get(media_type, 'png')

        # Generate unique image ID
        image_id = f"img_{uuid.uuid4().hex[:12]}"

        # Create images directory for this session
        ctx_manager = get_context_manager()
        session_dir = ctx_manager.get_session_dir(session_id)
        images_dir = os.path.join(session_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Save image file
        image_path = os.path.join(images_dir, f"{image_id}.{ext}")
        import base64
        with open(image_path, 'wb') as f:
            f.write(base64.b64decode(image_data))

        # Get file size for logging
        file_size = os.path.getsize(image_path)
        logger.info(f"Image saved: {image_id}.{ext} ({file_size:,} bytes) for session {session_id}")

        return Response(json.dumps({
            "image_id": image_id,
            "filename": f"{image_id}.{ext}",
            "media_type": media_type,
            "size": file_size,
            "relative_path": f"images/{image_id}.{ext}"
        }), mimetype='application/json')

    except Exception as e:
        logger.error(f"Image upload error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/images/<session_id>/<image_filename>', methods=['GET'])
def get_image(session_id, image_filename):
    """
    获取存储的图片文件

    返回图片的 base64 数据或直接返回二进制
    """
    try:
        ctx_manager = get_context_manager()
        session_dir = ctx_manager.get_session_dir(session_id)
        image_path = os.path.join(session_dir, "images", image_filename)

        if not os.path.exists(image_path):
            return Response(json.dumps({"error": "Image not found"}),
                          status=404, mimetype='application/json')

        # Determine media type from extension
        ext = image_filename.split('.')[-1].lower()
        media_type = EXT_TO_MEDIA_TYPE.get(ext, 'image/png')

        # Check if client wants base64 or binary
        want_base64 = request.args.get('format') == 'base64'

        if want_base64:
            import base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            return Response(json.dumps({
                "image_id": image_filename.rsplit('.', 1)[0],
                "media_type": media_type,
                "data": image_data
            }), mimetype='application/json')
        else:
            # Return binary image directly
            with open(image_path, 'rb') as f:
                image_data = f.read()
            return Response(image_data, mimetype=media_type)

    except Exception as e:
        logger.error(f"Get image error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


# ==================== Tool Result Management (like Claude Code) ====================

@app.route('/v1/tool-results/<session_id>', methods=['GET'])
def list_tool_results_api(session_id):
    """List all tool results for a session"""
    try:
        ctx_manager = get_context_manager()
        results = ctx_manager.list_tool_results(session_id)
        return Response(json.dumps({
            "session_id": session_id,
            "results": results,
            "count": len(results)
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"List tool results error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/tool-results/<session_id>/<tool_use_id>', methods=['GET'])
def get_tool_result_api(session_id, tool_use_id):
    """Get a specific tool result content"""
    try:
        ctx_manager = get_context_manager()
        # Use find_tool_result_file to search for files with new naming convention
        file_path = ctx_manager.find_tool_result_file(session_id, tool_use_id)

        if not file_path or not os.path.exists(file_path):
            return Response(json.dumps({
                "error": "Tool result not found",
                "session_id": session_id,
                "tool_use_id": tool_use_id
            }), status=404, mimetype='application/json')

        content = ctx_manager.load_tool_result(file_path)
        return Response(json.dumps({
            "session_id": session_id,
            "tool_use_id": tool_use_id,
            "content": content,
            "size": len(content) if content else 0
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Get tool result error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/tool-results', methods=['POST'])
def save_tool_result_api():
    """
    Save a tool result (auto-detects if it should be stored in file or inline).
    Used when tool execution produces large output.

    Request body:
    {
        "session_id": "...",
        "tool_use_id": "...",
        "tool_name": "...",  // optional
        "result": "..."
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        tool_use_id = data.get('tool_use_id')
        tool_name = data.get('tool_name')
        result = data.get('result', '')

        if not session_id or not tool_use_id:
            return Response(json.dumps({
                "error": "session_id and tool_use_id are required"
            }), status=400, mimetype='application/json')

        ctx_manager = get_context_manager()
        result_info = ctx_manager.save_tool_result(session_id, tool_use_id, result, tool_name)

        return Response(json.dumps(result_info), mimetype='application/json')
    except Exception as e:
        logger.error(f"Save tool result error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


@app.route('/v1/tool-results/cleanup', methods=['POST'])
def cleanup_tool_results_api():
    """
    Clean up old tool results.
    Request body: {"max_age_days": 7}  // optional, defaults to 7
    """
    try:
        data = request.get_json() or {}
        max_age_days = data.get('max_age_days', 7)

        ctx_manager = get_context_manager()
        cleaned_count = ctx_manager.cleanup_old_tool_results(max_age_days)

        return Response(json.dumps({
            "success": True,
            "cleaned_sessions": cleaned_count,
            "max_age_days": max_age_days
        }), mimetype='application/json')
    except Exception as e:
        logger.error(f"Cleanup tool results error: {e}")
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')


# ==================== MCP 工具端点 ====================

@app.route('/v1/tools', methods=['GET'])
def list_tools():
    """列出所有可用的 MCP 工具（动态生成技能描述）"""
    return Response(
        json.dumps({"tools": get_tool_definitions()}),
        mimetype='application/json'
    )


@app.route('/v1/tools/execute', methods=['POST'])
def execute_tool_endpoint():
    """执行 MCP 工具"""
    try:
        raw_data = request.get_data(as_text=True)
        logger.info(f"Raw tool request: {raw_data[:500]}")

        try:
            data = request.get_json(force=True)
        except Exception as json_err:
            logger.error(f"JSON parse error: {json_err}, raw: {raw_data[:200]}")
            # Return error instead of trying to fix malformed JSON
            return jsonify({"error": f"Invalid JSON: {str(json_err)}"}), 400

        tool_name = data.get('name')
        tool_input = data.get('input', {})

        logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

        # Validate required inputs for specific tools (prevent truncated tool calls)
        truncation_checks = {
            'write_file': ['content'],
            'edit': ['old_string', 'new_string'],
            'execute_command': ['command'],
            'web_search': ['query'],
            'web_fetch': ['url'],
            'read_file': ['path'],
            'create_directory': ['path'],
            'git_commit': ['message'],
        }

        if tool_name in truncation_checks:
            missing_params = [p for p in truncation_checks[tool_name] if p not in tool_input or not tool_input.get(p)]
            if missing_params:
                logger.warning(f"{tool_name} called without required params: {missing_params} - likely truncated response")
                return Response(
                    json.dumps({"result": {
                        "error": f"Tool call incomplete: required parameter(s) {missing_params} missing for {tool_name}. The model response may have been truncated.",
                        "truncated": True,
                        "tool": tool_name,
                        "missing_params": missing_params
                    }}),
                    mimetype='application/json'
                )

        # 统一使用 execute_tool，内部会处理 MCP 工具的懒加载检查
        result = execute_tool(tool_name, tool_input)

        return Response(
            json.dumps({"result": result}),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


# ==================== Skill 管理端点 ====================

@app.route('/v1/skills', methods=['GET'])
def list_skills():
    """列出所有可用的 Skills"""
    try:
        loader = get_skill_loader()
        skills = loader.list_skills()
        return Response(
            json.dumps({"skills": skills}),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"List skills error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/skills/<skill_name>', methods=['GET'])
def get_skill(skill_name):
    """获取特定 Skill 的详细信息"""
    try:
        loader = get_skill_loader()
        skill = loader.get_skill(skill_name)
        if skill:
            return Response(
                json.dumps(skill.to_dict()),
                mimetype='application/json'
            )
        else:
            return Response(
                json.dumps({"error": f"Skill '{skill_name}' not found"}),
                status=404,
                mimetype='application/json'
            )
    except Exception as e:
        logger.error(f"Get skill error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/skills/<skill_name>/instructions', methods=['GET'])
def get_skill_instructions(skill_name):
    """获取 Skill 的完整指令"""
    try:
        loader = get_skill_loader()
        instructions = loader.get_skill_instructions(skill_name)
        if instructions:
            return Response(
                json.dumps({"instructions": instructions}),
                mimetype='application/json'
            )
        else:
            return Response(
                json.dumps({"error": f"Skill '{skill_name}' not found"}),
                status=404,
                mimetype='application/json'
            )
    except Exception as e:
        logger.error(f"Get skill instructions error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/skills/reload', methods=['POST'])
def reload_skills():
    """重新加载所有 Skills (强制刷新)"""
    try:
        loader = get_skill_loader()
        loader.reload(force=True)  # Force reload bypassing cache
        skills = loader.list_skills()
        return Response(
            json.dumps({"message": "Skills reloaded", "count": len(skills), "skills": skills}),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Reload skills error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/skills/path', methods=['GET'])
def get_skills_path():
    """获取 Skills 目录路径"""
    try:
        loader = get_skill_loader()
        return Response(
            json.dumps({"path": str(loader.skills_dir)}),
            mimetype='application/json'
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/config/aws', methods=['GET', 'POST'])
def aws_config():
    """获取或设置 AWS 凭证配置"""
    from auth.config_manager import AuthMethod
    from auth.aws_profiles import list_profiles

    if request.method == 'GET':
        try:
            status = auth_manager.get_status()
            # 添加 profiles 列表
            status['profiles'] = list_profiles()
            return Response(
                json.dumps(status),
                mimetype='application/json'
            )
        except Exception as e:
            logger.error(f"AWS config error: {e}")
            return Response(
                json.dumps({"error": str(e)}),
                status=500,
                mimetype='application/json'
            )
    else:
        try:
            data = request.get_json()
            method = data.get('method', 'env_file')

            if method == 'env_file':
                # 保存到 .env 文件
                access_key = data.get('access_key_id', '')
                secret_key = data.get('secret_access_key', '')
                region = data.get('region', 'us-east-1')

                if access_key and secret_key:
                    auth_manager.save_env_file(access_key, secret_key, region)

                # 更新配置方法
                auth_manager.update_config(method='env_file', region=region)

            elif method == 'aws_profile':
                profile_name = data.get('profile_name', 'default')
                auth_manager.update_config(
                    method='aws_profile',
                    profile_name=profile_name
                )

            elif method == 'env_vars':
                auth_manager.update_config(method='env_vars')

            return Response(
                json.dumps({"success": True}),
                mimetype='application/json'
            )
        except Exception as e:
            logger.error(f"AWS config save error: {e}")
            return Response(
                json.dumps({"error": str(e)}),
                status=500,
                mimetype='application/json'
            )


@app.route('/v1/config/aws/test', methods=['GET'])
def aws_test_connection():
    """测试 AWS 连接"""
    try:
        result = auth_manager.validate_credentials()
        return Response(
            json.dumps(result),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"AWS test error: {e}")
        return Response(
            json.dumps({"valid": False, "error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/config/memory', methods=['GET', 'POST'])
def memory_config():
    """获取或设置 AgentCore Memory 配置"""
    from memory_sync import load_memory_config, save_memory_config, get_memory_config, CONFIG_FILE

    if request.method == 'GET':
        config = get_memory_config()
        return Response(
            json.dumps(config),
            mimetype='application/json'
        )
    else:
        try:
            data = request.get_json()
            new_config = {
                "memory_id": data.get('memory_id', ''),
                "memory_region": data.get('memory_region', 'us-west-2'),
                "memory_enabled": data.get('memory_enabled', True)
            }

            # 当启用 Memory Sync 时，自动配置 4 种内置策略
            if new_config.get('memory_enabled') and new_config.get('memory_id'):
                setup_result = auto_setup_memory_strategies(
                    new_config['memory_id'],
                    new_config['memory_region']
                )
                if setup_result.get('strategies'):
                    # 保存策略配置到 ltm 节点
                    full_config = {}
                    if os.path.exists(CONFIG_FILE):
                        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                            full_config = json.load(f)

                    if 'memory' not in full_config:
                        full_config['memory'] = {}

                    full_config['memory']['ltm'] = {
                        'enabled': True,
                        'strategies': setup_result['strategies'],
                        'sync_interval': 900
                    }

                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(full_config, f, indent=2, ensure_ascii=False)

                    logger.info(f"Auto-configured {len(setup_result['strategies'])} strategies for Memory")

            if save_memory_config(new_config):
                logger.info(f"Memory config updated: {new_config.get('memory_id')}")
                return Response(
                    json.dumps({"success": True}),
                    mimetype='application/json'
                )
            else:
                return Response(
                    json.dumps({"error": "Failed to save config"}),
                    status=500,
                    mimetype='application/json'
                )
        except Exception as e:
            logger.error(f"Memory config error: {e}")
            return Response(
                json.dumps({"error": str(e)}),
                status=500,
                mimetype='application/json'
            )


@app.route('/v1/config/memory/strategies/refresh', methods=['POST'])
def refresh_memory_strategies():
    """刷新 LTM 策略配置，从 Memory 资源获取实际的策略 ID 和 namespace"""
    from memory_sync import get_memory_config, CONFIG_FILE

    try:
        config = get_memory_config()
        memory_id = config.get('memory_id')
        region = config.get('memory_region', 'us-west-2')

        if not memory_id:
            return Response(
                json.dumps({"success": False, "error": "Memory ID not configured"}),
                status=400,
                mimetype='application/json'
            )

        # 调用 auto_setup 函数获取实际的策略配置
        setup_result = auto_setup_memory_strategies(memory_id, region)

        if setup_result.get('strategies'):
            # 更新配置文件中的策略
            full_config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)

            if 'memory' not in full_config:
                full_config['memory'] = {}

            full_config['memory']['ltm'] = {
                'enabled': True,
                'strategies': setup_result['strategies'],
                'sync_interval': full_config.get('memory', {}).get('ltm', {}).get('sync_interval', 900)
            }

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)

            logger.info(f"Refreshed {len(setup_result['strategies'])} strategies from Memory")

            return Response(
                json.dumps({
                    "success": True,
                    "strategies": setup_result['strategies'],
                    "message": f"Discovered {len(setup_result['strategies'])} strategies"
                }),
                mimetype='application/json'
            )
        else:
            return Response(
                json.dumps({
                    "success": False,
                    "error": setup_result.get('error', 'No strategies found'),
                    "strategies": []
                }),
                status=500,
                mimetype='application/json'
            )

    except Exception as e:
        logger.error(f"Refresh strategies error: {e}")
        return Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json'
        )


def auto_setup_memory_strategies(memory_id: str, region: str, create_missing: bool = True) -> dict:
    """
    自动设置 Memory 的 LTM 策略
    1. 获取现有策略
    2. 如果缺少必要策略，自动创建（semantic, summary, userPreference）
    3. 创建 EPISODIC 策略，配置 reflection 指向其他策略的 namespace
    4. 返回所有策略的实际 namespace
    """
    import boto3
    import time

    actor_id = "springo"
    strategies = []

    # 策略类型映射
    type_display_map = {
        'SEMANTIC': 'SEMANTIC_MEMORY',
        'USER_PREFERENCE': 'USER_PREFERENCE',
        'SUMMARIZATION': 'SUMMARIZATION',
        'EPISODIC': 'EPISODIC_MEMORY',
    }

    # 需要的 LTM 策略定义（不包括 EPISODIC，单独处理）
    required_ltm_strategies = {
        'ConversationFacts': {'type': 'semanticMemoryStrategy', 'description': 'Extract semantic facts from conversations'},
        'UserPreferences': {'type': 'userPreferenceMemoryStrategy', 'description': 'Extract user preferences'},
        'ConversationSummary': {'type': 'summaryMemoryStrategy', 'description': 'Generate conversation summaries'},
    }

    try:
        # 使用控制面板客户端获取 Memory 详情
        control_client = boto3.client('bedrock-agentcore-control', region_name=region)

        try:
            memory_response = control_client.get_memory(memoryId=memory_id)
            logger.info(f"Got memory details for {memory_id}")

            # 从响应中提取策略信息 - 正确的路径是 response['memory']['strategies']
            memory_data = memory_response.get('memory', {})
            memory_strategies = memory_data.get('strategies', [])
            logger.info(f"Found {len(memory_strategies)} strategies in memory resource")

            for mem_strategy in memory_strategies:
                # 直接从策略对象获取字段
                strategy_id = mem_strategy.get('strategyId', '')
                strategy_name = mem_strategy.get('name', '')
                strategy_type_raw = mem_strategy.get('type', 'SEMANTIC')
                strategy_description = mem_strategy.get('description', '')
                namespace_patterns = mem_strategy.get('namespaces', [])

                # 映射类型显示名称
                strategy_type = type_display_map.get(strategy_type_raw, strategy_type_raw)

                # 构建实际的 namespace
                # 模板格式: /strategies/{memoryStrategyId}/actors/{actorId}/
                # 或: /episodes/{memoryStrategyId}/actors/{actorId}/
                if namespace_patterns:
                    pattern = namespace_patterns[0]
                    actual_namespace = pattern.replace('{memoryStrategyId}', strategy_id).replace('{actorId}', actor_id)
                    # 移除 {sessionId} 占位符（如果存在）
                    if '{sessionId}' in actual_namespace:
                        actual_namespace = actual_namespace.replace('/sessions/{sessionId}/', '/')
                else:
                    # 默认 namespace 格式
                    actual_namespace = f"/strategies/{strategy_id}/actors/{actor_id}/"

                strategies.append({
                    'id': strategy_id,
                    'name': strategy_name,
                    'type': strategy_type,
                    'namespace': actual_namespace,
                    'description': strategy_description or f'{strategy_name} strategy'
                })

                logger.info(f"Found strategy: {strategy_name} (ID: {strategy_id}) -> {actual_namespace}")

            # 检查是否需要创建缺失的 LTM 策略（不包括 EPISODIC）
            if create_missing:
                existing_names = [s['name'] for s in strategies]
                existing_types = [s['type'] for s in strategies]
                strategies_to_create = []

                for name, config in required_ltm_strategies.items():
                    if name not in existing_names:
                        strategies_to_create.append({
                            config['type']: {
                                'name': name,
                                'description': config['description']
                            }
                        })

                if strategies_to_create:
                    logger.info(f"Creating {len(strategies_to_create)} missing LTM strategies: {[list(s.keys())[0] for s in strategies_to_create]}")
                    try:
                        update_response = control_client.update_memory(
                            memoryId=memory_id,
                            memoryStrategies={
                                'addMemoryStrategies': strategies_to_create
                            }
                        )

                        # 重新获取策略列表
                        new_strategies = update_response.get('memory', {}).get('strategies', [])
                        logger.info(f"After update, memory has {len(new_strategies)} strategies")

                        # 重新处理所有策略
                        strategies = []
                        for mem_strategy in new_strategies:
                            strategy_id = mem_strategy.get('strategyId', '')
                            strategy_name = mem_strategy.get('name', '')
                            strategy_type_raw = mem_strategy.get('type', 'SEMANTIC')
                            strategy_description = mem_strategy.get('description', '')
                            namespace_patterns = mem_strategy.get('namespaces', [])

                            strategy_type = type_display_map.get(strategy_type_raw, strategy_type_raw)

                            if namespace_patterns:
                                pattern = namespace_patterns[0]
                                actual_namespace = pattern.replace('{memoryStrategyId}', strategy_id).replace('{actorId}', actor_id)
                                if '{sessionId}' in actual_namespace:
                                    actual_namespace = actual_namespace.replace('/sessions/{sessionId}/', '/')
                            else:
                                actual_namespace = f"/strategies/{strategy_id}/actors/{actor_id}/"

                            strategies.append({
                                'id': strategy_id,
                                'name': strategy_name,
                                'type': strategy_type,
                                'namespace': actual_namespace,
                                'description': strategy_description or f'{strategy_name} strategy'
                            })

                    except Exception as create_err:
                        logger.warning(f"Failed to create missing LTM strategies: {create_err}")

                # 处理 EPISODIC 策略的 reflection 配置
                # 收集所有非 EPISODIC 策略的 namespace 用于 reflection
                reflection_namespaces = []
                episodic_strategy = None

                for s in strategies:
                    if s['type'] == 'EPISODIC_MEMORY':
                        episodic_strategy = s
                    else:
                        # 收集其他策略的 namespace 用于 reflection
                        reflection_namespaces.append(s['namespace'])

                logger.info(f"Reflection namespaces for EPISODIC: {reflection_namespaces}")

                # 如果有 reflection namespaces，需要检查/更新 EPISODIC 策略
                if reflection_namespaces:
                    try:
                        if episodic_strategy:
                            # 删除现有的 EPISODIC 策略，然后重新创建带 reflection 的
                            logger.info(f"Deleting existing EPISODIC strategy: {episodic_strategy['id']}")
                            control_client.update_memory(
                                memoryId=memory_id,
                                memoryStrategies={
                                    'deleteMemoryStrategies': [
                                        {'memoryStrategyId': episodic_strategy['id']}
                                    ]
                                }
                            )
                            # 等待删除完成
                            time.sleep(2)

                        # 创建带 reflectionConfiguration 的 EPISODIC 策略
                        logger.info(f"Creating EPISODIC strategy with reflection to: {reflection_namespaces}")
                        episodic_response = control_client.update_memory(
                            memoryId=memory_id,
                            memoryStrategies={
                                'addMemoryStrategies': [
                                    {
                                        'episodicMemoryStrategy': {
                                            'name': 'ConversationEpisodes',
                                            'description': 'Episodic memory with reflection from other LTM strategies',
                                            'reflectionConfiguration': {
                                                'namespaces': reflection_namespaces
                                            }
                                        }
                                    }
                                ]
                            }
                        )

                        # 更新 strategies 列表 - 移除旧的 EPISODIC，添加新的
                        strategies = [s for s in strategies if s['type'] != 'EPISODIC_MEMORY']

                        # 从响应中获取新创建的 EPISODIC 策略信息
                        new_strategies_list = episodic_response.get('memory', {}).get('strategies', [])
                        for mem_strategy in new_strategies_list:
                            if mem_strategy.get('type') == 'EPISODIC':
                                strategy_id = mem_strategy.get('strategyId', '')
                                strategy_name = mem_strategy.get('name', '')
                                namespace_patterns = mem_strategy.get('namespaces', [])

                                if namespace_patterns:
                                    pattern = namespace_patterns[0]
                                    actual_namespace = pattern.replace('{memoryStrategyId}', strategy_id).replace('{actorId}', actor_id)
                                    if '{sessionId}' in actual_namespace:
                                        actual_namespace = actual_namespace.replace('/sessions/{sessionId}/', '/')
                                else:
                                    actual_namespace = f"/episodes/{strategy_id}/actors/{actor_id}/"

                                strategies.append({
                                    'id': strategy_id,
                                    'name': strategy_name,
                                    'type': 'EPISODIC_MEMORY',
                                    'namespace': actual_namespace,
                                    'description': 'Episodic memory with reflection',
                                    'has_reflection': True,
                                    'reflection_namespaces': reflection_namespaces
                                })
                                logger.info(f"Created EPISODIC strategy with reflection: {strategy_id}")
                                break

                    except Exception as episodic_err:
                        logger.warning(f"Failed to setup EPISODIC with reflection: {episodic_err}")

        except control_client.exceptions.ResourceNotFoundException:
            logger.warning(f"Memory {memory_id} not found")
        except Exception as e:
            logger.warning(f"Failed to get memory details via control plane: {e}")

        # 如果没有发现任何策略，使用默认配置（但标记为未验证）
        if not strategies:
            logger.warning("No strategies discovered, using default configuration")
            default_strategies = [
                {'type': 'SEMANTIC_MEMORY', 'name': 'ConversationFacts', 'description': 'Extract semantic facts from conversations'},
                {'type': 'USER_PREFERENCE', 'name': 'UserPreferences', 'description': 'Extract user preferences'},
                {'type': 'SUMMARIZATION', 'name': 'SessionSummary', 'description': 'Summarize conversation sessions'},
                {'type': 'EPISODIC_MEMORY', 'name': 'EpisodicMemory', 'description': 'Store episodic memories'},
            ]
            for strategy_type in default_strategies:
                strategies.append({
                    'id': f"{strategy_type['name']}-{actor_id}",
                    'name': strategy_type['name'],
                    'type': strategy_type['type'],
                    'namespace': f"/strategies/{strategy_type['name']}/actors/{actor_id}/",
                    'description': strategy_type['description'],
                    'unverified': True  # 标记为未验证
                })

        return {
            'success': True,
            'strategies': strategies,
            'actor_id': actor_id
        }

    except Exception as e:
        logger.warning(f"Auto-setup strategies failed: {e}")
        # 返回空策略列表，让用户知道需要手动配置
        return {
            'success': False,
            'strategies': [],
            'actor_id': actor_id,
            'error': str(e)
        }


@app.route('/v1/config/memory/create', methods=['POST'])
def memory_create():
    """
    自动创建 AgentCore Memory 和 S3 桶

    在用户选择的区域同时创建:
    1. AgentCore Memory
    2. S3 桶 (用于存储图片和工具结果)

    请求体: {"region": "us-west-2"}
    """
    from memory_sync import create_memory, save_memory_config, init_memory_sync
    from s3_sync import create_s3_bucket, init_s3_sync

    try:
        data = request.get_json() or {}
        region = data.get('region', 'us-west-2')

        logger.info(f"Creating Memory and S3 bucket in region: {region}")

        result = {
            "region": region,
            "memory": None,
            "s3": None
        }

        # 1. 创建 AgentCore Memory
        memory_result = create_memory(region)
        result["memory"] = memory_result

        if not memory_result.get("success"):
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create Memory: {memory_result.get('error')}",
                    "result": result
                }),
                status=500,
                mimetype='application/json'
            )

        # 2. 创建 S3 桶
        s3_result = create_s3_bucket(region)
        result["s3"] = s3_result

        if not s3_result.get("success"):
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create S3 bucket: {s3_result.get('error')}",
                    "result": result
                }),
                status=500,
                mimetype='application/json'
            )

        # 3. 重新初始化同步服务
        try:
            init_s3_sync(s3_result["bucket"], region)
            init_memory_sync(memory_result["memory_id"], region)
        except Exception as e:
            logger.warning(f"Failed to reinitialize sync services: {e}")

        logger.info(f"Created Memory ({memory_result['memory_id']}) and S3 ({s3_result['bucket']}) in {region}")

        return Response(
            json.dumps({
                "success": True,
                "region": region,
                "memory_id": memory_result.get("memory_id"),
                "memory_name": memory_result.get("memory_name"),
                "s3_bucket": s3_result.get("bucket"),
                "result": result
            }),
            mimetype='application/json'
        )

    except Exception as e:
        logger.error(f"Memory/S3 create error: {e}")
        return Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/config/memory/test', methods=['GET'])
def memory_test_connection():
    """测试 AgentCore Memory 连接"""
    from memory_sync import get_memory_config

    try:
        config = get_memory_config()
        if not config.get('memory_id'):
            return Response(
                json.dumps({"success": False, "error": "Memory ID not configured"}),
                mimetype='application/json'
            )

        if not config.get('memory_enabled'):
            return Response(
                json.dumps({"success": False, "error": "Memory sync is disabled"}),
                mimetype='application/json'
            )

        # Try to connect to AgentCore Memory using data plane API
        import boto3
        client = boto3.client('bedrock-agentcore', region_name=config['memory_region'])

        # Use list_actors to verify connection - only requires memoryId
        response = client.list_actors(
            memoryId=config['memory_id'],
            maxResults=1
        )

        return Response(
            json.dumps({
                "success": True,
                "memory_id": config['memory_id'],
                "region": config['memory_region']
            }),
            mimetype='application/json'
        )
    except Exception as e:
        error_msg = str(e)
        # Check for specific error types
        if 'ResourceNotFoundException' in error_msg:
            error_msg = f"Memory '{config.get('memory_id')}' not found"
        elif 'AccessDeniedException' in error_msg:
            error_msg = "Access denied - check IAM permissions"

        logger.error(f"Memory test error: {e}")
        return Response(
            json.dumps({"success": False, "error": error_msg}),
            mimetype='application/json'
        )


@app.route('/v1/memory/status', methods=['GET'])
def memory_sync_status():
    """获取 AgentCore Memory 同步状态"""
    from memory_sync import get_memory_config, get_sync_manager
    import os
    import json as json_module

    try:
        config = get_memory_config()
        sync_manager = get_sync_manager()

        # Base status
        status = {
            "enabled": config.get('memory_enabled', False),
            "memory_id": config.get('memory_id', ''),
            "region": config.get('memory_region', 'us-west-2'),
            "running": sync_manager is not None,
            "sessions_synced": 0,
            "total_events": 0,
            "pending": 0
        }

        if not config.get('memory_enabled') or not config.get('memory_id'):
            status["status"] = "disabled"
            return Response(json.dumps(status), mimetype='application/json')

        if sync_manager is None:
            status["status"] = "not_running"
            return Response(json.dumps(status), mimetype='application/json')

        # Count synced sessions and events
        sessions_dir = os.path.expanduser("~/.springo/sessions")
        if os.path.exists(sessions_dir):
            synced_sessions = 0
            total_synced = 0

            for session_id in os.listdir(sessions_dir):
                sync_file = os.path.join(sessions_dir, session_id, ".sync_state.json")
                if os.path.exists(sync_file):
                    try:
                        with open(sync_file, 'r') as f:
                            state = json_module.load(f)
                            if state.get("last_synced_index", -1) >= 0:
                                synced_sessions += 1
                                total_synced += state.get("total_synced", 0)
                    except Exception:
                        pass

            status["sessions_synced"] = synced_sessions
            status["total_events"] = total_synced

        # Check queue size (approximate pending count)
        try:
            status["pending"] = sync_manager.upload_queue.qsize()
        except Exception:
            pass

        # Determine status
        if status["pending"] > 0:
            status["status"] = "syncing"
        else:
            status["status"] = "synced"

        return Response(json.dumps(status), mimetype='application/json')

    except Exception as e:
        logger.error(f"Memory status error: {e}")
        return Response(
            json.dumps({"status": "error", "error": str(e)}),
            mimetype='application/json'
        )


@app.route('/v1/config/s3', methods=['GET', 'POST'])
def s3_config():
    """获取或设置 S3 同步配置"""
    from s3_sync import load_s3_config, save_s3_config, get_s3_config

    if request.method == 'GET':
        config = get_s3_config()
        return Response(json.dumps(config), mimetype='application/json')

    # POST - 更新配置
    try:
        data = request.get_json() or {}
        current_config = load_s3_config()

        # 更新指定字段
        for key in ['s3_bucket', 's3_region', 's3_enabled', 's3_upload_on_sync']:
            if key in data:
                current_config[key] = data[key]

        if save_s3_config(current_config):
            return Response(json.dumps({
                "success": True,
                "config": current_config
            }), mimetype='application/json')
        else:
            return Response(
                json.dumps({"error": "Failed to save config"}),
                status=500,
                mimetype='application/json'
            )
    except Exception as e:
        logger.error(f"S3 config error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/s3/status', methods=['GET'])
def s3_sync_status():
    """获取 S3 同步状态"""
    try:
        s3_manager = get_s3_manager()
        config = get_s3_config()

        status = {
            "enabled": config.get('s3_enabled', False),
            "bucket": config.get('s3_bucket', 'springo'),
            "region": config.get('s3_region', 'us-east-1'),
            "running": s3_manager is not None and s3_manager._initialized,
            "account_id": s3_manager._account_id if s3_manager else None,
            "cached_uploads": len(s3_manager._upload_cache) if s3_manager else 0
        }

        if s3_manager and s3_manager._initialized:
            status["status"] = "ready"
        elif not config.get('s3_enabled'):
            status["status"] = "disabled"
        else:
            status["status"] = "not_initialized"

        return Response(json.dumps(status), mimetype='application/json')

    except Exception as e:
        logger.error(f"S3 status error: {e}")
        return Response(
            json.dumps({"status": "error", "error": str(e)}),
            mimetype='application/json'
        )


@app.route('/v1/s3/sync/<session_id>', methods=['POST'])
def s3_sync_session(session_id):
    """手动同步会话文件到 S3"""
    try:
        s3_manager = get_s3_manager()

        if not s3_manager:
            return Response(
                json.dumps({"error": "S3 sync not initialized"}),
                status=400,
                mimetype='application/json'
            )

        # 同步会话文件
        uploaded = s3_manager.sync_session_files(session_id)

        return Response(json.dumps({
            "success": True,
            "session_id": session_id,
            "uploaded_count": len(uploaded),
            "files": uploaded
        }), mimetype='application/json')

    except Exception as e:
        logger.error(f"S3 sync error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/config/working-dir', methods=['GET', 'POST'])
def working_dir_config():
    """获取或设置当前工作目录"""
    if request.method == 'GET':
        return Response(
            json.dumps({"working_dir": get_working_dir()}),
            mimetype='application/json'
        )
    else:
        try:
            data = request.get_json()
            working_dir = data.get('working_dir', '')
            # Expand ~ to user's home directory before validation
            expanded_dir = os.path.expanduser(working_dir) if working_dir else ''
            if expanded_dir and os.path.isdir(expanded_dir):
                set_working_dir(working_dir)  # set_working_dir will expand again, that's fine
                logger.info(f"Working directory updated: {expanded_dir}")
                return Response(
                    json.dumps({"success": True, "working_dir": expanded_dir}),
                    mimetype='application/json'
                )
            else:
                return Response(
                    json.dumps({"error": f"Invalid directory: {working_dir}"}),
                    status=400,
                    mimetype='application/json'
                )
        except Exception as e:
            logger.error(f"Working dir config error: {e}")
            return Response(
                json.dumps({"error": str(e)}),
                status=500,
                mimetype='application/json'
            )


# ==================== 外部 MCP 服务器端点 ====================

@app.route('/v1/mcp/servers', methods=['GET'])
def list_mcp_servers():
    """列出所有配置的 MCP 服务器（含状态：configured/running/error/disabled）"""
    manager = get_mcp_manager()
    return Response(
        json.dumps({
            "servers": manager.get_configured_servers(),
            "config_path": manager.config_path
        }),
        mimetype='application/json'
    )


@app.route('/v1/mcp/tools', methods=['GET'])
def list_mcp_tools():
    """列出所有外部 MCP 服务器的工具"""
    tools = get_mcp_tools()
    return Response(
        json.dumps({"tools": tools, "count": len(tools)}),
        mimetype='application/json'
    )


@app.route('/v1/mcp/initialize', methods=['POST'])
def init_mcp_servers():
    """初始化 MCP 服务器连接"""
    try:
        success = initialize_mcp_servers()
        manager = get_mcp_manager()
        return Response(
            json.dumps({
                "success": success,
                "servers": manager.get_status()
            }),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"MCP init error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/mcp/servers', methods=['POST'])
def add_mcp_server():
    """添加并启动一个新的 MCP 服务器"""
    try:
        data = request.get_json()
        name = data.get('name')
        command = data.get('command')
        args = data.get('args', [])
        env = data.get('env', {})

        if not name or not command:
            return Response(
                json.dumps({"error": "name and command are required"}),
                status=400,
                mimetype='application/json'
            )

        manager = get_mcp_manager()
        success = manager.add_server(name, command, args, env)

        if success:
            # Save to config file
            config_path = manager.config_path
            try:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                else:
                    config = {"servers": []}

                # Add new server to config
                config["servers"].append({
                    "name": name,
                    "command": command,
                    "args": args,
                    "env": env,
                    "enabled": True
                })

                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save MCP config: {e}")

            return Response(
                json.dumps({"success": True, "servers": manager.get_status()}),
                mimetype='application/json'
            )
        else:
            return Response(
                json.dumps({"error": f"Failed to start server {name}"}),
                status=500,
                mimetype='application/json'
            )
    except Exception as e:
        logger.error(f"Add MCP server error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


@app.route('/v1/mcp/servers/<server_name>', methods=['DELETE'])
def remove_mcp_server(server_name):
    """停止并移除一个 MCP 服务器"""
    try:
        manager = get_mcp_manager()
        manager.remove_server(server_name)

        # Update config file
        config_path = manager.config_path
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)

                # Remove server from config
                config["servers"] = [s for s in config.get("servers", []) if s.get("name") != server_name]

                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to update MCP config: {e}")

        return Response(
            json.dumps({"success": True, "servers": manager.get_status()}),
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Remove MCP server error: {e}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )


# ==================== API Info ====================

@app.route('/', methods=['GET'])
def index():
    """API info endpoint"""
    return Response(json.dumps({
        "name": "Claude Bedrock Proxy",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "messages": "/v1/messages",
            "models": "/v1/models",
            "tools": "/v1/tools",
            "health": "/health"
        }
    }), mimetype='application/json')


@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def catch_all(path):
    """捕获未处理的请求"""
    logger.info(f"Unhandled: {request.method} /{path}")
    return Response(json.dumps({"error": "not found", "path": path}), status=404, mimetype='application/json')


if __name__ == '__main__':
    import argparse
    import ssl

    parser = argparse.ArgumentParser(description='Claude Web Application with Bedrock Backend')
    parser.add_argument('--https', action='store_true', help='Enable HTTPS mode')
    parser.add_argument('--port', type=int, default=8080, help='Port (default: 8080)')
    parser.add_argument('--host', default='127.0.0.1', help='Host (default: 127.0.0.1)')
    parser.add_argument('--debug', action='store_true', default=False, help='Enable debug mode (default: False)')
    parser.add_argument('--no-debug', action='store_true', help='Explicitly disable debug mode')
    args = parser.parse_args()

    # Debug mode: enabled by default in development, can be disabled with --no-debug
    debug_mode = args.debug and not args.no_debug

    # 获取认证状态
    status = auth_manager.get_status()
    auth_status = "已配置" if status.get('configured') else "未配置"
    connected_status = "已连接" if status.get('connected') else "未连接"

    # HTTPS 配置
    ssl_context = None
    protocol = "http"
    port = args.port

    if args.https:
        cert_dir = os.path.join(BASE_DIR, 'certs')
        cert_file = os.path.join(cert_dir, 'server.pem')
        key_file = os.path.join(cert_dir, 'server-key.pem')

        if os.path.exists(cert_file) and os.path.exists(key_file):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(cert_file, key_file)
            protocol = "https"
            port = 443 if args.port == 8080 else args.port
            logger.info(f"HTTPS mode enabled with certs from {cert_dir}")
        else:
            logger.error(f"Certificate files not found in {cert_dir}")
            logger.error("Please run: ./generate_certs.sh")
            exit(1)

    # 获取工具数量（使用动态生成的工具定义）
    tool_count = len(get_tool_definitions())

    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║         Claude Web Application (Bedrock Backend)                  ║
╠═══════════════════════════════════════════════════════════════════╣
║  功能:                                                            ║
║    ✓ Claude AI 对话 (AWS Bedrock)                                 ║
║    ✓ {tool_count} 个 MCP 工具 (文件/Git/Web/浏览器)                        ║
║    ✓ 上下文管理和 Token 计数                                      ║
║    ✓ 外部 MCP 服务器支持                                          ║
║                                                                   ║
║  访问地址:                                                        ║
║    聊天界面: {protocol}://{args.host}:{port}/chat                          ║
║    AWS配置:  {protocol}://{args.host}:{port}/config                        ║
║                                                                   ║
║  AWS 状态:                                                        ║
║    Region: {AWS_REGION}                                                ║
║    认证:   {auth_status} | {connected_status}                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    # Auto-initialize MCP servers at startup
    try:
        success = initialize_mcp_servers()
        if success:
            manager = get_mcp_manager()
            mcp_status = manager.get_status()
            if mcp_status:
                print(f"    MCP 服务器已启动: {list(mcp_status.keys())}")

            # Pre-activate commonly used MCP tools to avoid tool_search overhead
            # This saves 1 API round-trip per query (~1-3 seconds)
            from tool_registry import get_tool_registry
            registry = get_tool_registry()

            PREACTIVATE_TOOLS = [
                'strands-agents__search_docs',
                'strands-agents__fetch_doc',
                'bedrock-agentcore__search_agentcore_docs',
                'bedrock-agentcore__fetch_agentcore_doc',
                'web-search__brave_web_search',
                'context7__resolve-library-id',
                'context7__query-docs',
            ]

            activated = []
            for tool_name in PREACTIVATE_TOOLS:
                if registry.is_deferred(tool_name):
                    # Get tool definition from MCP server
                    server_name = tool_name.split('__')[0]
                    actual_tool = tool_name.split('__', 1)[1]
                    if server_name in manager.servers:
                        server = manager.servers[server_name]
                        for tool in server.tools:
                            if tool['name'] == actual_tool:
                                definition = {
                                    'name': tool_name,
                                    'description': tool.get('description', ''),
                                    'input_schema': tool.get('inputSchema', {'type': 'object', 'properties': {}})
                                }
                                if registry.activate(tool_name, definition):
                                    activated.append(tool_name)
                                break

            if activated:
                print(f"    预激活工具: {len(activated)} 个")
                logger.info(f"Pre-activated tools: {activated}")
    except Exception as e:
        logger.warning(f"MCP auto-init failed: {e}")

    # 初始化 S3 同步（先于 Memory 同步，因为 Memory 同步可能依赖 S3）
    try:
        if init_s3_sync():
            print("    ✓ S3 同步已启动")
        else:
            print("    - S3 同步未启用 (检查配置)")
    except Exception as e:
        print(f"    ✗ S3 同步初始化失败: {e}")

    # 初始化 AgentCore Memory 同步
    try:
        if init_memory_sync():
            print("    ✓ AgentCore Memory 同步已启动")
        else:
            print("    - AgentCore Memory 同步未启用 (检查配置)")
    except Exception as e:
        logger.warning(f"Memory sync init failed: {e}")

    # 注册退出处理
    import atexit
    atexit.register(shutdown_memory_sync)
    atexit.register(shutdown_s3_sync)

    app.run(host=args.host, port=port, debug=debug_mode, threaded=True, ssl_context=ssl_context)
