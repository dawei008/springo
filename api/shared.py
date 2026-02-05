"""
Shared utilities for API blueprints
Common functions, constants, and helpers
"""

import json
import time
import uuid
import logging
from typing import Generator
from flask import Response
import boto3
from botocore.config import Config

from auth.config_manager import AuthConfigManager
from mcp_tools import get_tool_definitions, get_working_dir
from error_handler import format_error_response, get_http_status

logger = logging.getLogger(__name__)

# Auth manager singleton
auth_manager = AuthConfigManager()

# AWS Bedrock configuration
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

DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

## Response Style

**IMPORTANT: Do NOT use emoji in your responses.** Keep your responses clean and professional without emoji characters. Use plain text formatting instead.

## Tool Selection Guidelines

| Task | Best Tool | Avoid |
|------|-----------|-------|
| Check current time/date | `execute_command` with `date` | guessing the date |
| Find files by pattern | `glob` | bash find/ls |
| Search file content | `grep` | bash grep/rg |
| Read single file | `read_file` | bash cat |
| Read multiple files | `read_files` | multiple read_file calls |
| Edit existing file | `edit` | write_file (unless rewriting) |
| Execute commands | `execute_command` | - |
| Long-running tasks | `execute_command` with run_in_background=true | - |
| Complex multi-step tasks | `task` (launches background agent) | blocking main session |
| Deep code exploration | `task` with agent_type="explore" | manual grep/read loops |
| Track complex tasks | `todo_write` | - |
| Ask user questions | `ask_user` | - |
| Plan before coding | `enter_plan_mode` | - |

## Best Practices

1. **Check current time first** when tasks involve dates, deadlines, or searching for "latest/recent" content - use `execute_command` with `date +"%Y-%m-%d"` or `date +"%Y"`
2. **Use parallel tool calls** when operations are independent
3. **Prefer specialized tools** over bash commands
4. **Background tasks** for long operations (use run_in_background=true)
5. **Use edit for modifications**, write_file for new files
6. **Reduce round trips** - chain related commands with &&
7. **Avoid truncation** - keep content under 500 lines per file

## Scheduler Tool

Use the `scheduler` tool when users want to:
- Set reminders ("提醒我...", "remind me...")
- Schedule recurring tasks ("每天...", "every day...")
- Delay execution ("N分钟后...", "in N minutes...")
- Plan future actions ("明天...", "tomorrow...")

Parse natural language time expressions:
| Expression | schedule_type | schedule_value |
|-----------|--------------|----------------|
| 每天早上9点 | cron | 0 9 * * * |
| 每周一 | cron | 0 9 * * 1 |
| 每小时 | cron | 0 * * * * |
| 30分钟后 | delay | 30 |
| 1小时后 | delay | 60 |
| 明天下午3点 | once | 2026-02-06T15:00:00 |

Example usage:
```
scheduler(
    action="create",
    name="检查邮件提醒",
    schedule_type="cron",
    schedule_value="0 9 * * *",
    prompt="提醒用户检查邮件并查看重要消息"
)
```

## Background Task Tool (task)

Use the `task` tool to launch background agents for complex work that shouldn't block the conversation:

**When to use:**
- Deep codebase exploration (analyzing architecture, tracing dependencies)
- Tasks requiring extensive file reading (>10 files)
- Research tasks that may take multiple iterations
- Parallel independent subtasks that can run concurrently
- Long-running analysis (security audit, code review, refactoring planning)

**Agent types:**
- `explore` - Code exploration and architecture understanding
- `research` - Web research and information gathering
- `implement` - Code implementation and modifications
- `general` - General purpose tasks

**Example:**
```
task(
    description="Analyze authentication flow",
    prompt="Trace the login flow from frontend to backend, identify all auth-related files",
    agent_type="explore"
)
```

The task runs in a separate session and results are returned when complete.
"""


def get_bedrock_client():
    """Get Bedrock client using auth config manager"""
    try:
        return auth_manager.get_bedrock_client()
    except Exception as e:
        logger.warning(f"Failed to get configured client, falling back to default: {e}")
        config = Config(
            region_name=AWS_REGION,
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        return boto3.client('bedrock-runtime', config=config)


def convert_anthropic_to_bedrock(anthropic_request: dict, include_tools: bool = True) -> tuple:
    """Convert Anthropic API format to Bedrock format"""
    model = anthropic_request.get("model", "claude-3-5-sonnet-20241022")
    bedrock_model_id = BEDROCK_MODEL_MAPPING.get(model, f"us.anthropic.{model}-v1:0")

    bedrock_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": anthropic_request.get("max_tokens", 16384),
        "messages": anthropic_request.get("messages", []),
    }

    for key in ["system", "temperature", "top_p", "top_k", "stop_sequences", "tools", "tool_choice"]:
        if key in anthropic_request:
            bedrock_body[key] = anthropic_request[key]

    # Add working directory info to system prompt
    current_working_dir = get_working_dir()
    working_dir_info = ""
    if current_working_dir:
        working_dir_info = f"""

## Current Working Directory
**IMPORTANT**: The user has set the working directory to: `{current_working_dir}`
- All file operations should be relative to this directory
"""

    if "system" not in bedrock_body:
        bedrock_body["system"] = DEFAULT_SYSTEM_PROMPT + working_dir_info
    else:
        bedrock_body["system"] = bedrock_body["system"] + working_dir_info

    if include_tools and "tools" not in bedrock_body:
        bedrock_body["tools"] = get_tool_definitions()

    return bedrock_model_id, bedrock_body


def handle_streaming_response(bedrock_client, model_id: str, body: dict, original_model: str) -> Generator:
    """Handle streaming response with text and tool calls"""
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
        error_response = format_error_response(e, lang="zh")
        yield f"event: error\ndata: {json.dumps(error_response)}\n\n"


def json_response(data: dict, status: int = 200) -> Response:
    """Create JSON response"""
    return Response(json.dumps(data), status=status, mimetype='application/json')


def error_response(error: Exception, lang: str = "zh") -> Response:
    """Create error response"""
    error_data = format_error_response(error, lang=lang)
    status = get_http_status(error)
    return Response(json.dumps(error_data), status=status, mimetype='application/json')
