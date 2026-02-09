"""
Springo Bedrock Async Service
异步 Bedrock 服务 - 使用 aioboto3
"""
import json
import uuid
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

import aioboto3
from botocore.config import Config

from ..config import settings
from .error_handler import format_error_response as _eh_format_error, get_http_status, should_retry, parse_error

logger = logging.getLogger(__name__)


# Default context limits (200K models)
_DEFAULT_LIMITS = {
    "max_context_tokens": 200000,
    "compact_threshold": 120000,
    "warning_threshold": 160000,
    "target_after_summary": 40000,
    "max_output_tokens": 64000,
}

# Model Registry — single source of truth for all model capabilities
MODEL_REGISTRY = {
    "claude-opus-4-6": {
        "bedrock_id": "us.anthropic.claude-opus-4-6-v1",
        "display_name": "Claude Opus 4.6",
        "family": "opus",
        "max_context_tokens": 1000000,
        "compact_threshold": 600000,
        "warning_threshold": 800000,
        "target_after_summary": 200000,
        "max_output_tokens": 64000,
        "recommended": True,
    },
    "claude-opus-4-5-20251101": {
        "bedrock_id": "us.anthropic.claude-opus-4-5-20251101-v1:0",
        "display_name": "Claude Opus 4.5",
        "family": "opus",
        **_DEFAULT_LIMITS,
    },
    "claude-sonnet-4-5-20250929": {
        "bedrock_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "display_name": "Claude Sonnet 4.5",
        "family": "sonnet",
        **_DEFAULT_LIMITS,
    },
    "claude-haiku-4-5-20251001": {
        "bedrock_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "display_name": "Claude Haiku 4.5",
        "family": "haiku",
        **_DEFAULT_LIMITS,
    },
    "claude-sonnet-4-20250514": {
        "bedrock_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "display_name": "Claude Sonnet 4",
        "family": "sonnet",
        **_DEFAULT_LIMITS,
    },
    "claude-opus-4-20250514": {
        "bedrock_id": "us.anthropic.claude-opus-4-20250514-v1:0",
        "display_name": "Claude Opus 4",
        "family": "opus",
        **_DEFAULT_LIMITS,
    },
    "claude-3-7-sonnet-20250219": {
        "bedrock_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "display_name": "Claude 3.7 Sonnet",
        "family": "sonnet",
        **_DEFAULT_LIMITS,
    },
    "claude-3-5-sonnet-20241022": {
        "bedrock_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "display_name": "Claude 3.5 Sonnet",
        "family": "sonnet",
        **_DEFAULT_LIMITS,
    },
    "claude-3-5-haiku-20241022": {
        "bedrock_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "display_name": "Claude 3.5 Haiku",
        "family": "haiku",
        **_DEFAULT_LIMITS,
    },
    "claude-3-opus-20240229": {
        "bedrock_id": "us.anthropic.claude-3-opus-20240229-v1:0",
        "display_name": "Claude 3 Opus",
        "family": "opus",
        **_DEFAULT_LIMITS,
    },
    "claude-3-sonnet-20240229": {
        "bedrock_id": "us.anthropic.claude-3-sonnet-20240229-v1:0",
        "display_name": "Claude 3 Sonnet",
        "family": "sonnet",
        **_DEFAULT_LIMITS,
    },
    "claude-3-haiku-20240307": {
        "bedrock_id": "us.anthropic.claude-3-haiku-20240307-v1:0",
        "display_name": "Claude 3 Haiku",
        "family": "haiku",
        **_DEFAULT_LIMITS,
    },
}

# Backward-compatible flat mapping
BEDROCK_MODEL_MAPPING = {k: v["bedrock_id"] for k, v in MODEL_REGISTRY.items()}


def get_model_limits(model: str) -> dict:
    """Get context limits for a model. Returns defaults for unknown models."""
    info = MODEL_REGISTRY.get(model)
    if info:
        return {
            "max_context_tokens": info["max_context_tokens"],
            "compact_threshold": info["compact_threshold"],
            "warning_threshold": info["warning_threshold"],
            "target_after_summary": info["target_after_summary"],
            "max_output_tokens": info["max_output_tokens"],
        }
    return dict(_DEFAULT_LIMITS)


def format_error_response(error: Exception, lang: str = "zh") -> dict:
    """Format error into structured response — delegates to error_handler module"""
    return _eh_format_error(error, lang=lang)


# Default system prompt (aligned with Flask shared.py)
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

## CRITICAL RULE - NO EMOJIS (STRICTLY ENFORCED)

**ABSOLUTELY DO NOT use any emojis, emoticons, or unicode symbols in your responses.** This is a strict requirement:
- NO emoji characters (😀, 📁, ✅, ❌, 🎉, ✨, 📝, etc.)
- NO unicode symbols (✓, ✗, •, →, ★, etc.)
- Use plain text only: "Done", "Error", "Success", "-", "->", "*"
- This applies to ALL responses and ALL generated files
- Violation of this rule is considered a critical error

## CRITICAL: Always Use Absolute Paths

**For ALL tool calls that accept file or directory paths, you MUST use absolute paths.**

- Correct: `/Users/name/project/file.txt`
- Correct: `~/.springo/skills/pptx/script.py` (~ expands to home directory)
- Wrong: `file.txt` (relative path)
- Wrong: `./project/file.txt` (relative path)
- Wrong: `workspace/file.txt` (relative path)

The working directory will be provided below. Use it to construct absolute paths.

{SPRINGO_MD_PLACEHOLDER}

## Important: Two Directory Scopes

You work with TWO separate directory trees. Do NOT confuse them:

1. **Project directory** (working_dir) — source code, config files, app logic
2. **`~/.springo/`** — Springo's runtime data: skills, sessions, config, scripts

When searching for **skills**, **sessions**, **config**, or **scripts**, ALWAYS use `~/.springo/` as the base path:
- Skills: `read_file ~/.springo/skills/<name>/SKILL.md` or `list_directory ~/.springo/skills/`
- Config: `read_file ~/.springo/config.json`
- For glob/grep, set `path` parameter to `~/.springo/` — do NOT search the project directory for these.

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

1. **Check current time first** when tasks involve dates, deadlines, or searching for "latest/recent" content - use `execute_command` with `date +"%Y-%m-%d"` or `date +"%Y"`

2. **Use parallel tool calls** when operations are independent:
   - Reading multiple unrelated files
   - Searching in different directories
   - Running independent commands
   - IMPORTANT: Call multiple tools in the same response when they don't depend on each other

3. **Prefer specialized tools** over bash commands:
   - `glob` for file pattern matching (sorted by modification time)
   - `grep` for content search (supports output_mode: files_with_matches, content, count)
   - `edit` for precise string replacement (safer than write_file)
   - `read_files` for batch file reading

4. **Background tasks** for long operations:
   - Use `run_in_background=true` for builds, tests, servers
   - Check status with `get_task_status`
   - List all with `list_background_tasks`

5. **Edit vs Write**:
   - Use `edit` when modifying specific parts of a file
   - Use `write_file` only when creating new files or complete rewrites

6. **Reduce round trips**:
   - Chain related bash commands with && when they must run sequentially
   - Use `read_files` instead of multiple `read_file` calls

7. **Avoid truncation errors**:
   - When writing files, keep content under 500 lines per file
   - For large content, split into multiple smaller files
   - When generating HTML/code files, keep them focused and modular
   - If creating multiple files, do them in separate tool calls, not all at once

8. **Web search (MCP only)**:
   - Use MCP tool: web-search__brave_web_search (built-in web_search removed)
   - **IMPORTANT**: When user asks for "最新"/"latest"/"recent" content, ALWAYS use freshness parameter:
     - freshness="pd" (past day) - for breaking news
     - freshness="pw" (past week) - RECOMMENDED for "最新" queries
     - freshness="pm" (past month) - for broader recent content
     - freshness="py" (past year) - for annual content
   - Use ENGLISH keywords in query, include current year for recent content
   - Use count=5-10 for initial exploration
   - For news: use web-search__brave_news_search

9. **Specialized agents** with `task` tool:
   - Use agent_type="explore" for code exploration
   - Use agent_type="research" for web research
   - Use agent_type="implement" for code implementation

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

## Safety

- Commands are checked for dangerous patterns
- Sensitive files (.env, credentials, etc.) require confirmation
- File operations are restricted to allowed directories
"""


class BedrockService:
    """异步 Bedrock 服务"""

    def __init__(self, region: str = None):
        self.region = region or settings.aws_region
        self._session_kwargs = {}  # kwargs for aioboto3.Session
        self._client_kwargs = {}   # extra kwargs for client creation

        # Integrate AuthConfigManager credentials from ~/.springo/config.json
        try:
            from .auth_manager import get_aws_config
            import os as _os
            aws_config = get_aws_config()
            method = aws_config.get("method") or aws_config.get("auth_method", "")

            if method == "aws_profile" and aws_config.get("profile"):
                self._session_kwargs["profile_name"] = aws_config["profile"]
                logger.info(f"BedrockService using AWS profile: {aws_config['profile']}")

            elif method == "manual_keys":
                # Manual keys are set in os.environ by set_aws_config()
                if _os.environ.get("AWS_ACCESS_KEY_ID"):
                    logger.info("BedrockService using manual keys from environment")

            elif method == "sso":
                # SSO credentials are set in os.environ by select_sso_role()
                if _os.environ.get("AWS_ACCESS_KEY_ID"):
                    logger.info("BedrockService using SSO credentials from environment")

            elif method == "env_file":
                # Load .env file into environment
                env_file = _os.path.expanduser("~/.springo/.env")
                if _os.path.exists(env_file):
                    with open(env_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                _os.environ[key.strip()] = value.strip().strip('"').strip("'")
                    logger.info("BedrockService loaded credentials from .env file")

            if aws_config.get("region"):
                self.region = aws_config["region"]

        except Exception as e:
            logger.debug(f"Auth config not available, using default credentials: {e}")

        self.session = aioboto3.Session(**self._session_kwargs)
        self.config = Config(
            region_name=self.region,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            connect_timeout=settings.bedrock_connect_timeout,
            read_timeout=settings.bedrock_read_timeout
        )
    
    def get_bedrock_model_id(self, model: str) -> str:
        """获取 Bedrock 模型 ID"""
        return BEDROCK_MODEL_MAPPING.get(model, f"us.anthropic.{model}-v1:0")
    
    def convert_request_to_bedrock(
        self,
        request: Dict[str, Any],
        include_tools: bool = True,
        tools: list = None,
        working_dir: str = None
    ) -> tuple[str, Dict[str, Any]]:
        """将 Anthropic API 请求转换为 Bedrock 格式

        NOTE: Deep-copies messages to avoid mutating the caller's list
        (time prefix injection would otherwise leak into persisted sessions).
        """
        import copy
        model = request.get("model", "claude-sonnet-4-5-20250929")
        bedrock_model_id = self.get_bedrock_model_id(model)

        bedrock_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.get("max_tokens", 16384),
            "messages": copy.deepcopy(request.get("messages", [])),
        }
        
        # Copy optional parameters
        for key in ["temperature", "top_p", "top_k", "stop_sequences", "tool_choice"]:
            if key in request and request[key] is not None:
                bedrock_body[key] = request[key]
        
        # Handle system prompt - inject SPRINGO.md content
        from ..utils.springo_md import load_springo_md
        system_prompt = request.get("system") or DEFAULT_SYSTEM_PROMPT
        springo_md = load_springo_md()
        if springo_md:
            system_prompt = system_prompt.replace("{SPRINGO_MD_PLACEHOLDER}", springo_md)
        else:
            system_prompt = system_prompt.replace("{SPRINGO_MD_PLACEHOLDER}", "")
        if working_dir:
            import os
            springo_config_dir = os.path.expanduser("~/.springo")
            system_prompt += (
                f"\n\n## Working Directory & Springo Config\n"
                f"- **Working Directory**: `{working_dir}` — project code lives here\n"
                f"- **Springo Config**: `{springo_config_dir}/` — settings, skills, sessions, scripts\n"
                f"  - Skills: `{springo_config_dir}/skills/` (each subfolder has SKILL.md)\n"
                f"  - Config: `{springo_config_dir}/config.json`\n"
                f"- For `glob`/`grep`: use `path` parameter to search the right directory\n"
                f"  - Project files: `path: \"{working_dir}\"`\n"
                f"  - Skills/config: `path: \"{springo_config_dir}\"`\n"
            )
        bedrock_body["system"] = system_prompt
        
        # Handle tools
        if include_tools:
            if request.get("tools"):
                bedrock_body["tools"] = request["tools"]
            elif tools:
                bedrock_body["tools"] = tools
        
        # Inject current time into last user message
        if bedrock_body.get("messages"):
            now = datetime.now()
            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            weekday = weekday_names[now.weekday()]
            time_str = now.strftime('%Y-%m-%d %H:%M')
            time_prefix = f"[Current time: {time_str} ({weekday})]\n\n"
            
            # Find last user message
            for i in range(len(bedrock_body["messages"]) - 1, -1, -1):
                msg = bedrock_body["messages"][i]
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        bedrock_body["messages"][i]["content"] = time_prefix + content
                    elif isinstance(content, list) and len(content) > 0:
                        if content[0].get("type") == "text":
                            content[0]["text"] = time_prefix + content[0].get("text", "")
                    break
        
        return bedrock_model_id, bedrock_body
    
    async def invoke_model(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """异步非流式调用 Bedrock (with 429 retry)"""
        import random

        for attempt in range(max_retries):
            try:
                async with self.session.client(
                    'bedrock-runtime',
                    region_name=self.region,
                    config=self.config
                ) as client:
                    response = await client.invoke_model(
                        modelId=model_id,
                        body=json.dumps(body),
                        contentType="application/json",
                        accept="application/json"
                    )
                    response_body = await response['body'].read()
                    return json.loads(response_body)
            except Exception as e:
                error_str = str(e)
                is_throttle = 'ThrottlingException' in error_str or '429' in error_str or 'Too Many Requests' in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Bedrock 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    continue
                raise
    
    async def invoke_model_stream(
        self,
        model_id: str,
        body: Dict[str, Any],
        original_model: str,
        max_retries: int = 3
    ) -> AsyncGenerator[str, None]:
        """
        异步流式调用 Bedrock (with 429 retry)

        Yields:
            SSE formatted strings
        """
        import random

        # Retry connection phase for 429 throttling
        response = None
        client_ctx = None
        for attempt in range(max_retries):
            try:
                client_ctx = self.session.client(
                    'bedrock-runtime',
                    region_name=self.region,
                    config=self.config
                )
                client = await client_ctx.__aenter__()
                response = await client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body),
                    contentType="application/json",
                    accept="application/json"
                )
                break  # Connection succeeded
            except Exception as e:
                error_str = str(e)
                is_throttle = 'ThrottlingException' in error_str or '429' in error_str or 'Too Many Requests' in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Bedrock stream 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                    if client_ctx:
                        try:
                            await client_ctx.__aexit__(None, None, None)
                        except Exception:
                            pass
                    await asyncio.sleep(backoff)
                    continue
                # Non-retryable error or last attempt
                if client_ctx:
                    try:
                        await client_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                raise

        try:
            message_id = f"msg_{uuid.uuid4().hex[:24]}"
            current_block_index = -1
            started_message = False

            async for event in response['body']:
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

            # Ensure message was started
            if not started_message:
                empty_msg = {
                    'id': message_id,
                    'type': 'message',
                    'role': 'assistant',
                    'content': [],
                    'model': original_model,
                    'stop_reason': None,
                    'stop_sequence': None,
                    'usage': {'input_tokens': 0, 'output_tokens': 0}
                }
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': empty_msg})}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        except Exception as e:
            logger.error(f"Bedrock streaming error: {e}")
            error_data = format_error_response(e)
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        finally:
            if client_ctx:
                try:
                    await client_ctx.__aexit__(None, None, None)
                except Exception:
                    pass

    async def invoke_model_stream_text(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming call that yields simple parsed dicts for agent team use.

        Yields:
            {"type": "delta", "text": "chunk"}
            {"type": "usage", "input_tokens": N, "output_tokens": N}
        """
        import random

        response = None
        client_ctx = None
        for attempt in range(max_retries):
            try:
                client_ctx = self.session.client(
                    'bedrock-runtime',
                    region_name=self.region,
                    config=self.config
                )
                client = await client_ctx.__aenter__()
                response = await client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body),
                    contentType="application/json",
                    accept="application/json"
                )
                break
            except Exception as e:
                error_str = str(e)
                is_throttle = 'ThrottlingException' in error_str or '429' in error_str or 'Too Many Requests' in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Bedrock stream_text 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                    if client_ctx:
                        try:
                            await client_ctx.__aexit__(None, None, None)
                        except Exception:
                            pass
                    await asyncio.sleep(backoff)
                    continue
                if client_ctx:
                    try:
                        await client_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                raise

        try:
            async for event in response['body']:
                chunk = json.loads(event.get("chunk", {}).get("bytes", b"{}"))
                chunk_type = chunk.get("type")

                if chunk_type == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield {"type": "delta", "text": delta.get("text", "")}

                elif chunk_type == "message_delta":
                    usage = chunk.get("usage", {})
                    if usage:
                        yield {"type": "usage", "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}

                elif chunk_type == "message_start":
                    msg = chunk.get("message", {})
                    usage = msg.get("usage", {})
                    if usage:
                        yield {"type": "usage", "input_tokens": usage.get("input_tokens", 0), "output_tokens": 0}

        except Exception as e:
            logger.error(f"Bedrock stream_text error: {e}")
            raise
        finally:
            if client_ctx:
                try:
                    await client_ctx.__aexit__(None, None, None)
                except Exception:
                    pass


# Singleton instance
_bedrock_service: Optional[BedrockService] = None


def get_bedrock_service() -> BedrockService:
    """获取 Bedrock 服务单例"""
    global _bedrock_service
    if _bedrock_service is None:
        _bedrock_service = BedrockService()
    return _bedrock_service
