"""
Springo Bedrock Async Service
异步 Bedrock 服务 - 使用 aioboto3
"""
import base64
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
from .model_registry import (
    MODEL_REGISTRY,
    BEDROCK_MODEL_MAPPING,
    get_model_limits,
    get_bedrock_id,
    get_model_info,
)

logger = logging.getLogger(__name__)


def format_error_response(error: Exception, lang: str = "zh") -> dict:
    """Format error into structured response — delegates to error_handler module"""
    return _eh_format_error(error, lang=lang)


# ---------------------------------------------------------------------------
# System prompts — split into common (model-agnostic) + Anthropic-specific
# ---------------------------------------------------------------------------

ANTHROPIC_SYSTEM_PROMPT = """
## CRITICAL RULE - NO EMOJIS (STRICTLY ENFORCED)

**ABSOLUTELY DO NOT use any emojis, emoticons, or unicode symbols in your responses.** This is a strict requirement:
- NO emoji characters (😀, 📁, ✅, ❌, 🎉, ✨, 📝, etc.)
- NO unicode symbols (✓, ✗, •, →, ★, etc.)
- Use plain text only: "Done", "Error", "Success", "-", "->", "*"
- This applies to ALL responses and ALL generated files
- Violation of this rule is considered a critical error
"""

# Default system prompt (aligned with Flask shared.py)
COMMON_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

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

# Combined prompt for backward compatibility (used when api_format is unknown)
DEFAULT_SYSTEM_PROMPT = COMMON_SYSTEM_PROMPT + ANTHROPIC_SYSTEM_PROMPT


def _get_system_prompt_for_model(model_name: str) -> str:
    """Return the appropriate system prompt based on model's api_format."""
    info = get_model_info(model_name)
    if info and info.get("api_format") == "converse":
        return COMMON_SYSTEM_PROMPT
    # Default to full prompt (common + anthropic) for Claude and unknown models
    return COMMON_SYSTEM_PROMPT + ANTHROPIC_SYSTEM_PROMPT


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
        return get_bedrock_id(model)

    @staticmethod
    def get_api_format(model: str) -> str:
        """Return the api_format for *model* ('anthropic' or 'converse').

        Defaults to 'anthropic' for backward compatibility when the model
        is not found in the registry.
        """
        info = get_model_info(model)
        return info["api_format"] if info else "anthropic"
    
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
        model = request.get("model", "claude-opus-4-6")
        bedrock_model_id = self.get_bedrock_model_id(model)

        # Determine api_format for this model
        model_info = get_model_info(model)
        api_format = model_info["api_format"] if model_info else "anthropic"

        bedrock_body = {
            "max_tokens": request.get("max_tokens", 16384),
            "messages": copy.deepcopy(request.get("messages", [])),
        }

        # Only add anthropic_version for Anthropic-format models
        if api_format == "anthropic":
            bedrock_body["anthropic_version"] = "bedrock-2023-05-31"

        # Copy optional parameters
        for key in ["temperature", "top_p", "top_k", "stop_sequences", "tool_choice"]:
            if key in request and request[key] is not None:
                bedrock_body[key] = request[key]

        # Handle system prompt - inject SPRINGO.md content
        # Use model-appropriate system prompt (common only for Converse models)
        from ..utils.springo_md import load_springo_md
        system_prompt = request.get("system") or _get_system_prompt_for_model(model)
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
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """异步非流式调用 Bedrock (with 429 retry).

        When *api_format* is ``"converse"`` the call is routed through the
        Converse API; otherwise the legacy ``invoke_model`` path is used.
        """
        if api_format == "converse":
            return await self._converse_invoke(model_id, body, max_retries=max_retries)

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
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        异步流式调用 Bedrock (with 429 retry)

        When *api_format* is ``"converse"`` the call is routed through
        ``_converse_stream``; otherwise the legacy InvokeModel path is used.

        Yields:
            SSE formatted strings
        """
        if api_format == "converse":
            async for evt in self._converse_stream(model_id, body, original_model, max_retries=max_retries):
                yield evt
            return

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
        max_retries: int = 3,
        api_format: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming call that yields simple parsed dicts for agent team use.

        When *api_format* is ``"converse"`` the call is routed through
        ``_converse_stream_text``; otherwise the legacy InvokeModel path is used.

        Yields:
            {"type": "delta", "text": "chunk"}
            {"type": "usage", "input_tokens": N, "output_tokens": N}
        """
        if api_format == "converse":
            async for evt in self._converse_stream_text(model_id, body, max_retries=max_retries):
                yield evt
            return

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

    # ------------------------------------------------------------------
    # Converse API helpers (for non-Anthropic models)
    # ------------------------------------------------------------------

    @staticmethod
    def _to_converse_messages(messages: list) -> list:
        """Convert Anthropic-format messages to Converse API format.

        Converse expects:
          [{"role": "user", "content": [{"text": "..."}]}, ...]

        Anthropic messages may have ``content`` as a plain string or a list of
        typed blocks (text, image, tool_use, tool_result, ...).
        """
        converse_msgs = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                converse_msgs.append({
                    "role": role,
                    "content": [{"text": content}] if content else [{"text": " "}],
                })
            elif isinstance(content, list):
                blocks = []
                for block in content:
                    if isinstance(block, str):
                        blocks.append({"text": block})
                    elif isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            blocks.append({"text": block.get("text", "")})
                        elif btype == "image":
                            # Pass through image blocks for vision models
                            source = block.get("source", {})
                            data = source.get("data", "")
                            # Converse API expects raw bytes, Anthropic stores base64
                            if isinstance(data, str):
                                data = base64.b64decode(data)
                            blocks.append({
                                "image": {
                                    "format": source.get("media_type", "image/png").split("/")[-1],
                                    "source": {"bytes": data},
                                }
                            })
                        elif btype == "tool_use":
                            blocks.append({
                                "toolUse": {
                                    "toolUseId": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}),
                                }
                            })
                        elif btype == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, str):
                                result_blocks = [{"text": result_content}]
                            elif isinstance(result_content, list):
                                result_blocks = []
                                for rb in result_content:
                                    if isinstance(rb, str):
                                        result_blocks.append({"text": rb})
                                    elif isinstance(rb, dict) and rb.get("type") == "text":
                                        result_blocks.append({"text": rb.get("text", "")})
                                    else:
                                        result_blocks.append({"text": json.dumps(rb)})
                            else:
                                result_blocks = [{"text": str(result_content)}]
                            blocks.append({
                                "toolResult": {
                                    "toolUseId": block.get("tool_use_id", ""),
                                    "content": result_blocks,
                                    "status": "error" if block.get("is_error") else "success",
                                }
                            })
                        else:
                            # Fallback: serialize unknown block as text
                            blocks.append({"text": json.dumps(block)})
                if not blocks:
                    blocks = [{"text": " "}]
                converse_msgs.append({"role": role, "content": blocks})
            else:
                converse_msgs.append({
                    "role": role,
                    "content": [{"text": str(content)}],
                })
        return converse_msgs

    @staticmethod
    def _to_converse_tools(tools: list) -> list:
        """Convert Anthropic tool definitions to Converse toolConfig format."""
        converse_tools = []
        for tool in tools:
            spec = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "inputSchema": {
                    "json": tool.get("input_schema", tool.get("inputSchema", {}))
                },
            }
            converse_tools.append({"toolSpec": spec})
        return converse_tools

    def _build_converse_kwargs(
        self, model_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build kwargs dict for ``client.converse()`` / ``client.converse_stream()``."""
        system_prompt = body.get("system", "")
        system_block = [{"text": system_prompt}] if system_prompt else []

        messages = self._to_converse_messages(body.get("messages", []))

        inference_config: Dict[str, Any] = {}
        if "max_tokens" in body:
            inference_config["maxTokens"] = body["max_tokens"]
        if "temperature" in body:
            inference_config["temperature"] = body["temperature"]
        if "top_p" in body:
            inference_config["topP"] = body["top_p"]
        if "stop_sequences" in body:
            inference_config["stopSequences"] = body["stop_sequences"]

        kwargs: Dict[str, Any] = {
            "modelId": model_id,
            "messages": messages,
        }
        if system_block:
            kwargs["system"] = system_block
        if inference_config:
            kwargs["inferenceConfig"] = inference_config

        # Convert tools if present
        tools = body.get("tools")
        if tools:
            converse_tools = self._to_converse_tools(tools)
            kwargs["toolConfig"] = {"tools": converse_tools}

            # tool_choice mapping
            tool_choice = body.get("tool_choice")
            if tool_choice:
                tc_type = tool_choice.get("type", "auto")
                if tc_type == "any":
                    kwargs["toolConfig"]["toolChoice"] = {"any": {}}
                elif tc_type == "tool":
                    kwargs["toolConfig"]["toolChoice"] = {
                        "tool": {"name": tool_choice.get("name", "")}
                    }
                else:
                    kwargs["toolConfig"]["toolChoice"] = {"auto": {}}

        return kwargs

    async def _converse_invoke(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Non-streaming Converse API call.  Returns an Anthropic-shaped response."""
        import random

        kwargs = self._build_converse_kwargs(model_id, body)

        for attempt in range(max_retries):
            try:
                async with self.session.client(
                    "bedrock-runtime",
                    region_name=self.region,
                    config=self.config,
                ) as client:
                    response = await client.converse(**kwargs)

                # Convert Converse response to Anthropic-like shape
                content_blocks = []
                for block in response.get("output", {}).get("message", {}).get("content", []):
                    if "text" in block:
                        content_blocks.append({"type": "text", "text": block["text"]})
                    elif "toolUse" in block:
                        tu = block["toolUse"]
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tu.get("toolUseId", ""),
                            "name": tu.get("name", ""),
                            "input": tu.get("input", {}),
                        })

                stop_reason_map = {
                    "end_turn": "end_turn",
                    "tool_use": "tool_use",
                    "max_tokens": "max_tokens",
                    "stop_sequence": "stop_sequence",
                }
                raw_stop = response.get("stopReason", "end_turn")
                stop_reason = stop_reason_map.get(raw_stop, raw_stop)

                usage = response.get("usage", {})

                return {
                    "content": content_blocks,
                    "stop_reason": stop_reason,
                    "usage": {
                        "input_tokens": usage.get("inputTokens", 0),
                        "output_tokens": usage.get("outputTokens", 0),
                    },
                }
            except Exception as e:
                error_str = str(e)
                is_throttle = "ThrottlingException" in error_str or "429" in error_str or "Too Many Requests" in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Converse 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    continue
                raise

    async def _converse_stream(
        self,
        model_id: str,
        body: Dict[str, Any],
        original_model: str,
        max_retries: int = 3,
    ) -> AsyncGenerator[str, None]:
        """Streaming Converse API call.  Yields SSE-formatted strings identical
        to those produced by ``invoke_model_stream`` so the frontend needs no changes."""
        import random

        kwargs = self._build_converse_kwargs(model_id, body)

        # Retry connection phase
        response = None
        client_ctx = None
        for attempt in range(max_retries):
            try:
                client_ctx = self.session.client(
                    "bedrock-runtime",
                    region_name=self.region,
                    config=self.config,
                )
                client = await client_ctx.__aenter__()
                response = await client.converse_stream(**kwargs)
                break
            except Exception as e:
                error_str = str(e)
                is_throttle = "ThrottlingException" in error_str or "429" in error_str or "Too Many Requests" in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Converse stream 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
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
            message_id = f"msg_{uuid.uuid4().hex[:24]}"
            current_block_index = -1
            started_message = False
            input_tokens = 0
            output_tokens = 0
            # Deferred stop_reason: metadata (with token counts) arrives AFTER
            # messageStop in the Converse stream, so we must wait for it before
            # emitting the message_delta / message_stop SSE events.
            pending_stop_reason = None

            async for event in response["stream"]:
                # -- messageStart --
                if "messageStart" in event:
                    started_message = True
                    role = event["messageStart"].get("role", "assistant")
                    msg = {
                        "id": message_id,
                        "type": "message",
                        "role": role,
                        "content": [],
                        "model": original_model,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    }
                    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': msg})}\n\n"

                # -- contentBlockStart --
                elif "contentBlockStart" in event:
                    cbs = event["contentBlockStart"]
                    current_block_index = cbs.get("contentBlockIndex", current_block_index + 1)
                    start_block = cbs.get("start", {})
                    if "toolUse" in start_block:
                        tu = start_block["toolUse"]
                        content_block = {
                            "type": "tool_use",
                            "id": tu.get("toolUseId", ""),
                            "name": tu.get("name", ""),
                            "input": {},
                        }
                    else:
                        content_block = {"type": "text", "text": ""}
                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': content_block})}\n\n"

                # -- contentBlockDelta --
                elif "contentBlockDelta" in event:
                    cbd = event["contentBlockDelta"]
                    idx = cbd.get("contentBlockIndex", current_block_index)
                    delta_block = cbd.get("delta", {})

                    if "text" in delta_block:
                        delta = {"type": "text_delta", "text": delta_block["text"]}
                    elif "reasoningContent" in delta_block:
                        rc = delta_block["reasoningContent"]
                        delta = {"type": "thinking_delta", "thinking": rc.get("text", "")}
                    elif "toolUse" in delta_block:
                        delta = {"type": "input_json_delta", "partial_json": delta_block["toolUse"].get("input", "")}
                    else:
                        continue

                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': idx, 'delta': delta})}\n\n"

                # -- contentBlockStop --
                elif "contentBlockStop" in event:
                    idx = event["contentBlockStop"].get("contentBlockIndex", current_block_index)
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': idx})}\n\n"

                # -- messageStop --
                elif "messageStop" in event:
                    # Save the stop reason but do NOT yield yet -- the metadata
                    # event (with actual output_tokens) arrives after this.
                    raw_stop = event["messageStop"].get("stopReason", "end_turn")
                    stop_map = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens", "stop_sequence": "stop_sequence"}
                    pending_stop_reason = stop_map.get(raw_stop, raw_stop)

                # -- metadata (usage) --
                elif "metadata" in event:
                    usage = event["metadata"].get("usage", {})
                    input_tokens = usage.get("inputTokens", 0)
                    output_tokens = usage.get("outputTokens", 0)

                    # If we have a pending stop, emit the deferred SSE events
                    # now that we have the real token counts.
                    if pending_stop_reason is not None:
                        delta_data = {
                            "type": "message_delta",
                            "delta": {"stop_reason": pending_stop_reason, "stop_sequence": None},
                            "usage": {"output_tokens": output_tokens},
                        }
                        yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"
                        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                        pending_stop_reason = None

            # Edge case: messageStop received but metadata never arrived --
            # emit the deferred events with whatever token count we have.
            if pending_stop_reason is not None:
                delta_data = {
                    "type": "message_delta",
                    "delta": {"stop_reason": pending_stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens},
                }
                yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

            # Ensure message_start was sent
            if not started_message:
                empty_msg = {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": original_model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': empty_msg})}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        except Exception as e:
            logger.error(f"Converse streaming error: {e}")
            error_data = format_error_response(e)
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        finally:
            if client_ctx:
                try:
                    await client_ctx.__aexit__(None, None, None)
                except Exception:
                    pass

    async def _converse_stream_text(
        self,
        model_id: str,
        body: Dict[str, Any],
        max_retries: int = 3,
    ) -> AsyncGenerator[dict, None]:
        """Converse streaming that yields simple dicts for agent team use.

        Same yield format as ``invoke_model_stream_text``.
        """
        import random

        kwargs = self._build_converse_kwargs(model_id, body)

        response = None
        client_ctx = None
        for attempt in range(max_retries):
            try:
                client_ctx = self.session.client(
                    "bedrock-runtime",
                    region_name=self.region,
                    config=self.config,
                )
                client = await client_ctx.__aenter__()
                response = await client.converse_stream(**kwargs)
                break
            except Exception as e:
                error_str = str(e)
                is_throttle = "ThrottlingException" in error_str or "429" in error_str or "Too Many Requests" in error_str
                if is_throttle and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 5)
                    logger.warning(f"Converse stream_text 429 throttled (attempt {attempt + 1}/{max_retries}), retrying in {backoff:.1f}s...")
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
            async for event in response["stream"]:
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        yield {"type": "delta", "text": delta["text"]}
                elif "metadata" in event:
                    usage = event["metadata"].get("usage", {})
                    if usage:
                        yield {
                            "type": "usage",
                            "input_tokens": usage.get("inputTokens", 0),
                            "output_tokens": usage.get("outputTokens", 0),
                        }
        except Exception as e:
            logger.error(f"Converse stream_text error: {e}")
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
