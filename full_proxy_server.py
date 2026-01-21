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
from typing import Generator
from flask import Flask, request, Response, stream_with_context
import boto3
from botocore.config import Config

# 认证模块
from auth.config_manager import AuthConfigManager
from ui.routes import config_bp

# MCP 工具模块
from mcp_tools import get_tool_definitions, execute_tool, set_search_config, get_search_config, set_working_dir, get_working_dir

# 上下文管理模块
from context_manager import get_context_manager, get_stats as get_context_stats

# MCP 服务器客户端
from mcp_client import get_mcp_manager, initialize_mcp_servers, get_mcp_tools, call_mcp_tool, shutdown_mcp_servers

# Skill 加载器
from skill_loader import get_skill_loader

# 错误处理模块
from error_handler import format_error_response, get_user_friendly_message, should_retry, get_http_status

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

# 注册配置 UI Blueprint
app.register_blueprint(config_bp)

# MCP auto-initialization flag
_mcp_initialized = False

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
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        return boto3.client('bedrock-runtime', config=config)


# Default system prompt with tool usage guidelines
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

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

7. **Web search efficiency**:
   - Combine related searches into one comprehensive query
   - Use max_results=5-10 for initial exploration, increase only if needed
   - After searching, fetch specific URLs rather than searching again

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
    # IMPORTANT: Dynamically inject the current working directory so the model knows where to create files
    current_working_dir = get_working_dir()
    working_dir_info = ""
    if current_working_dir:
        working_dir_info = f"""

## Current Working Directory
**IMPORTANT**: The user has set the working directory to: `{current_working_dir}`
- All file operations should be relative to this directory
- When creating files/directories, use paths relative to this working directory
- Example: To create a file at `{current_working_dir}/output/test.txt`, use path `output/test.txt`
"""

    if "system" not in bedrock_body:
        bedrock_body["system"] = DEFAULT_SYSTEM_PROMPT + working_dir_info
    else:
        # Append working directory info to existing system prompt
        bedrock_body["system"] = bedrock_body["system"] + working_dir_info

    # 自动添加 MCP 工具 (动态生成，包含技能列表)
    if include_tools and "tools" not in bedrock_body:
        bedrock_body["tools"] = get_tool_definitions()

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


@app.route('/v1/sessions/<session_id>', methods=['POST'])
def save_session_messages(session_id):
    """保存消息到会话"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        ctx_manager = get_context_manager()

        if isinstance(messages, list):
            ctx_manager.save_messages(session_id, messages)
        else:
            ctx_manager.save_message(session_id, messages)

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
            import re
            fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', raw_data)
            data = json.loads(fixed)

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
    """重新加载所有 Skills"""
    try:
        loader = get_skill_loader()
        loader.reload()
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


# ==================== 搜索引擎配置端点 ====================

@app.route('/v1/config/search', methods=['GET', 'POST'])
def search_config():
    """获取或设置搜索引擎配置"""
    if request.method == 'GET':
        return Response(
            json.dumps(get_search_config()),
            mimetype='application/json'
        )
    else:
        try:
            data = request.get_json()
            engine = data.get('engine', 'duckduckgo')
            api_key = data.get('apiKey', '')
            custom_url = data.get('customUrl', '')
            set_search_config(engine, api_key, custom_url)
            logger.info(f"Search config updated: engine={engine}")
            return Response(
                json.dumps({"success": True, "engine": engine}),
                mimetype='application/json'
            )
        except Exception as e:
            logger.error(f"Search config error: {e}")
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
            if working_dir and os.path.isdir(working_dir):
                set_working_dir(working_dir)
                logger.info(f"Working directory updated: {working_dir}")
                return Response(
                    json.dumps({"success": True, "working_dir": working_dir}),
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
    """列出所有已连接的 MCP 服务器"""
    manager = get_mcp_manager()
    return Response(
        json.dumps({
            "servers": manager.get_status(),
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
    args = parser.parse_args()

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
    except Exception as e:
        logger.warning(f"MCP auto-init failed: {e}")

    app.run(host=args.host, port=port, debug=True, threaded=True, ssl_context=ssl_context)
