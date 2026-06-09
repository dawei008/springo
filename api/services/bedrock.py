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
from .error_handler import format_error_response as _eh_format_error, get_http_status, parse_error


_RETRYABLE_TOKENS = (
    'ThrottlingException', '429', 'Too Many Requests',
    'ServiceUnavailableException', '503', 'Service Unavailable',
    'InternalServerException', '500', 'Internal Server Error',
    'ModelTimeoutException', 'RequestTimeout', '408',
    'ModelStreamErrorException',
    'Connection reset', 'Connection aborted', 'Read timed out',
)


def _is_retryable_error(error_str: str) -> bool:
    return any(token in error_str for token in _RETRYABLE_TOKENS)

from .model_registry import (
    MODEL_REGISTRY,
    BEDROCK_MODEL_MAPPING,
    get_model_limits,
    get_bedrock_id,
    get_model_info,
    get_max_tools,
    model_supports_tools,
    model_needs_tool_flattening,
)

logger = logging.getLogger(__name__)


def format_error_response(error: Exception, lang: str = "zh") -> dict:
    """Format error into structured response — delegates to error_handler module"""
    return _eh_format_error(error, lang=lang)


# ---------------------------------------------------------------------------
# Tool priority for Converse models with limited tool capacity.
# Tools are selected in tier order until max_tools is reached.
# ---------------------------------------------------------------------------
# Tier 1: Core tools — always included
_TOOL_TIER1 = {
    # File operations
    "read_file", "read_files", "write_file", "edit", "list_directory",
    "create_directory", "delete_file", "move_file", "search_files",
    "get_file_info", "glob", "grep",
    # Execution & tasks
    "execute_command", "get_task_status", "list_background_tasks", "task",
    # Git
    "git",
    # User interaction & workflow
    "ask_user", "todo_read", "todo_write", "delegate_task",
    "summarize_context", "tool_search", "use_skill", "scheduler",
    # Planning & memory (always available)
    "enter_plan_mode", "exit_plan_mode",
    "memory_search", "memory_write", "memory_get",
    # ACP agents (delegate to external AI agents)
    "acp_prompt", "acp_list_agents", "acp_new_session",
}
# Tier 2: Web & knowledge
_TOOL_TIER2_PREFIXES = (
    "web-search__", "fetch__", "aws-knowledge__",
)
# Tier 3: GitHub, AWS tools
_TOOL_TIER3_PREFIXES = (
    "github__", "aws-pricing__", "aws-diagram__", "huggingface__",
)
# Everything else (builder-mcp, playwright, pencil, etc.) is tier 4.


def _prioritize_tools(tools: list, max_tools: int) -> list:
    """Select up to *max_tools* from *tools*, prioritising core tools."""
    if max_tools <= 0 or len(tools) <= max_tools:
        return tools

    tier1, tier2, tier3, tier4 = [], [], [], []
    for t in tools:
        name = t.get("name", "")
        if name in _TOOL_TIER1:
            tier1.append(t)
        elif any(name.startswith(p) for p in _TOOL_TIER2_PREFIXES):
            tier2.append(t)
        elif any(name.startswith(p) for p in _TOOL_TIER3_PREFIXES):
            tier3.append(t)
        else:
            tier4.append(t)

    selected: list = []
    for tier in (tier1, tier2, tier3, tier4):
        remaining = max_tools - len(selected)
        if remaining <= 0:
            break
        selected.extend(tier[:remaining])

    logger.info(
        f"Tool limit applied: {len(tools)} -> {len(selected)} "
        f"(max_tools={max_tools}, tiers={len(tier1)}/{len(tier2)}/{len(tier3)}/{len(tier4)})"
    )
    return selected


# Tool context budget: tools may occupy up to this fraction of the model's
# context window.  Matches Claude Code's approach — roughly 25%.
_TOOL_BUDGET_RATIO = 0.25

# Absolute floor: never evict if tools are below this (small model safety net)
_TOOL_BUDGET_FLOOR = 20_000


def _strip_internal_tool_markers(tools: list) -> list:
    """Strip internal markers (keys starting with '_') from tool definitions.

    These markers (e.g. _bedrock_tool_type) are used internally by Springo
    but must not be sent to the Bedrock API.
    """
    cleaned = []
    for tool in tools:
        if any(k.startswith("_") for k in tool):
            clean = {k: v for k, v in tool.items() if not k.startswith("_")}
            cleaned.append(clean)
        else:
            cleaned.append(tool)
    return cleaned


def _estimate_tools_tokens(tools: list) -> int:
    """Rough token estimate for a list of tool definitions (~4 chars/token)."""
    import json as _json
    return sum(len(_json.dumps(t)) for t in tools) // 4


def _strip_messages_cache_control(messages: list) -> None:
    """Remove any existing cache_control markers from message content blocks.

    We re-apply a single checkpoint per request; stale markers left over from
    earlier turns would push us past Bedrock's 4-checkpoint limit.
    """
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)


def _set_message_cache_checkpoint(msg: Dict[str, Any]) -> None:
    """Tag the last content block of `msg` with cache_control: ephemeral.

    Anthropic's API accepts cache_control only on *content blocks*, not on the
    message object itself. If the message content is a plain string, we
    normalize it to a single-element text block first.
    """
    content = msg.get("content")
    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ]
        return
    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = {"type": "ephemeral"}


def _get_tool_budget(model: str) -> int:
    """Calculate the tool token budget for a model.

    Uses the model's context window and allocates TOOL_BUDGET_RATIO of it for tools.

    budget = max(context_window * _TOOL_BUDGET_RATIO, _TOOL_BUDGET_FLOOR)
    """
    limits = get_model_limits(model)
    ctx = limits.get("max_context_tokens", 200000)
    return max(int(ctx * _TOOL_BUDGET_RATIO), _TOOL_BUDGET_FLOOR)


def _auto_unload_tools(tools: list, model: str = "") -> list:
    """Evict unused tools to save context tokens.

    Trigger conditions (ALL must be met):
      1. Past grace period (> TOOL_GRACE_TURNS user messages)
      2. Total tool tokens exceed the model's dynamic tool budget
         (effective_context_window * 25%, min 20K)

    When triggered, keeps:
      - Tier 1 (builtin core tools) — always
      - Any tool actually used in this session

    Everything else (MCP tools, external tools) gets evicted if unused.
    Evicted tools remain discoverable via tool_search and can be
    re-activated on demand (hot-loading already handles this).
    """
    from .session_state import get_user_turn, get_used_tools, TOOL_GRACE_TURNS

    current_turn = get_user_turn()
    if current_turn <= TOOL_GRACE_TURNS:
        return tools  # Grace period — include everything

    # Calculate dynamic budget based on model's effective context window
    budget = _get_tool_budget(model)
    total_tokens = _estimate_tools_tokens(tools)
    if total_tokens <= budget:
        return tools  # Within budget — no eviction needed

    used_tools = get_used_tools()
    kept = []
    evicted_names = []

    for t in tools:
        name = t.get("name", "")
        # Tier 1 (builtin core) — never evict
        if name in _TOOL_TIER1:
            kept.append(t)
            continue
        # Actually used this session — keep
        if name in used_tools:
            kept.append(t)
            continue
        # Evict everything else
        evicted_names.append(name)

    if evicted_names:
        kept_tokens = _estimate_tools_tokens(kept)
        logger.info(
            f"Auto-unload: evicted {len(evicted_names)} unused tools "
            f"({total_tokens:,} -> {kept_tokens:,} tokens, "
            f"budget={budget:,}, model={model}, turn {current_turn}). "
            f"Evicted: {evicted_names[:5]}{'...' if len(evicted_names) > 5 else ''}"
        )

    return kept


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

# Default system prompt
COMMON_SYSTEM_PROMPT = """You are a helpful AI assistant with access to various tools for file operations, code editing, searching, and command execution.

## Response Style (IMPORTANT)

Be direct, concise, and substantive. Go straight to the point.

- Lead with the answer or action, not the reasoning
- Skip filler words, preamble, and unnecessary transitions ("Sure!", "Great question!", "Let me help you with that")
- Do not restate what the user said — just do it
- If you can say it in one sentence, don't use three
- When summarizing or explaining, include only what is necessary — no padding, no generic platitudes
- Prefer concrete facts, numbers, and specifics over vague statements
- When the user asks for a summary, give substance: key takeaways, decisions, and actionable items — not high-level fluff
- Match the language of the user's message (if they write in Chinese, respond in Chinese; if English, respond in English)

## CRITICAL: Always Use Absolute Paths

**For ALL tool calls AND response text that mention file or directory paths, you MUST use absolute paths.**

This applies to:
1. Tool call parameters (file paths, directory paths)
2. Response text when referencing files (e.g., "I created `/Users/name/project/file.txt`")
3. Code suggestions that contain file paths

- Correct: `/Users/name/project/file.txt`
- Correct: `~/.springo/skills/pptx/script.py` (~ expands to home directory)
- Wrong: `file.txt` (relative path)
- Wrong: `./project/file.txt` (relative path)
- Wrong: `workspace/file.txt` (relative path)

The working directory will be provided below. Use it to construct absolute paths for both tool calls and text references.

{SPRINGO_MD_PLACEHOLDER}

## Important: Two Directory Scopes

You work with TWO separate directory trees. Do NOT confuse them:

1. **Project directory** (working_dir) — source code, config files, app logic
2. **`~/.springo/`** — Springo's runtime data: skills, sessions, config, scripts

When searching for **skills**, **sessions**, **config**, or **scripts**, ALWAYS use `~/.springo/` as the base path:
- Skills: `read_file ~/.springo/skills/<name>/SKILL.md` or `list_directory ~/.springo/skills/`
- Config: `read_file ~/.springo/config.json`
- For glob/grep, set `path` parameter to `~/.springo/` — do NOT search the project directory for these.

## Skill-First Principle (IMPORTANT)

For any non-trivial task, ALWAYS check if a matching skill exists before writing code yourself:
1. Review the available skills listed in the `use_skill` tool description
2. If a skill matches the task, call `use_skill` immediately — do NOT write Python/JS scripts to do what a skill already handles
3. Only fall back to manual coding if no skill covers the task

This applies to ALL complex tasks: document creation/editing, data processing, browser automation, presentations, spreadsheets, PDF operations, etc. Skills contain tested, optimized workflows — prefer them over ad-hoc scripts.

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
| Delegate to external AI agent | `acp_prompt` (Kiro, Gemini, OpenClaw, etc.) | SSH/manual CLI |
| Track complex tasks | `todo_write` | - |
| Ask user questions | `ask_user` | - |
| Plan before coding | `enter_plan_mode` | - |

## Parallel Tool Execution

You can call multiple tools in a single response. If you intend to call multiple tools and there are no dependencies between the calls, make all of the independent calls in the same response. Maximize use of parallel tool calls where possible to increase efficiency. However, if some tool calls depend on previous calls to inform dependent values, do NOT call these tools in parallel and instead call them sequentially. For instance, if one operation must complete before another starts (like reading a file before editing it), run these operations sequentially instead. Never use placeholders or guess missing parameters in tool calls.

Examples of parallel-safe calls:
- Multiple `write_file` calls writing different files
- Multiple `read_file` / `read_files` calls for different paths
- Multiple `grep` / `glob` searches in different directories
- Multiple `edit` calls on different files
- Running `execute_command` for independent operations

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
   - Use MCP tool: web-search__brave_web_search
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
| 明天下午3点 | once | (calculate from current time, e.g. YYYY-MM-DDT15:00:00) |

IMPORTANT: For "once" type, always calculate the correct date from the current time injected in the user message. Never use hardcoded dates.

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

## Proactive Task Completion (IMPORTANT)

You are an autonomous problem-solver. When given a task, drive it to completion without waiting for the user to point out next steps.

### Core Principles

1. **Complete the loop**: Every task has a natural completion cycle. Follow it:
   - Code change: read -> understand -> edit -> verify (run/test) -> fix if needed
   - Bug fix: reproduce -> diagnose root cause -> fix -> verify fix -> check for regressions
   - Research: search -> read -> synthesize -> present findings
   - Don't stop at "I've made the change" — verify it works.

2. **Self-diagnose errors**: When a command fails or code breaks:
   - Read the FULL error message carefully
   - Identify the root cause (don't guess — trace it)
   - Fix the underlying issue, not the symptom
   - Never retry the exact same command hoping for a different result
   - If blocked after 2 attempts, try a different approach

3. **Track what you've tried**: Maintain awareness across iterations:
   - Remember which approaches failed and why
   - Don't repeat failed strategies
   - Build on partial progress rather than starting over
   - If context was compacted, check `todo_write` items for prior state

4. **Continue until done**: Don't stop prematurely:
   - If a build has errors, fix them — don't just report them
   - If a test fails, debug it — don't just show the output
   - If one file needs changes, check if related files also need updates
   - Only stop when the user's goal is fully achieved, or you need user input to proceed

5. **Ask only when truly blocked**: Prefer action over questions:
   - If you can infer the answer from context, code, or conventions — just do it
   - If multiple approaches are valid and low-risk, pick the best one and proceed
   - Only use `ask_user` when the choice materially affects the outcome and you can't determine the user's preference

### Anti-Patterns to Avoid

- Reporting an error without attempting to fix it
- Saying "I've updated the file" without verifying the change works
- Stopping after one failed attempt without trying alternatives
- Asking "should I continue?" when the answer is obviously yes
- Losing track of the overall goal after multiple tool calls
- Fragmenting a simple task into multiple back-and-forth exchanges

## Artifacts (single-tag API)

Substantial, self-contained content that the user wants to view, reference, or keep — documents, interactive apps, reports, designs — lives in Springo's Canvas panel. There is **one writer tag** (`<springo-artifact op="...">`) and **one reader tool** (`canvas`, read-only). That's the whole API.

### `<springo-artifact op="create">` — make a new artifact

```
<springo-artifact op="create" type="app" title="Short descriptive title" icon="dashboard">
  <springo-file path="App.jsx" type="text/jsx">
    export default function App() { return <div>Hello</div>; }
  </springo-file>
</springo-artifact>
```

**`type` (required):** `app` (interactive UI) · `component` (single reusable piece) · `document` (long-form text/report/SVG) · `template` (starter for later projects).

**`icon` (optional, no emoji):** `app`, `component`, `document`, `template`, `dashboard`, `chart`, `todo`, `web`, `form`, `counter`, `mobile`, `calendar`, `chat`, `image`, `code`, `box`. Falls back to the `type` value when omitted.

### `<springo-artifact op="patch">` — modify an existing artifact

When the user's message includes an `<artifact-context>` block, an artifact is open. Changes to it **must** be patches:

```
<springo-artifact op="patch" id="art-msg-123-0">
  <springo-file path="App.jsx" action="replace" type="text/jsx">
    /* full new contents of App.jsx */
  </springo-file>
  <springo-file path="NewHelper.jsx" action="create" type="text/jsx">
    /* newly added file */
  </springo-file>
  <springo-file path="OldFile.jsx" action="delete" />
</springo-artifact>
```

- `id` comes verbatim from `<artifact-context>`. **Never invent an id.**
- Only include files that **change**. Unchanged files: don't mention them.
- Emit a fresh `op="create"` only when the user asks for a genuinely *different* thing ("now make a separate calculator"). When in doubt, patch.

### `<springo-artifact op="action">` — drive runtime state

For ephemeral state the artifact can handle via `postMessage` (navigate, reset counter, toggle theme), skip rewriting code:

```
<springo-artifact op="action" id="art-msg-123-0">
  { "type": "navigate", "route": "/settings" }
</springo-artifact>
```

The artifact's own code must listen: `window.springo?.onChatAction((payload) => { ... })`. If the handler doesn't exist yet, emit `op="patch"` to add it, then a follow-up `op="action"` (or fold the state change into the patch and skip the action).

### When to create / not create an artifact

**Create** when the user asks for a standalone deliverable: a report, a dashboard, a full mini-app, a finished document, a long SVG diagram.

**Don't create** for conversational answers, short snippets inside explanations, summaries/lists that live in chat, tool results, or "explaining something" responses. The test: "Is this a thing they'll save or come back to?"

### Observing live artifact state

The `<artifact-context>` block carries a `<runtime-state>` section populated from the artifact's own `window.springo.setState(...)` calls. Use it to answer "what's the current count?" / "did they enter email?" without asking.

Instrument new artifacts like this:

```jsx
const [count, setCount] = React.useState(0);
React.useEffect(() => { window.springo?.setState({ count }); }, [count]);
```

### Pinned-element edits

If the user's message starts with `[Pinned element: <componentName> (<tagName>) at "<cssPath>"]`, they clicked a specific element. Scope the patch to that element's file and touch nothing else.

### Design quality

For any visible UI (`type=app`/`component`/`template`), call `use_skill('canvas')` first — it carries the responsive-layout rules, the AI-slop avoid-list, and the Springo design tokens already injected into the iframe.

### canvas tool — read only

For inspection only. Writes always go through `<springo-artifact op="...">`.

- `canvas(action="list")` — all artifacts
- `canvas(action="read", artifact_id, path?)` — source files
- `canvas(action="state", artifact_id)` — current runtime state
- `canvas(action="query", artifact_id, selector)` — CSS selector against live iframe DOM

**Never** write a Python script to `read_file` / mutate / `write_file` a Canvas artifact's source. Artifacts live under `~/.springo/artifacts/<id>/` on disk, but you edit them through `<springo-artifact op="patch">` so the renderer sees the change immediately and versions are snapshot. Python round-trips bypass both.

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

    def refresh_session(self):
        """Recreate the aioboto3 session to pick up refreshed credentials.

        Called by the retry layer when an ExpiredTokenException is detected.
        """
        logger.info("BedrockService: refreshing aioboto3 session for credential renewal")
        self.session = aioboto3.Session(**self._session_kwargs)

    def get_bedrock_model_id(self, model: str) -> str:
        """获取 Bedrock 模型 ID"""
        return get_bedrock_id(model)

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

        # Use model's max output as default — 16384 is too small for models like
        # Opus that write long analyses before tool calls, causing max_tokens truncation.
        model_max_output = model_info.get("max_output", 16384) if model_info else 16384
        default_max = 64000 if request.get("design_mode") else model_max_output
        bedrock_body = {
            "max_tokens": max(request.get("max_tokens", default_max), default_max),
            "messages": copy.deepcopy(request.get("messages", [])),
            "_original_model": model,  # used by _build_converse_kwargs
        }

        # Only add anthropic_version for Anthropic-format models
        if api_format == "anthropic":
            bedrock_body["anthropic_version"] = "bedrock-2023-05-31"
            # Beta features
            bedrock_body["anthropic_beta"] = ["fine-grained-tool-streaming-2025-05-14"]

            # Adaptive thinking for Opus 4.7+ (only supported mode; Bedrock accepts
            # the same shape as Anthropic API).  Default: xhigh effort, summarized display.
            if model in ("claude-opus-4-7", "claude-opus-4-8"):
                if request.get("thinking_enabled"):
                    effort = request.get("thinking_effort") or "xhigh"
                    if effort not in ("low", "medium", "high", "xhigh", "max"):
                        effort = "xhigh"
                    bedrock_body["thinking"] = {"type": "adaptive", "display": "summarized"}
                    bedrock_body["output_config"] = {"effort": effort}
                    logger.info(f"[Thinking] {model} adaptive thinking enabled, effort={effort}")
                else:
                    logger.info(f"[Thinking] {model} thinking DISABLED (thinking_enabled={request.get('thinking_enabled')!r})")

        # Copy optional parameters
        # Opus 4.7+ does not accept temperature/top_p/top_k
        _no_sampling = model in ("claude-opus-4-7", "claude-opus-4-8")
        for key in ["temperature", "top_p", "top_k", "stop_sequences", "tool_choice"]:
            if _no_sampling and key in ("temperature", "top_p", "top_k"):
                continue
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
        # working_dir + design_mode used to be appended to the static system
        # prompt. They vary per session / per turn and were busting the cache.
        # We collect them here and inject into the dynamic block below.
        per_turn_system_parts: list[str] = []
        if working_dir:
            import os
            springo_config_dir = os.path.expanduser("~/.springo")
            per_turn_system_parts.append(
                f"\n\n## Working Directory & Springo Config\n"
                f"- **Working Directory**: `{working_dir}` — project code lives here\n"
                f"- **Springo Config**: `{springo_config_dir}/` — settings, skills, sessions, scripts\n"
                f"  - Skills: `{springo_config_dir}/skills/` (each subfolder has SKILL.md)\n"
                f"  - Config: `{springo_config_dir}/config.json`\n"
                f"- For `glob`/`grep`: use `path` parameter to search the right directory\n"
                f"  - Project files: `path: \"{working_dir}\"`\n"
                f"  - Skills/config: `path: \"{springo_config_dir}\"`\n"
            )
        design_mode = request.get("design_mode", False)
        if design_mode:
            per_turn_system_parts.append(
                "\n\n## Design Mode Active\n\n"
                "The user is in Springo's design flow. Call the `artifacts-design` skill "
                "via `use_skill` to load the visual guidelines AND the Springo design tokens "
                "(CSS variables already injected into the Canvas iframe). Then emit a "
                "`<springo-artifact op=\"create\">` or `<springo-artifact op=\"patch\" id=\"...\">` directly in your response text — "
                "do not use code tools to write design files.\n"
            )

        # Inject long-term memory (MEMORY.md + recent daily logs) into the static block
        # so it's cached alongside the base system prompt. Per-turn dynamic memory
        # snippets (which change with the user's latest message) go into the separate
        # dynamic block below.
        relevant_snippets: str = ""
        try:
            from .memory_files import get_memory_file_manager, find_relevant_memory_snippets
            mem_mgr = get_memory_file_manager()
            if mem_mgr:
                memory_context = mem_mgr.get_context_for_prompt()
                if memory_context:
                    system_prompt += "\n" + memory_context

                # Per-turn dynamic memory retrieval: find snippets relevant to current message
                messages_list = bedrock_body.get("messages", [])
                if messages_list:
                    last_user_text = ""
                    for msg in reversed(messages_list):
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            if isinstance(content, str):
                                last_user_text = content
                            elif isinstance(content, list):
                                last_user_text = " ".join(
                                    b.get("text", "") for b in content
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                            break
                    if last_user_text:
                        relevant = find_relevant_memory_snippets(
                            query=last_user_text,
                            manager=mem_mgr,
                            max_snippets=3,
                            max_chars_per_snippet=400,
                            days=mem_mgr.retention_days,
                        )
                        if relevant:
                            relevant_snippets = (
                                "\n\n## Relevant Past Context\n"
                                "The following memory snippets were matched to the current message. "
                                "Use them if relevant, but verify before acting on older entries.\n\n"
                                + relevant
                            )
        except Exception as e:
            logger.debug(f"Memory injection skipped: {e}")

        # Build the dynamic system block (per-turn parts + artifact context +
        # matched memory snippets). These change per-request but are independent
        # of the stable base block — splitting them lets the base block stay
        # cached while only this small tail gets rebuilt. Also used by the
        # non-Anthropic (converse) path which doesn't support multi-block
        # system prompts — for those, we concatenate at the end.
        artifact_context = request.get("design_context")
        dynamic_system_parts: list[str] = list(per_turn_system_parts)
        if artifact_context:
            truncated = artifact_context[:50000]
            dynamic_system_parts.append(
                "\n\n## Canvas State (live)\n"
                "An artifact is currently open in Springo's Canvas panel. Its files and "
                "(optional) runtime state are below. When the user's request targets this "
                "artifact, emit `<springo-artifact op=\"patch\" id=\"...\">` — use the id from the "
                "context block. Do NOT rebuild it with `op=\"create\"`.\n\n"
                f"{truncated}\n"
            )
        if relevant_snippets:
            dynamic_system_parts.append(relevant_snippets)
        dynamic_system = "".join(dynamic_system_parts)

        if api_format == "anthropic":
            # Block #1: stable — instructions + SPRINGO.md + MEMORY.md + design-mode note.
            # This is the hot cache: changes rarely (new session, new skill, distill).
            system_blocks: list[Dict[str, Any]] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            # Block #2 (optional): dynamic — Canvas artifact context + per-turn memory
            # snippets. Separate checkpoint so that opening/closing artifacts and swapping
            # between sessions with different artifacts does NOT bust block #1's cache.
            if dynamic_system:
                system_blocks.append(
                    {
                        "type": "text",
                        "text": dynamic_system,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
            bedrock_body["system"] = system_blocks
        else:
            # Converse API: no multi-block support, collapse to a single string.
            bedrock_body["system"] = system_prompt + dynamic_system
        
        # Handle tools (skip for models that don't support tool use)
        if include_tools and model_supports_tools(model):
            raw_tools = request.get("tools") or tools or []
            if raw_tools:
                # Design mode: all tools remain available — system prompt guides
                # the model to produce artifacts rather than write files directly
                # Auto-unload: evict unused tools after grace period
                raw_tools = _auto_unload_tools(raw_tools, model=model)
                # Apply tool limit for Converse models with max_tools set
                max_t = get_max_tools(model)
                if max_t > 0 and len(raw_tools) > max_t:
                    raw_tools = _prioritize_tools(raw_tools, max_t)

                # Strip internal markers from tools (e.g. _bedrock_tool_type)
                # Computer tool is sent as a regular tool — Bedrock doesn't
                # support the computer_20250124 beta type.  Screenshots are
                # returned as image blocks in tool_result instead.
                raw_tools = _strip_internal_tool_markers(raw_tools)

                if api_format == "anthropic" and raw_tools:
                    # Strip stale cache_control from all tools first — tool dicts
                    # are reused across auto-loop iterations, so previous calls may
                    # have left cache_control on other tools, exceeding Bedrock's
                    # 4-block limit.
                    for t in raw_tools:
                        t.pop("cache_control", None)
                    raw_tools[-1]["cache_control"] = {"type": "ephemeral"}
                bedrock_body["tools"] = raw_tools
        
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

        # Mark the end of the stable conversation history as a cache checkpoint.
        # When a new user message is appended on the next turn, everything up to
        # this point stays cached and only the new tail is recomputed. We put the
        # checkpoint on the last block of the second-to-last message (typically an
        # assistant turn) — the last message is almost always the fresh user query
        # (possibly prepended with the time_prefix above), which is never cacheable.
        if api_format == "anthropic" and bedrock_body.get("messages") and len(bedrock_body["messages"]) >= 2:
            try:
                _strip_messages_cache_control(bedrock_body["messages"])
                _set_message_cache_checkpoint(bedrock_body["messages"][-2])
            except Exception as e:
                # Non-fatal: cache is an optimization, not a correctness requirement.
                logger.debug(f"Failed to apply messages cache checkpoint: {e}")

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

        # Remove internal metadata before sending to Anthropic InvokeModel API
        original_model = body.pop("_original_model", None) or ""
        body.pop("extended_context", None)

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
                if _is_retryable_error(error_str) and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 8)
                    logger.warning(f"Bedrock invoke retryable error (attempt {attempt + 1}/{max_retries}): {error_str[:120]}. Retrying in {backoff:.1f}s...")
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

        # Remove internal metadata before sending to Anthropic InvokeModel API
        body.pop("_original_model", None)
        body.pop("extended_context", None)

        body_json = json.dumps(body)
        message_id = f"msg_{uuid.uuid4().hex[:24]}"

        # Retry wrapper: handles both connection errors AND empty stream responses.
        # Bedrock occasionally returns 0 chunks (empty stream) especially for large
        # contexts with many tools.  We retry with exponential backoff, refreshing
        # the aioboto3 session after repeated failures.
        for attempt in range(max_retries):
            client_ctx = None
            try:
                client_ctx = self.session.client(
                    'bedrock-runtime',
                    region_name=self.region,
                    config=self.config
                )
                client = await client_ctx.__aenter__()
                response = await client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=body_json,
                    contentType="application/json",
                    accept="application/json"
                )

                current_block_index = -1
                started_message = False
                got_stop_reason = False
                chunk_timeout = settings.bedrock_stream_chunk_timeout
                _chunk_count = 0

                body_iter = response['body'].__aiter__()
                while True:
                    try:
                        event = await asyncio.wait_for(body_iter.__anext__(), timeout=chunk_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.error(f"Bedrock stream stalled: no chunk received in {chunk_timeout}s (got {_chunk_count} chunks before stall)")
                        raise Exception(f"Stream stalled: no data received in {chunk_timeout} seconds")
                    _chunk_count += 1
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
                        got_stop_reason = bool(chunk.get('delta', {}).get('stop_reason'))
                        delta_data = {
                            'type': 'message_delta',
                            'delta': chunk.get('delta', {}),
                            'usage': chunk.get('usage', {})
                        }
                        yield f"event: message_delta\ndata: {json.dumps(delta_data)}\n\n"

                    elif chunk_type == "message_stop":
                        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

                # Stream finished — close client cleanly BEFORE checking if empty
                try:
                    await client_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
                client_ctx = None

                if started_message and got_stop_reason:
                    return  # Success — complete response received

                _msg_count = len(body.get("messages", []))
                _sys = body.get("system", "")
                if isinstance(_sys, list):
                    _sys_len = sum(len(b.get("text", "")) for b in _sys if isinstance(b, dict))
                else:
                    _sys_len = len(_sys)
                _max_tok = body.get("max_tokens", "?")
                _tools_count = len(body.get("tools", []))

                if started_message and not got_stop_reason:
                    # Partial stream: message_start arrived but stream ended
                    # before message_delta with stop_reason.  Can't retry at
                    # this level because SSE events were already yielded.
                    # Emit a synthetic message_delta so the auto-loop sees
                    # empty_response and can retry at its level.
                    logger.warning(
                        f"Bedrock partial stream ({_chunk_count} chunks, no stop_reason) for {model_id}: "
                        f"msgs={_msg_count}, max_tokens={_max_tok}, tools={_tools_count}"
                    )
                    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'empty_response'}, 'usage': {'output_tokens': 0}})}\n\n"
                    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                    return

                # Zero-chunk empty stream — safe to retry (nothing yielded yet)
                logger.warning(
                    f"Bedrock empty stream (0 chunks) for {model_id}, "
                    f"attempt {attempt + 1}/{max_retries}: "
                    f"msgs={_msg_count}, system_len={_sys_len}, max_tokens={_max_tok}, tools={_tools_count}"
                )
                if attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random() * 2, 10)
                    logger.info(f"Retrying empty stream in {backoff:.1f}s (attempt {attempt + 2}/{max_retries})")
                    if attempt >= 1:
                        self.refresh_session()
                        logger.info("Refreshed aioboto3 session after repeated empty stream")
                    await asyncio.sleep(backoff)
                    continue

                # All retries exhausted — emit synthetic empty_response
                logger.error(f"Bedrock empty stream persists after {max_retries} attempts for {model_id}")
                empty_msg = {
                    'id': message_id, 'type': 'message', 'role': 'assistant',
                    'content': [], 'model': original_model,
                    'stop_reason': 'empty_response', 'stop_sequence': None,
                    'usage': {'input_tokens': 0, 'output_tokens': 0}
                }
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': empty_msg})}\n\n"
                yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'empty_response'}, 'usage': {'output_tokens': 0}})}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                return

            except Exception as e:
                error_str = str(e)
                if _is_retryable_error(error_str) and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 8)
                    logger.warning(f"Bedrock stream retryable error (attempt {attempt + 1}/{max_retries}): {error_str[:120]}. Retrying in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"Bedrock streaming error: {e}", exc_info=True)
                error_data = format_error_response(e)
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                return
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

        # Remove internal metadata before sending to Anthropic InvokeModel API
        original_model = body.pop("_original_model", None) or ""
        body.pop("extended_context", None)

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
                if _is_retryable_error(error_str) and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 8)
                    logger.warning(f"Bedrock stream_text retryable error (attempt {attempt + 1}/{max_retries}): {error_str[:120]}. Retrying in {backoff:.1f}s...")
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
            chunk_timeout = settings.bedrock_stream_chunk_timeout
            body_iter = response['body'].__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(body_iter.__anext__(), timeout=chunk_timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.error(f"Bedrock stream_text stalled: no chunk in {chunk_timeout}s")
                    raise Exception(f"Stream stalled: no data received in {chunk_timeout} seconds")
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
    def _flatten_tool_content_blocks(messages: list) -> list:
        """Strip toolUse/toolResult blocks from message history.

        Some models (e.g. GLM 4.7) support tool calls via the Converse API
        but their Bedrock integration cannot deserialize toolUse/toolResult
        content blocks when they appear in *message history*.

        Previous approaches converted these blocks to descriptive text, but
        GLM 4.7 would mimic/echo ANY text that resembles tool information,
        causing it to output the flattened history instead of making real
        tool calls.

        Current approach:
        - Assistant messages: DROP toolUse blocks entirely (keep only text).
        - User messages: Replace toolResult blocks with just the result
          content as plain text — no tool names, IDs, or parameters.
        """
        out = []
        for msg in messages:
            new_blocks = []
            for block in msg.get("content", []):
                if "toolUse" in block:
                    # Drop tool calls from assistant history entirely
                    pass
                elif "toolResult" in block:
                    # Keep only the result content as plain text
                    tr = block["toolResult"]
                    parts = []
                    for c in tr.get("content", []):
                        parts.append(c.get("text", json.dumps(c, ensure_ascii=False)))
                    result_text = "\n".join(parts)
                    if len(result_text) > 4000:
                        result_text = result_text[:4000] + "\n...(truncated)"
                    if result_text.strip():
                        new_blocks.append({"text": result_text})
                else:
                    new_blocks.append(block)
            if not new_blocks:
                new_blocks = [{"text": " "}]
            out.append({"role": msg["role"], "content": new_blocks})
        return out

    @staticmethod
    def _extract_text_tool_calls(
        text: str, tool_names: set[str] | None = None,
    ) -> list[dict]:
        """Parse function-call-like text and return synthetic tool_use blocks.

        GLM 4.7 on Bedrock sometimes returns ``stopReason: tool_use`` but
        embeds the tool invocation as plain text instead of a proper
        ``toolUse`` content block.  Patterns handled:

        1. ``brave_web_search(query="NVIDIA H200", freshness="pw")``
        2. ``read_file({"path": "/some/file"})``  (JSON arg)
        3. Echoed flattened history: ``[Tool call: name(...)]``

        *tool_names*, if provided, limits matches to known tool names (both
        exact and suffix matches are tried so that ``brave_web_search``
        resolves to ``web-search__brave_web_search``).
        """
        import re

        calls: list[dict] = []

        # Find all function-call patterns.  We use a two-pass approach:
        # first locate `name(` then find the matching `)` handling braces.
        for m in re.finditer(r'([\w][\w\-\.]*)\(', text):
            raw_name = m.group(1)
            start = m.end()  # position right after '('

            # Resolve to a known tool name
            resolved_name = raw_name
            if tool_names:
                if raw_name in tool_names:
                    resolved_name = raw_name
                else:
                    suffix_matches = [
                        tn for tn in tool_names
                        if tn.endswith(raw_name) or tn.endswith(f"__{raw_name}")
                    ]
                    if suffix_matches:
                        resolved_name = suffix_matches[0]
                    else:
                        continue

            # Find the matching closing paren, accounting for nested braces
            depth = 1
            pos = start
            while pos < len(text) and depth > 0:
                ch = text[pos]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == '"':
                    # Skip string contents
                    pos += 1
                    while pos < len(text) and text[pos] != '"':
                        if text[pos] == '\\':
                            pos += 1  # skip escaped char
                        pos += 1
                pos += 1
            if depth != 0:
                continue
            params_str = text[start:pos - 1].strip()

            # Try to parse as JSON first (handles {"key": "value"} format)
            params: dict = {}
            if params_str.startswith('{'):
                try:
                    params = json.loads(params_str)
                except (json.JSONDecodeError, ValueError):
                    pass
            if not params:
                # Fall back to key=value parsing
                for kv in re.finditer(
                    r'(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|(\S+?)(?:\s*[,)]|$))',
                    params_str,
                ):
                    key = kv.group(1)
                    val = kv.group(2) if kv.group(2) is not None else (
                        kv.group(3) if kv.group(3) is not None else kv.group(4)
                    )
                    if val is not None:
                        params[key] = val

            calls.append({
                "type": "tool_use",
                "id": f"tooluse_{uuid.uuid4().hex[:24]}",
                "name": resolved_name,
                "input": params,
            })

        return calls

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
        original_model = body.pop("_original_model", None)
        system_prompt = body.get("system", "")
        system_block = [{"text": system_prompt}] if system_prompt else []

        messages = self._to_converse_messages(body.get("messages", []))

        # Flatten toolUse/toolResult blocks for models whose Bedrock
        # integration cannot deserialize them in message history.
        if original_model and model_needs_tool_flattening(original_model):
            messages = self._flatten_tool_content_blocks(messages)

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

        # Enable thinking mode for models that support it (e.g. Kimi K2.5)
        # by passing reasoning_effort via additionalModelRequestFields.
        model_info = get_model_info(original_model or model_id)
        if model_info and model_info.get("supports_thinking"):
            provider = model_info.get("provider", "")
            if provider == "moonshot":
                kwargs["additionalModelRequestFields"] = {
                    "reasoning_effort": "high"
                }

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

        # _ghost_tool_retries: extra retries when the model returns
        # stopReason=tool_use but no toolUse block (intermittent Bedrock bug
        # seen with GLM 4.7).
        _GHOST_TOOL_MAX_RETRIES = 2
        ghost_tool_attempt = 0

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

                # GLM 4.7 workaround: stopReason=tool_use but no toolUse
                # block — the tool call may be embedded as plain text, or
                # missing entirely (intermittent Bedrock bug).
                has_tool_block = any(b.get("type") == "tool_use" for b in content_blocks)
                if stop_reason == "tool_use" and not has_tool_block:
                    # Try to recover from text first
                    tool_names = {
                        t.get("toolSpec", {}).get("name", "")
                        for t in kwargs.get("toolConfig", {}).get("tools", [])
                    }
                    full_text = " ".join(
                        b["text"] for b in content_blocks if b.get("type") == "text"
                    )
                    parsed = self._extract_text_tool_calls(full_text, tool_names or None)
                    if parsed:
                        content_blocks.extend(parsed)
                        logger.info(
                            f"Recovered {len(parsed)} tool call(s) from text for model {model_id}"
                        )
                    elif ghost_tool_attempt < _GHOST_TOOL_MAX_RETRIES:
                        # Retry with toolChoice forced to "any" — the model
                        # intended a tool call but Bedrock dropped the block.
                        # Forcing toolChoice often makes the backend produce
                        # a proper toolUse block.
                        ghost_tool_attempt += 1
                        if "toolConfig" in kwargs:
                            kwargs["toolConfig"]["toolChoice"] = {"any": {}}
                        logger.warning(
                            f"Ghost tool_use (attempt {ghost_tool_attempt}/{_GHOST_TOOL_MAX_RETRIES}): "
                            f"retrying {model_id} with toolChoice=any"
                        )
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        # Exhausted retries — downgrade to end_turn so the
                        # caller doesn't enter an infinite tool loop.
                        stop_reason = "end_turn"
                        logger.warning(
                            f"stopReason=tool_use but no toolUse block after "
                            f"{_GHOST_TOOL_MAX_RETRIES} retries for {model_id}"
                        )

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

    @staticmethod
    async def _iter_with_heartbeat(async_iter, interval: float = 15.0):
        """Wrap an async iterator to yield heartbeat sentinels during long waits.

        Yields tuples of ``("event", item)`` for real events and
        ``("heartbeat", None)`` when *interval* seconds elapse without a
        new event.  This prevents the frontend SSE connection from timing
        out while waiting for slow Bedrock models (e.g. large Converse
        models with long time-to-first-token).

        If no real event arrives within ``bedrock_stream_chunk_timeout``
        seconds, the iterator raises to prevent indefinite hangs.
        """
        max_wait = settings.bedrock_stream_chunk_timeout
        it = async_iter.__aiter__()
        pending = asyncio.ensure_future(it.__anext__())
        try:
            while True:
                elapsed = 0.0
                while True:
                    done, _ = await asyncio.wait({pending}, timeout=interval)
                    if done:
                        try:
                            yield ("event", pending.result())
                        except StopAsyncIteration:
                            return
                        pending = asyncio.ensure_future(it.__anext__())
                        break
                    else:
                        elapsed += interval
                        if elapsed >= max_wait:
                            logger.error(f"Converse stream stalled: no event in {max_wait}s")
                            raise Exception(f"Stream stalled: no data received in {max_wait} seconds")
                        yield ("heartbeat", None)
        finally:
            if not pending.done():
                pending.cancel()
                try:
                    await pending
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass

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
        from ..utils.streaming import SSEEventBuilder

        kwargs = self._build_converse_kwargs(model_id, body)

        heartbeat_interval = settings.sse_heartbeat_interval  # default 10s

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
                # Wrap the initial API call with heartbeats – the
                # converse_stream() call itself can block for a very long
                # time on cold-start / large-model scenarios and must not
                # cause the frontend SSE connection to time out.
                api_call = asyncio.ensure_future(
                    client.converse_stream(**kwargs)
                )
                try:
                    while True:
                        done, _ = await asyncio.wait(
                            {api_call}, timeout=heartbeat_interval
                        )
                        if done:
                            break
                        yield SSEEventBuilder.heartbeat(0, "model_connecting")
                    response = api_call.result()
                except BaseException:
                    if not api_call.done():
                        api_call.cancel()
                        try:
                            await api_call
                        except (asyncio.CancelledError, Exception):
                            pass
                    raise
                break
            except Exception as e:
                error_str = str(e)
                if _is_retryable_error(error_str) and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 8)
                    logger.warning(f"Converse stream retryable error (attempt {attempt + 1}/{max_retries}): {error_str[:120]}. Retrying in {backoff:.1f}s...")
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
            # GLM 4.7 workaround: track text and toolUse presence
            _stream_text_parts: list[str] = []
            _stream_has_tool_use = False

            async for item_type, event in self._iter_with_heartbeat(
                response["stream"], interval=heartbeat_interval
            ):
                if item_type == "heartbeat":
                    yield SSEEventBuilder.heartbeat(0, "model_thinking")
                    continue
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
                        _stream_has_tool_use = True
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
                        _stream_text_parts.append(delta_block["text"])
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
                        # GLM 4.7 workaround: inject synthetic tool_use blocks
                        if pending_stop_reason == "tool_use" and not _stream_has_tool_use:
                            tool_names = {
                                t.get("toolSpec", {}).get("name", "")
                                for t in kwargs.get("toolConfig", {}).get("tools", [])
                            }
                            full_text = "".join(_stream_text_parts)
                            parsed = self._extract_text_tool_calls(full_text, tool_names or None)
                            if not parsed:
                                # Text parse failed — retry via non-streaming
                                # call with toolChoice=any to force a tool call.
                                retry_kwargs = dict(kwargs)
                                if "toolConfig" in retry_kwargs:
                                    retry_kwargs["toolConfig"] = dict(retry_kwargs["toolConfig"])
                                    retry_kwargs["toolConfig"]["toolChoice"] = {"any": {}}
                                for _ghost_try in range(2):
                                    logger.info(
                                        f"Stream ghost tool_use retry {_ghost_try + 1}/2 for {model_id} (toolChoice=any)"
                                    )
                                    try:
                                        async with self.session.client(
                                            "bedrock-runtime",
                                            region_name=self.region,
                                            config=self.config,
                                        ) as retry_client:
                                            retry_resp = await retry_client.converse(**retry_kwargs)
                                        retry_content = retry_resp.get("output", {}).get("message", {}).get("content", [])
                                        for rb in retry_content:
                                            if "toolUse" in rb:
                                                tu = rb["toolUse"]
                                                parsed.append({
                                                    "type": "tool_use",
                                                    "id": tu.get("toolUseId", f"tooluse_{uuid.uuid4().hex[:24]}"),
                                                    "name": tu.get("name", ""),
                                                    "input": tu.get("input", {}),
                                                })
                                        if parsed:
                                            break
                                    except Exception as retry_err:
                                        logger.warning(f"Stream ghost retry failed: {retry_err}")
                                    await asyncio.sleep(0.5)

                            if parsed:
                                logger.info(
                                    f"Stream: recovered {len(parsed)} tool call(s) for {model_id}"
                                )
                                for tc in parsed:
                                    current_block_index += 1
                                    cb = {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": {}}
                                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': cb})}\n\n"
                                    input_json = json.dumps(tc.get("input", {}))
                                    delta = {"type": "input_json_delta", "partial_json": input_json}
                                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': delta})}\n\n"
                                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                            else:
                                pending_stop_reason = "end_turn"
                                logger.warning(
                                    f"Stream: ghost tool_use unrecoverable after retries for {model_id}"
                                )

                        # Empty-response-after-tool-results retry: some models
                        # (e.g. Kimi K2.5) consume output tokens but return
                        # empty text deltas after receiving tool results.
                        # Retry once with a nudge in the system prompt.
                        if pending_stop_reason == "end_turn" and output_tokens > 0:
                            full_text = "".join(_stream_text_parts).strip()
                            if not full_text and not _stream_has_tool_use:
                                msgs = kwargs.get("messages", [])
                                last_msg = msgs[-1] if msgs else {}
                                has_tool_results = (
                                    last_msg.get("role") == "user"
                                    and isinstance(last_msg.get("content"), list)
                                    and any(
                                        isinstance(b, dict) and "toolResult" in b
                                        for b in last_msg["content"]
                                    )
                                )
                                if has_tool_results:
                                    logger.warning(
                                        f"Empty response ({output_tokens} output tokens) after tool "
                                        f"results for {model_id}, retrying with nudge..."
                                    )
                                    try:
                                        retry_kwargs = dict(kwargs)
                                        sys_parts = list(retry_kwargs.get("system", []))
                                        sys_parts.append({
                                            "text": (
                                                "\n\nIMPORTANT: You MUST process the tool results "
                                                "above and provide a complete, visible text response "
                                                "to the user. Do not respond with empty content."
                                            )
                                        })
                                        retry_kwargs["system"] = sys_parts
                                        async with self.session.client(
                                            "bedrock-runtime",
                                            region_name=self.region,
                                            config=self.config,
                                        ) as retry_client:
                                            retry_resp = await retry_client.converse(**retry_kwargs)
                                        retry_content = (
                                            retry_resp.get("output", {})
                                            .get("message", {})
                                            .get("content", [])
                                        )
                                        retry_texts = [
                                            rb["text"]
                                            for rb in retry_content
                                            if isinstance(rb, dict)
                                            and "text" in rb
                                            and rb["text"].strip()
                                        ]
                                        if retry_texts:
                                            combined = "\n".join(retry_texts)
                                            logger.info(
                                                f"Empty-response retry recovered {len(combined)} "
                                                f"chars for {model_id}"
                                            )
                                            current_block_index += 1
                                            cb = {"type": "text", "text": ""}
                                            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': cb})}\n\n"
                                            delta = {"type": "text_delta", "text": combined}
                                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': delta})}\n\n"
                                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                                            # Also check if retry wanted tool_use
                                            retry_tool_uses = [
                                                rb for rb in retry_content
                                                if isinstance(rb, dict) and "toolUse" in rb
                                            ]
                                            if retry_tool_uses:
                                                pending_stop_reason = "tool_use"
                                                for rtu in retry_tool_uses:
                                                    tu = rtu["toolUse"]
                                                    current_block_index += 1
                                                    tu_id = tu.get("toolUseId", f"tooluse_{uuid.uuid4().hex[:24]}")
                                                    cb = {"type": "tool_use", "id": tu_id, "name": tu.get("name", ""), "input": {}}
                                                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': cb})}\n\n"
                                                    input_json = json.dumps(tu.get("input", {}))
                                                    delta = {"type": "input_json_delta", "partial_json": input_json}
                                                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': delta})}\n\n"
                                                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                                            retry_usage = retry_resp.get("usage", {})
                                            output_tokens += retry_usage.get("outputTokens", 0)
                                        else:
                                            logger.warning(
                                                f"Empty-response retry also returned empty for {model_id}"
                                            )
                                    except Exception as retry_err:
                                        logger.warning(f"Empty-response retry failed: {retry_err}")

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
                # GLM 4.7 workaround (same as metadata handler above)
                if pending_stop_reason == "tool_use" and not _stream_has_tool_use:
                    tool_names = {
                        t.get("toolSpec", {}).get("name", "")
                        for t in kwargs.get("toolConfig", {}).get("tools", [])
                    }
                    full_text = "".join(_stream_text_parts)
                    parsed = self._extract_text_tool_calls(full_text, tool_names or None)
                    if not parsed:
                        edge_retry_kwargs = dict(kwargs)
                        if "toolConfig" in edge_retry_kwargs:
                            edge_retry_kwargs["toolConfig"] = dict(edge_retry_kwargs["toolConfig"])
                            edge_retry_kwargs["toolConfig"]["toolChoice"] = {"any": {}}
                        for _ghost_try in range(2):
                            try:
                                async with self.session.client(
                                    "bedrock-runtime",
                                    region_name=self.region,
                                    config=self.config,
                                ) as retry_client:
                                    retry_resp = await retry_client.converse(**edge_retry_kwargs)
                                retry_content = retry_resp.get("output", {}).get("message", {}).get("content", [])
                                for rb in retry_content:
                                    if "toolUse" in rb:
                                        tu = rb["toolUse"]
                                        parsed.append({
                                            "type": "tool_use",
                                            "id": tu.get("toolUseId", f"tooluse_{uuid.uuid4().hex[:24]}"),
                                            "name": tu.get("name", ""),
                                            "input": tu.get("input", {}),
                                        })
                                if parsed:
                                    break
                            except Exception:
                                pass
                            await asyncio.sleep(0.5)
                    if parsed:
                        for tc in parsed:
                            current_block_index += 1
                            cb = {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": {}}
                            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': current_block_index, 'content_block': cb})}\n\n"
                            input_json = json.dumps(tc.get("input", {}))
                            delta = {"type": "input_json_delta", "partial_json": input_json}
                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': current_block_index, 'delta': delta})}\n\n"
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                    else:
                        pending_stop_reason = "end_turn"

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

        Same yield format as ``invoke_model_stream_text``, plus
        ``{"type": "heartbeat"}`` sentinels during long waits.
        """
        import random

        kwargs = self._build_converse_kwargs(model_id, body)
        heartbeat_interval = settings.sse_heartbeat_interval  # default 10s

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
                # Wrap the initial API call with heartbeats to prevent
                # downstream SSE connections from timing out.
                api_call = asyncio.ensure_future(
                    client.converse_stream(**kwargs)
                )
                try:
                    while True:
                        done, _ = await asyncio.wait(
                            {api_call}, timeout=heartbeat_interval
                        )
                        if done:
                            break
                        yield {"type": "heartbeat"}
                    response = api_call.result()
                except BaseException:
                    if not api_call.done():
                        api_call.cancel()
                        try:
                            await api_call
                        except (asyncio.CancelledError, Exception):
                            pass
                    raise
                break
            except Exception as e:
                error_str = str(e)
                if _is_retryable_error(error_str) and attempt < max_retries - 1:
                    backoff = min(2 ** attempt + random.random(), 8)
                    logger.warning(f"Converse stream_text retryable error (attempt {attempt + 1}/{max_retries}): {error_str[:120]}. Retrying in {backoff:.1f}s...")
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
            async for item_type, event in self._iter_with_heartbeat(
                response["stream"], interval=heartbeat_interval
            ):
                if item_type == "heartbeat":
                    yield {"type": "heartbeat"}
                    continue
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
