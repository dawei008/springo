"""
Context Manager for Springo FastAPI
Token 计数、上下文统计、自动摘要、结构化信息提取、工具结果文件管理
"""

import copy
import json
import os
import re
import glob
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Token 计数配置 (defaults — use get_model_limits() for per-model values)
MAX_TOKENS = 200000
SUMMARY_THRESHOLD = 120000
TARGET_AFTER_SUMMARY = 40000
RECENT_MESSAGES_TO_KEEP = 10


def _resolve_limits(model: str = None, **_kwargs) -> tuple:
    """Resolve context limits for a model. Returns (max_tokens, summary_threshold, target_after_summary)."""
    if model:
        from .model_registry import get_model_limits
        limits = get_model_limits(model)
        return limits["max_context_tokens"], limits["compact_threshold"], limits["target_after_summary"]
    return MAX_TOKENS, SUMMARY_THRESHOLD, TARGET_AFTER_SUMMARY

# Tool result size limits (bytes)
MAX_TOOL_RESULT_CONTEXT_SIZE = 8 * 1024   # 8KB per tool result in history
MAX_INLINE_OUTPUT_SIZE = 30 * 1024         # 30KB for inline storage

# Token 缓存
_token_cache: Dict[str, int] = {}
_CACHE_MAX_SIZE = 1000


def _estimate_tokens(text: str) -> int:
    """估算 token 数量（1:3 字符/token 比率）"""
    if not text:
        return 0
    # 尝试使用 tiktoken
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        pass
    # 回退到估算
    return max(1, len(text) // 3)


def count_tokens(text: str) -> int:
    """计算文本的 token 数（带缓存）"""
    if not text:
        return 0

    cache_key = hashlib.md5((text[:1000] + text[-1000:] + str(len(text))).encode()).hexdigest()
    if cache_key in _token_cache:
        return _token_cache[cache_key]

    tokens = _estimate_tokens(text)

    # 缓存管理
    if len(_token_cache) >= _CACHE_MAX_SIZE:
        # FIFO 清理
        keys_to_remove = list(_token_cache.keys())[:_CACHE_MAX_SIZE // 2]
        for k in keys_to_remove:
            _token_cache.pop(k, None)

    _token_cache[cache_key] = tokens
    return tokens


def count_message_tokens(message: Dict[str, Any]) -> int:
    """计算单条消息的 token 数"""
    content = message.get("content", "")
    if isinstance(content, str):
        return count_tokens(content)
    elif isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    total += count_tokens(block.get("text", ""))
                elif block_type == "tool_use":
                    total += count_tokens(json.dumps(block.get("input", {})))
                    total += count_tokens(block.get("name", ""))
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        total += count_tokens(result_content)
                    elif isinstance(result_content, list):
                        for sub in result_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                total += count_tokens(sub.get("text", ""))
                elif block_type == "image":
                    total += 1600  # 图片固定估算
            elif isinstance(block, str):
                total += count_tokens(block)
        return total
    return 0


@dataclass
class TokenBreakdown:
    """Token 分解详情"""
    system_prompt: int = 0
    tools: int = 0
    skills: int = 0
    memory_files: int = 0
    user_text: int = 0
    assistant_text: int = 0
    tool_use: int = 0
    tool_result: int = 0
    images: int = 0
    total: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "skills": self.skills,
            "memory_files": self.memory_files,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "tool_use": self.tool_use,
            "tool_result": self.tool_result,
            "images": self.images,
            "total": self.total,
        }


def compute_breakdown(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    tools: List[Dict] = None,
) -> TokenBreakdown:
    """计算 token 分解"""
    bd = TokenBreakdown()

    # System prompt
    bd.system_prompt = count_tokens(system_prompt)

    # Tools
    if tools:
        bd.tools = count_tokens(json.dumps(tools))

    # Messages
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(content, str):
            if role == "user":
                bd.user_text += count_tokens(content)
            elif role == "assistant":
                bd.assistant_text += count_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if role == "user":
                        bd.user_text += count_tokens(text)
                    else:
                        bd.assistant_text += count_tokens(text)
                elif block_type == "tool_use":
                    bd.tool_use += count_tokens(json.dumps(block.get("input", {})))
                    bd.tool_use += count_tokens(block.get("name", ""))
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        bd.tool_result += count_tokens(result_content)
                    elif isinstance(result_content, list):
                        for sub in result_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                bd.tool_result += count_tokens(sub.get("text", ""))
                elif block_type == "image":
                    bd.images += 1600

    bd.total = (
        bd.system_prompt + bd.tools + bd.skills + bd.memory_files
        + bd.user_text + bd.assistant_text + bd.tool_use + bd.tool_result
        + bd.images
    )
    return bd


def get_context_stats(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    tools: List[Dict] = None,
    model: str = None,
    **_kwargs,
) -> Dict[str, Any]:
    """获取上下文统计信息"""
    max_tok, summary_thresh, _ = _resolve_limits(model)
    bd = compute_breakdown(messages, system_prompt, tools)

    return {
        "total_tokens": bd.total,
        "max_tokens": max_tok,
        "usage_percent": round(bd.total / max_tok * 100, 1) if max_tok > 0 else 0,
        "summary_threshold": summary_thresh,
        "needs_summary": bd.total > summary_thresh,
        "message_count": len(messages),
        "breakdown": bd.to_dict(),
    }


# ============================================================================
# 结构化信息提取
# ============================================================================

# 正则模式
_FILE_PATH_PATTERNS = [
    re.compile(r'(?:^|\s)(/[\w./-]+\.\w+)'),                    # Unix 文件路径
    re.compile(r'(?:^|\s)([A-Z]:\\[\w.\\/-]+\.\w+)'),           # Windows 文件路径
    re.compile(r'`([\w./-]+\.\w+)`'),                             # 反引号引用文件
]
_CODE_BLOCK_PATTERN = re.compile(r'```[\w]*\n(.*?)```', re.DOTALL)
_GOAL_KEYWORDS_EN = re.compile(
    r'(?:I want|I need|please|could you|can you|help me|create|build|implement|fix|add|update|modify|change|remove|delete)',
    re.IGNORECASE
)
_GOAL_KEYWORDS_CN = re.compile(
    r'(?:我想|我需要|请|帮我|创建|构建|实现|修复|添加|更新|修改|改变|删除|移除)'
)
_ERROR_PATTERN = re.compile(
    r'(?:error|错误|failed|失败|exception|traceback|TypeError|ValueError|KeyError|ImportError|SyntaxError|RuntimeError)',
    re.IGNORECASE
)


def _extract_from_text(text: str, info: Dict[str, Any], role: str) -> None:
    """从文本中提取结构化信息（正则匹配）"""
    if not text:
        return

    # 文件路径
    for pattern in _FILE_PATH_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            if match and len(match) > 3 and '.' in match:
                info["files"].add(match)

    # 代码块
    code_blocks = _CODE_BLOCK_PATTERN.findall(text)
    for block in code_blocks:
        if block.strip():
            info["code_snippets"].append(block.strip()[:500])

    # 用户目标
    if role == "user":
        for pattern in [_GOAL_KEYWORDS_EN, _GOAL_KEYWORDS_CN]:
            matches = pattern.findall(text)
            if matches:
                # 提取包含关键词的句子
                sentences = re.split(r'[.。!！?？\n]', text)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if sentence and pattern.search(sentence):
                        info["user_goals"].add(sentence[:200])

    # 错误信息
    error_matches = _ERROR_PATTERN.findall(text)
    if error_matches:
        sentences = re.split(r'[.。\n]', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and _ERROR_PATTERN.search(sentence):
                info["errors"].add(sentence[:300])


def _extract_files_from_tool(tool_name: str, tool_input: Dict, info: Dict[str, Any]) -> None:
    """从工具输入中提取文件路径"""
    # 常见的路径参数名
    path_keys = ["path", "file_path", "filepath", "filename", "file", "directory", "dir",
                 "source", "target", "destination", "src", "dst"]
    for key in path_keys:
        val = tool_input.get(key)
        if val and isinstance(val, str) and ('/' in val or '\\' in val):
            info["files"].add(val)

    # 检查 command 参数中的文件引用
    command = tool_input.get("command", "")
    if command:
        for pattern in _FILE_PATH_PATTERNS:
            matches = pattern.findall(command)
            for match in matches:
                if match and len(match) > 3:
                    info["files"].add(match)


def _summarize_tool_input(tool_name: str, tool_input: Dict) -> str:
    """简要摘要工具输入"""
    if not tool_input:
        return f"{tool_name}()"

    # 提取关键参数的简短描述
    parts = [tool_name]
    for key in ["path", "file_path", "command", "query", "content"]:
        val = tool_input.get(key)
        if val and isinstance(val, str):
            short_val = val[:80] + "..." if len(val) > 80 else val
            parts.append(f"{key}={short_val}")
            break  # 只取第一个关键参数

    return "(" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else f"{tool_name}()"


def extract_structured_info(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """提取文件路径、代码片段、工具使用、用户目标、错误信息"""
    info = {
        "files": set(),
        "code_snippets": [],
        "tool_uses": [],
        "user_goals": set(),
        "errors": set(),
    }

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            _extract_from_text(content, info, role)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "text":
                    _extract_from_text(block.get("text", ""), info, role)
                elif block_type == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    _extract_files_from_tool(tool_name, tool_input, info)
                    summary = _summarize_tool_input(tool_name, tool_input)
                    info["tool_uses"].append(f"{tool_name}: {summary}")
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        _extract_from_text(result_content, info, "tool")

    # Convert sets to sorted lists for serialization
    return {
        "files": sorted(info["files"]),
        "code_snippets": info["code_snippets"][:10],  # 限制数量
        "tool_uses": info["tool_uses"][:20],
        "user_goals": sorted(info["user_goals"]),
        "errors": sorted(info["errors"]),
    }


# ============================================================================
# 结构化摘要 prompt（8 维度中文摘要）
# ============================================================================

def prepare_structured_summary_prompt(
    messages: List[Dict[str, Any]],
    structured_info: Dict[str, Any],
) -> str:
    """生成中文 8 维度结构化摘要 prompt"""

    # 构建对话文本摘要
    conversation_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            conversation_parts.append(f"[{role}]: {content[:300]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        conversation_parts.append(f"[{role}]: {block['text'][:300]}")
                    elif block.get("type") == "tool_use":
                        conversation_parts.append(
                            f"[{role}]: [调用工具 {block.get('name', '?')}]"
                        )

    conversation_text = "\n".join(conversation_parts[:60])

    # 构建结构化信息部分
    info_parts = []
    if structured_info.get("files"):
        info_parts.append(f"涉及文件: {', '.join(structured_info['files'][:20])}")
    if structured_info.get("user_goals"):
        info_parts.append(f"用户目标: {'; '.join(list(structured_info['user_goals'])[:5])}")
    if structured_info.get("errors"):
        info_parts.append(f"错误信息: {'; '.join(list(structured_info['errors'])[:5])}")
    if structured_info.get("tool_uses"):
        info_parts.append(f"工具使用: {'; '.join(structured_info['tool_uses'][:10])}")

    structured_text = "\n".join(info_parts) if info_parts else "无额外结构化信息"

    prompt = f"""请对以下对话进行结构化摘要。请用中文回答，按以下 9 个维度进行总结：

1. **主要任务**: 用户的核心目标和任务描述
2. **用户指令与约束**: 用户明确要求的工作方式（如"用team模式"、"开N个worker"、"不要用XX"、"必须先做XX再做YY"等执行方式、流程约束、禁止事项）。这些指令在后续对话中必须持续遵守，不可遗忘。
3. **关键决策**: 在对话中做出的重要技术决策
4. **涉及文件**: 讨论、修改或创建的文件列表
5. **代码变更**: 主要的代码修改内容摘要
6. **工具使用**: 使用了哪些工具，执行了什么操作
7. **遇到的问题**: 遇到的错误、问题及其解决方案
8. **当前状态**: 任务的当前进展状态
9. **待办事项**: 尚未完成的任务或后续步骤

## 结构化信息
{structured_text}

## 对话内容
{conversation_text}

请按以上 9 个维度输出简洁的摘要，每个维度 1-3 句话。如果某个维度没有相关内容，写"无"。
重要：第 2 维度（用户指令与约束）必须完整保留用户的原始措辞，不要改写或省略。"""

    return prompt


def prepare_summary_prompt(messages: List[Dict[str, Any]]) -> str:
    """wrapper: extract_structured_info -> prepare_structured_summary_prompt"""
    structured_info = extract_structured_info(messages)
    return prepare_structured_summary_prompt(messages, structured_info)


def create_summary_messages(
    summary: str,
    recent_messages: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """构建摘要消息列表：[系统摘要 user msg] + [assistant ack] + recent

    If recent_messages starts with an assistant message, skip the ack
    to avoid consecutive assistant messages (API requires alternating roles).
    """
    # Inject persistent todos into the summary so they survive compaction
    todo_block = ""
    try:
        from .session_state import format_todos_for_context
        todo_block = format_todos_for_context()
    except Exception:
        pass

    summary_content = f"[Context Summary - 对话历史已压缩]\n\n{summary}"
    if todo_block:
        summary_content += f"\n\n{todo_block}"

    summary_user = {
        "role": "user",
        "content": summary_content
    }
    summary_ack = {
        "role": "assistant",
        "content": "我已了解之前的对话摘要，可以继续协助你。请告诉我接下来需要做什么。"
    }

    new_messages = [summary_user]
    # Only add the ack if recent_messages doesn't start with an assistant message
    # (to prevent consecutive assistant messages that violate API alternating-role rules)
    if recent_messages and recent_messages[0].get("role") == "assistant":
        # Skip ack — summary_user (user) + recent[0] (assistant) is already valid
        pass
    else:
        new_messages.append(summary_ack)

    if recent_messages:
        new_messages.extend(recent_messages)

    return new_messages


# ============================================================================
# 智能消息分割（tool_use/tool_result 边界保护）
# ============================================================================

def split_messages_for_summary(
    messages: List[Dict[str, Any]],
    model: str = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """分割消息为 (旧消息, 保留消息)

    关键：tool_use/tool_result 边界保护
    1. 从末尾向前走，累计 token 到 target_after_summary
    2. 确保分割点在 user 消息边界
    3. 如果 user 消息含 tool_result，往前回溯到含 tool_use 的 assistant 消息之前
    """
    _, _, target_after = _resolve_limits(model)

    if len(messages) <= RECENT_MESSAGES_TO_KEEP:
        return [], messages

    # Step 1: 从末尾向前累计 token
    cumulative_tokens = 0
    split_idx = len(messages)

    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = count_message_tokens(messages[i]) + 4  # 结构开销
        cumulative_tokens += msg_tokens

        if cumulative_tokens >= target_after:
            split_idx = i + 1  # 从 i+1 开始保留
            break

    # 确保至少保留 RECENT_MESSAGES_TO_KEEP 条
    max_split = len(messages) - RECENT_MESSAGES_TO_KEEP
    if split_idx > max_split:
        split_idx = max_split
    if split_idx < 1:
        split_idx = 1

    # Step 2: 确保分割点在 user 消息边界
    # 向前调整到最近的 user 消息开始位置
    while split_idx > 0 and split_idx < len(messages):
        if messages[split_idx].get("role") == "user":
            break
        split_idx -= 1

    # Step 3: tool_use/tool_result 边界保护（iterative while loop）
    # 持续回溯，确保不会在 tool_use/tool_result 对中间分割
    adjustments = 0
    max_adjustments = 20  # 安全上限
    while split_idx > 1 and adjustments < max_adjustments:
        msg = messages[split_idx]

        # Case 1: user 消息含 tool_result → 需要包含前面的 assistant tool_use
        if msg.get("role") == "user":
            content = msg.get("content", "")
            has_tool_result = False
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        has_tool_result = True
                        break
            if has_tool_result:
                split_idx -= 1  # 回溯到 assistant 消息
                adjustments += 1
                continue

        # Case 2: assistant 消息含 tool_use → 检查前面是否还有 tool_result 链
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            has_tool_use = False
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        has_tool_use = True
                        break
            if has_tool_use and split_idx > 0:
                prev = messages[split_idx - 1]
                if prev.get("role") == "user":
                    prev_content = prev.get("content", "")
                    prev_has_tool_result = False
                    if isinstance(prev_content, list):
                        for block in prev_content:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                prev_has_tool_result = True
                                break
                    if prev_has_tool_result:
                        split_idx -= 1  # 回溯到前一个 user 消息
                        adjustments += 1
                        continue

        break  # 找到干净的分割点

    if adjustments > 0:
        logger.debug(f"split_messages: adjusted split point {adjustments} times for tool boundary protection")

    # 确保 split_idx 有效
    if split_idx <= 0:
        return [], messages
    if split_idx >= len(messages):
        return messages, []

    old_messages = messages[:split_idx]
    recent_messages = messages[split_idx:]

    return old_messages, recent_messages


# ============================================================================
# 重写 summarize_context（结构化摘要）
# ============================================================================

async def summarize_context(
    messages: List[Dict[str, Any]],
    bedrock_service=None,
    keep_recent: int = 10,
    compact_model: str = None,
) -> Dict[str, Any]:
    """自动摘要上下文（结构化版本）

    Args:
        messages: 完整消息列表
        bedrock_service: Bedrock 服务实例
        keep_recent: 保留最近的消息数（用于 fallback，优先用智能分割）

    Returns:
        {"success": bool, "original_count": int, "new_count": int,
         "tokens_before": int, "tokens_after": int, "messages": [...]}
    """
    if len(messages) <= keep_recent:
        return {
            "success": True,
            "original_count": len(messages),
            "new_count": len(messages),
            "tokens_before": sum(count_message_tokens(m) for m in messages),
            "tokens_after": sum(count_message_tokens(m) for m in messages),
            "messages": messages,
            "skipped": True,
            "reason": "Not enough messages to summarize",
        }

    tokens_before = sum(count_message_tokens(m) for m in messages)

    # Step 1: 智能分割（tool_use/tool_result 边界保护）
    old_messages, recent_messages = split_messages_for_summary(messages)

    if not old_messages:
        return {
            "success": True,
            "original_count": len(messages),
            "new_count": len(messages),
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
            "messages": messages,
            "skipped": True,
            "reason": "No messages to summarize after split",
        }

    # Step 2: 提取结构化信息
    structured_info = extract_structured_info(old_messages)

    # Step 3: 构建结构化摘要 prompt
    summary_prompt = prepare_structured_summary_prompt(old_messages, structured_info)

    # Step 4: 调用 Bedrock 生成摘要
    summary_text = ""
    if bedrock_service:
        try:
            from ..config import get_settings
            from .model_registry import get_model_info, get_bedrock_id
            _settings = get_settings()
            _compact_model_name = compact_model or _settings.compact_model_id

            # Determine api_format for the compact model
            _compact_api_format = "anthropic"
            _model_info = get_model_info(_compact_model_name)
            if _model_info:
                _compact_api_format = _model_info.get("api_format", "anthropic")

            # Guard: summarization only supports anthropic-format models.
            # If a converse-format model is configured, fall back to a safe default.
            _FALLBACK_COMPACT_MODEL = "claude-haiku-4-5-20251001"
            if _compact_api_format == "converse":
                logger.warning(
                    f"Compact model '{_compact_model_name}' uses converse API format "
                    f"which is not supported for summarization. "
                    f"Falling back to '{_FALLBACK_COMPACT_MODEL}'."
                )
                _compact_model_name = _FALLBACK_COMPACT_MODEL
                _compact_api_format = "anthropic"

            # Resolve short model name to Bedrock ID
            _compact_model_id = _compact_model_name
            if not _compact_model_id.startswith(("us.", "deepseek.", "minimax.", "moonshotai.", "moonshot.", "qwen.", "zai.")):
                _compact_model_id = get_bedrock_id(_compact_model_name)

            # Build the request body (anthropic InvokeModel format)
            _compact_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": summary_prompt}],
            }
            result = await bedrock_service.invoke_model(
                model_id=_compact_model_id,
                body=_compact_body,
                api_format=_compact_api_format,
            )
            if result and isinstance(result, dict):
                content = result.get("content", [])
                if content and isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            summary_text = block["text"]
                            break
        except Exception as e:
            logger.warning(f"Bedrock structured summary failed: {e}")

    if not summary_text:
        # 回退到简单摘要
        summary_parts = []
        for msg in old_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                summary_parts.append(f"[{role}]: {content[:200]}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                        summary_parts.append(f"[{role}]: {block['text'][:200]}")

        if not summary_parts:
            return {
                "success": True,
                "original_count": len(messages),
                "new_count": len(messages),
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "messages": messages,
                "skipped": True,
                "reason": "No content to summarize",
            }

        summary_text = "Previous conversation summary:\n" + "\n".join(summary_parts[:20])

    # Step 5: 构建新消息列表
    new_messages = create_summary_messages(summary_text, recent_messages)
    tokens_after = sum(count_message_tokens(m) for m in new_messages)

    logger.info(
        f"Structured summary: {len(old_messages)} old msgs -> summary, "
        f"kept {len(recent_messages)} recent, "
        f"tokens {tokens_before:,} -> {tokens_after:,}"
    )

    return {
        "success": True,
        "original_count": len(messages),
        "new_count": len(new_messages),
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "tokens_saved": tokens_before - tokens_after,
        "messages": new_messages,
    }


# ============================================================================
# Pre-compaction Memory Flush (OpenClaw pattern)
# ============================================================================

# Flush prompt: write a detailed journal of messages about to be compacted.
_MEMORY_FLUSH_PROMPT = """You are a session journal writer. The following conversation messages are about to be compacted (summarized and discarded). Your job is to write a **detailed journal** capturing what happened so it can be referenced in future sessions.

Rules:
- If the messages contain only greetings or trivial chitchat, respond with exactly: NOTHING_TO_REMEMBER
- Otherwise, write a detailed Markdown journal covering:
  - **What was done**: tasks attempted, tools used, commands run (include actual commands/code snippets)
  - **Key decisions**: why certain approaches were chosen over others
  - **Outcomes**: what worked, what failed, error messages encountered
  - **User preferences**: any stated or implied preferences
  - **Open items**: unfinished tasks, next steps, blockers
- Use Markdown headers (###), bullet lists, and fenced code blocks for commands/code
- Include specific file paths, URLs, model names, config values — concrete details matter
- Do NOT over-summarize — preserve enough context for future reference

Messages to analyze:
{messages_text}"""


async def pre_compaction_memory_flush(
    messages: List[Dict[str, Any]],
    bedrock_service=None,
    compact_model: str = None,
) -> Dict[str, Any]:
    """Extract and persist key facts from messages before context compaction.

    This implements the OpenClaw "pre-compaction flush" pattern: before context
    is compressed, a fast model extracts important facts and writes them to
    the daily memory log via memory_write.

    Args:
        messages: Messages that are about to be compacted (the "old" portion)
        bedrock_service: Bedrock service instance for model calls
        compact_model: Model to use for extraction (defaults to compact_model from settings)

    Returns:
        Dict with flush results: {flushed: bool, facts_count: int, error: str?}
    """
    if not messages or not bedrock_service:
        return {"flushed": False, "reason": "no_messages_or_service"}

    # Build text representation of messages (truncated to stay within limits)
    text_parts = []
    total_chars = 0
    MAX_CHARS = 128000  # Haiku has 200K context; allow full conversation visibility

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text blocks
            content = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        if not content or not content.strip():
            continue
        # Skip tool results (noisy)
        if role == "tool":
            continue

        snippet = content.strip()[:2000]
        line = f"[{role}]: {snippet}"
        if total_chars + len(line) > MAX_CHARS:
            break
        text_parts.append(line)
        total_chars += len(line)

    if not text_parts:
        return {"flushed": False, "reason": "no_text_content"}

    messages_text = "\n".join(text_parts)
    flush_prompt = _MEMORY_FLUSH_PROMPT.format(messages_text=messages_text)

    # Call fast model to extract facts
    try:
        from ..config import get_settings
        from .model_registry import get_model_info, get_bedrock_id

        _settings = get_settings()
        _flush_model = compact_model or _settings.compact_model_id

        # Use anthropic format
        _model_info = get_model_info(_flush_model)
        _api_format = "anthropic"
        if _model_info:
            _api_format = _model_info.get("api_format", "anthropic")

        _FALLBACK = "claude-haiku-4-5-20251001"
        if _api_format == "converse":
            _flush_model = _FALLBACK
            _api_format = "anthropic"

        _flush_model_id = _flush_model
        if not _flush_model_id.startswith(("us.", "deepseek.", "minimax.", "moonshotai.", "moonshot.", "qwen.", "zai.")):
            _flush_model_id = get_bedrock_id(_flush_model)

        flush_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": flush_prompt}],
        }

        result = await bedrock_service.invoke_model(
            model_id=_flush_model_id,
            body=flush_body,
            api_format=_api_format,
        )

        # Extract response text
        response_text = ""
        if result and isinstance(result, dict):
            content_blocks = result.get("content", [])
            if content_blocks and isinstance(content_blocks, list):
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        response_text = block["text"]
                        break

        if not response_text or "NOTHING_TO_REMEMBER" in response_text:
            logger.info("[MemoryFlush] No important facts to persist")
            return {"flushed": False, "reason": "nothing_to_remember"}

        # Write extracted facts to daily memory log
        from mcp_tools.handlers.memory_tools import memory_write

        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        content_to_write = f"## Pre-compaction flush ({today})\n\n{response_text.strip()}\n"
        write_result = memory_write(target="daily", content=content_to_write)

        if write_result.get("success"):
            # Count facts (lines starting with -)
            facts_count = sum(1 for line in response_text.split("\n") if line.strip().startswith("-"))
            logger.info(f"[MemoryFlush] Persisted {facts_count} facts to {write_result.get('path')}")
            return {"flushed": True, "facts_count": facts_count, "path": write_result.get("path")}
        else:
            logger.warning(f"[MemoryFlush] memory_write failed: {write_result.get('error')}")
            return {"flushed": False, "error": write_result.get("error")}

    except Exception as e:
        logger.warning(f"[MemoryFlush] Failed: {e}")
        return {"flushed": False, "error": str(e)}


# ============================================================================
# 自动摘要检查
# ============================================================================

def check_and_prepare_auto_summary(
    messages: List[Dict[str, Any]],
    model: str = None,
) -> Optional[Dict[str, Any]]:
    """检查是否需要摘要，返回准备信息

    Returns:
        None if no summary needed, else:
        {needs_summary, summary_prompt, old_messages_count, recent_messages, structured_info}
    """
    if not should_summarize(messages, model=model):
        return None

    if len(messages) <= RECENT_MESSAGES_TO_KEEP:
        return None

    old_messages, recent_messages = split_messages_for_summary(messages, model=model)

    if not old_messages:
        return None

    structured_info = extract_structured_info(old_messages)
    summary_prompt = prepare_structured_summary_prompt(old_messages, structured_info)

    return {
        "needs_summary": True,
        "summary_prompt": summary_prompt,
        "old_messages_count": len(old_messages),
        "recent_messages": recent_messages,
        "structured_info": structured_info,
    }


# ============================================================================
# 详细上下文分解
# ============================================================================

def get_context_breakdown(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    tools: List[Dict] = None,
    skills: List[Dict] = None,
    memory_files: List[Dict] = None,
    model: str = None,
    **_kwargs,
) -> Dict[str, Any]:
    """详细分解：每个分类返回 {tokens, count, percent}

    分类：system_prompt, system_tools, skills, memory_files, user_text,
          assistant_text, tool_use, tool_result, images, other
    """
    breakdown = {}

    # System prompt
    sys_tokens = count_tokens(system_prompt) if system_prompt else 0
    breakdown["system_prompt"] = {"tokens": sys_tokens, "count": 1 if system_prompt else 0}

    # Tools (system_tools)
    tools_tokens = count_tokens(json.dumps(tools)) if tools else 0
    breakdown["system_tools"] = {"tokens": tools_tokens, "count": len(tools) if tools else 0}

    # Skills
    skills_tokens = 0
    skills_count = 0
    if skills:
        for skill in skills:
            skills_tokens += count_tokens(json.dumps(skill))
            skills_count += 1
    breakdown["skills"] = {"tokens": skills_tokens, "count": skills_count}

    # Memory files
    mem_tokens = 0
    mem_count = 0
    if memory_files:
        for mf in memory_files:
            mem_tokens += count_tokens(json.dumps(mf))
            mem_count += 1
    breakdown["memory_files"] = {"tokens": mem_tokens, "count": mem_count}

    # Message categories
    user_text_tokens = 0
    user_text_count = 0
    assistant_text_tokens = 0
    assistant_text_count = 0
    tool_use_tokens = 0
    tool_use_count = 0
    tool_result_tokens = 0
    tool_result_count = 0
    image_tokens = 0
    image_count = 0
    other_tokens = 0

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(content, str):
            t = count_tokens(content)
            if role == "user":
                user_text_tokens += t
                user_text_count += 1
            elif role == "assistant":
                assistant_text_tokens += t
                assistant_text_count += 1
            else:
                other_tokens += t
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "text":
                    t = count_tokens(block.get("text", ""))
                    if role == "user":
                        user_text_tokens += t
                        user_text_count += 1
                    elif role == "assistant":
                        assistant_text_tokens += t
                        assistant_text_count += 1
                    else:
                        other_tokens += t
                elif block_type == "tool_use":
                    tool_use_tokens += count_tokens(json.dumps(block.get("input", {})))
                    tool_use_tokens += count_tokens(block.get("name", ""))
                    tool_use_count += 1
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        tool_result_tokens += count_tokens(result_content)
                    elif isinstance(result_content, list):
                        for sub in result_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                tool_result_tokens += count_tokens(sub.get("text", ""))
                    tool_result_count += 1
                elif block_type == "image":
                    image_tokens += 1600
                    image_count += 1

    breakdown["user_text"] = {"tokens": user_text_tokens, "count": user_text_count}
    breakdown["assistant_text"] = {"tokens": assistant_text_tokens, "count": assistant_text_count}
    breakdown["tool_use"] = {"tokens": tool_use_tokens, "count": tool_use_count}
    breakdown["tool_result"] = {"tokens": tool_result_tokens, "count": tool_result_count}
    breakdown["images"] = {"tokens": image_tokens, "count": image_count}
    breakdown["other"] = {"tokens": other_tokens, "count": 0}

    # Calculate total and percents
    total_tokens = sum(v["tokens"] for v in breakdown.values()) + len(messages) * 4
    for cat in breakdown:
        tokens = breakdown[cat]["tokens"]
        breakdown[cat]["percent"] = round((tokens / total_tokens) * 100, 1) if total_tokens > 0 else 0

    max_tok, _, _ = _resolve_limits(model)
    return {
        "breakdown": breakdown,
        "total_tokens": total_tokens,
        "max_tokens": max_tok,
        "usage_percent": round((total_tokens / max_tok) * 100, 1) if max_tok > 0 else 0,
        "messages_count": len(messages),
    }


def auto_check_context(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    tools: List[Dict] = None,
    model: str = None,
) -> Dict[str, Any]:
    """自动检查上下文健康状况"""
    stats = get_context_stats(messages, system_prompt, tools, model=model)

    warnings = []
    actions = []

    usage_pct = stats["usage_percent"]

    if usage_pct >= 95:
        warnings.append("CRITICAL: Context at 95%+ capacity, messages may be truncated")
        actions.append("immediate_summary")
    elif usage_pct >= 80:
        warnings.append("WARNING: Context at 80%+ capacity, summary recommended")
        actions.append("suggest_summary")
    elif usage_pct >= 60:
        warnings.append("INFO: Context at 60%+ capacity")

    # 检查工具结果占比
    bd = stats["breakdown"]
    if bd["tool_result"] > 0 and bd["total"] > 0:
        tool_result_pct = bd["tool_result"] / bd["total"] * 100
        if tool_result_pct > 50:
            warnings.append(f"Tool results occupy {tool_result_pct:.0f}% of context, consider truncating old results")
            actions.append("truncate_tool_results")

    # 检查消息数量
    if stats["message_count"] > 100:
        warnings.append(f"High message count ({stats['message_count']}), consider summarizing")
        actions.append("suggest_summary")

    return {
        "healthy": len(warnings) == 0,
        "usage_percent": usage_pct,
        "total_tokens": stats["total_tokens"],
        "max_tokens": stats["max_tokens"],
        "warnings": warnings,
        "recommended_actions": list(set(actions)),
        "breakdown": bd,
    }


def count_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """计算所有消息的总 token 数"""
    total = 0
    for msg in messages:
        total += count_message_tokens(msg)
        total += 4  # 消息结构开销
    return total


def should_summarize(messages: List[Dict[str, Any]], model: str = None, **_kwargs) -> bool:
    """检查是否需要摘要"""
    _, summary_thresh, _ = _resolve_limits(model)
    return count_messages_tokens(messages) > summary_thresh


def truncate_tool_results(
    messages: List[Dict[str, Any]],
    max_size: int = None,
) -> List[Dict[str, Any]]:
    """
    截断消息中的工具结果，防止上下文溢出。
    保留前半段 + 截断提示 + 后四分之一。

    Args:
        messages: 消息列表
        max_size: 每个工具结果的最大字节数 (默认 MAX_TOOL_RESULT_CONTEXT_SIZE)

    Returns:
        截断后的新消息列表
    """
    if max_size is None:
        max_size = MAX_TOOL_RESULT_CONTEXT_SIZE

    result = []
    for msg in messages:
        content = msg.get("content", "")

        if msg.get("role") == "user" and isinstance(content, list):
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        content_size = len(result_content.encode('utf-8'))
                        if content_size > max_size:
                            truncated = result_content[:max_size // 2]
                            truncated += f"\n\n[... truncated {content_size - max_size:,} bytes ...]\n\n"
                            truncated += result_content[-(max_size // 4):]
                            new_content.append({**block, "content": truncated})
                        else:
                            new_content.append(block)
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)

    return result


def _strip_old_images(
    messages: List[Dict[str, Any]],
    keep_recent_images: int = 3,
) -> List[Dict[str, Any]]:
    """Strip image blocks from older tool_results, keeping only recent ones.

    Bedrock enforces stricter dimension limits for many-image requests
    (2000px max). To avoid this, we replace older screenshot images with
    a text placeholder, keeping only the N most recent images.

    Args:
        messages: Message list (mutated in place for efficiency).
        keep_recent_images: Number of most recent images to preserve.

    Returns:
        Messages with old images replaced by text placeholders.
    """
    # First pass: find all image positions (msg_idx, block_idx, sub_block_idx)
    image_positions = []
    for i, msg in enumerate(messages):
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for j, block in enumerate(content):
            if block.get("type") != "tool_result":
                continue
            rc = block.get("content", "")
            if not isinstance(rc, list):
                continue
            for k, sub in enumerate(rc):
                if sub.get("type") == "image":
                    image_positions.append((i, j, k))

    if len(image_positions) <= keep_recent_images:
        return messages

    # Strip older images (keep the last N)
    to_strip = image_positions[:-keep_recent_images]
    result = copy.deepcopy(messages)

    for msg_idx, block_idx, sub_idx in reversed(to_strip):
        block = result[msg_idx]["content"][block_idx]
        rc = block["content"]
        # Replace image block with text placeholder
        rc[sub_idx] = {
            "type": "text",
            "text": "[screenshot removed from history]",
        }

    return result


def prepare_messages_for_api(
    messages: List[Dict[str, Any]],
    keep_recent: int = 3,
) -> List[Dict[str, Any]]:
    """
    为 API 调用准备消息：截断旧工具结果，保留最近的完整。

    Args:
        messages: 消息列表
        keep_recent: 保留最近 N 条 user 消息的工具结果完整

    Returns:
        处理后的消息列表
    """
    if not messages:
        return messages

    user_msg_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]

    if len(user_msg_indices) <= keep_recent:
        # Still need to strip old images even if messages are few
        return _strip_old_images(messages)

    cutoff_idx = user_msg_indices[-keep_recent] if keep_recent > 0 else len(messages)

    older = truncate_tool_results(messages[:cutoff_idx])
    recent = messages[cutoff_idx:]

    combined = older + recent
    # Strip old screenshot images to avoid Bedrock many-image limits
    return _strip_old_images(combined)


def repair_orphan_tool_uses(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    修复孤立的 tool_use 和 tool_result 块。

    处理三种情况：
    1. 孤立 tool_use: tool_use 没有对应的 tool_result → 补 dummy tool_result
    2. 孤立 tool_result: tool_result 没有对应的 tool_use（被裁剪掉了）→ 移除该 tool_result
    3. Context compaction 产生重复的 tool ID

    Bedrock API 要求：
    - 每个 tool_use 必须在紧接着的 user 消息中有对应的 tool_result
    - 每个 tool_result 必须在前一条 assistant 消息中有对应的 tool_use

    Args:
        messages: 需要修复的消息列表

    Returns:
        修复后的消息列表
    """
    if not messages:
        return messages

    # ── Pass 1: Collect all tool_use IDs and find orphans in both directions ──

    # Track tool_use IDs from the immediately preceding assistant message
    tool_uses_needing_result = []  # (msg_index, tool_id, tool_name)
    all_tool_use_ids = set()       # Every tool_use ID in the entire conversation
    seen_tool_ids = set()

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", [])

        if isinstance(content, list):
            if role == "assistant":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        tool_name = block.get("name", "unknown")
                        if tool_id:
                            if tool_id in seen_tool_ids:
                                logger.warning(f"Duplicate tool_use ID: {tool_id[:30]}... in msg[{i}]")
                            seen_tool_ids.add(tool_id)
                            all_tool_use_ids.add(tool_id)
                            tool_uses_needing_result.append((i, tool_id, tool_name))

            elif role == "user":
                tool_result_ids_here = set()
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_ids_here.add(block.get("tool_use_id"))

                remaining = []
                for (msg_idx, tool_id, tool_name) in tool_uses_needing_result:
                    if msg_idx == i - 1 and tool_id in tool_result_ids_here:
                        pass  # satisfied
                    else:
                        remaining.append((msg_idx, tool_id, tool_name))
                tool_uses_needing_result = remaining

    # ── Pass 1b: Build adjacency map — for each user msg, which tool_use IDs
    # are in the immediately preceding assistant message ──
    # Key present → previous message IS assistant (value may be empty set = no tool_use blocks)
    # Key absent  → previous message is NOT assistant (or i == 0)
    prev_assistant_tool_ids: Dict[int, set] = {}  # user_msg_index -> set of tool_use IDs from prev assistant
    for i, msg in enumerate(messages):
        if msg.get("role") == "user" and i > 0:
            prev_msg = messages[i - 1]
            if prev_msg.get("role") == "assistant":
                ids = set()
                content = prev_msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                            ids.add(block["id"])
                # Always set — even empty set means "assistant exists but has no tool_use blocks"
                prev_assistant_tool_ids[i] = ids

    # ── Pass 2: Build repaired message list ──
    # Fix orphan tool_uses (add dummy results) AND orphan tool_results (remove them)

    needs_tool_use_repair = bool(tool_uses_needing_result)
    orphans_by_msg = {}
    if needs_tool_use_repair:
        logger.warning(f"Found {len(tool_uses_needing_result)} orphan tool_use blocks, repairing...")
        for (msg_idx, tool_id, tool_name) in tool_uses_needing_result:
            if msg_idx not in orphans_by_msg:
                orphans_by_msg[msg_idx] = []
            orphans_by_msg[msg_idx].append((tool_id, tool_name))

    repaired = []
    pending_orphans = []

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", [])

        # ── Handle user messages ──
        if role == "user" and isinstance(content, list):
            new_content = []

            # Inject dummy tool_results for orphan tool_uses from previous assistant
            if pending_orphans:
                for tool_id, tool_name in pending_orphans:
                    new_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": f"[Tool execution interrupted - user sent new message before {tool_name} completed]",
                        "is_error": True,
                    })
                logger.info(f"Merged {len(pending_orphans)} dummy tool_results into user msg[{i}]")
                pending_orphans = []

            # Filter out orphan tool_results:
            # 1. tool_use_id not in conversation at all → orphan
            # 2. tool_use_id exists but NOT in the immediately preceding assistant msg → adjacency orphan
            # 3. No preceding assistant message at all → orphan (e.g., after compaction)
            # Note: use .get() without default — None means "no adjacent assistant",
            # empty set means "assistant exists but has no tool_use blocks"
            adjacent_ids = prev_assistant_tool_ids.get(i)  # None or set
            orphan_result_count = 0
            adjacency_orphan_count = 0
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    ref_id = block.get("tool_use_id")
                    if ref_id and ref_id not in all_tool_use_ids:
                        orphan_result_count += 1
                        continue  # Drop: no matching tool_use anywhere
                    # Bedrock requires tool_result's tool_use_id to be in the immediately
                    # preceding assistant message. Drop if: (a) no adjacent assistant, or
                    # (b) adjacent assistant has no matching tool_use block.
                    if ref_id and (adjacent_ids is None or ref_id not in adjacent_ids):
                        adjacency_orphan_count += 1
                        continue  # Drop: tool_use not in immediately preceding assistant
                new_content.append(block)

            if orphan_result_count:
                logger.warning(
                    f"Removed {orphan_result_count} orphan tool_result(s) from user msg[{i}] "
                    f"(no matching tool_use in conversation)"
                )
            if adjacency_orphan_count:
                logger.warning(
                    f"Removed {adjacency_orphan_count} adjacency-orphan tool_result(s) from user msg[{i}] "
                    f"(tool_use exists but not in previous assistant message)"
                )

            # If all content was removed, add a placeholder
            if not new_content:
                new_content = [{"type": "text", "text": "[Previous tool results removed due to context compaction]"}]

            repaired.append({"role": "user", "content": new_content})

        elif role == "user" and pending_orphans:
            # User message with string content but orphan tool_uses pending
            dummy_results = []
            for tool_id, tool_name in pending_orphans:
                dummy_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"[Tool execution interrupted - user sent new message before {tool_name} completed]",
                    "is_error": True,
                })
            existing = msg.get("content", "")
            merged = dummy_results + ([{"type": "text", "text": existing}] if existing else [])
            repaired.append({"role": "user", "content": merged})
            logger.info(f"Merged {len(dummy_results)} dummy tool_results into string user msg[{i}]")
            pending_orphans = []
        elif role == "assistant" and pending_orphans:
            # Consecutive assistant messages with pending orphan tool_uses from previous assistant.
            # Insert a synthetic user message with dummy tool_results BEFORE this assistant message.
            dummy_results = []
            for tool_id, tool_name in pending_orphans:
                dummy_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"[Tool execution interrupted - {tool_name} result lost during context compaction]",
                    "is_error": True,
                })
            repaired.append({"role": "user", "content": dummy_results})
            logger.info(f"Inserted synthetic user msg with {len(dummy_results)} dummy tool_results before assistant msg[{i}]")
            pending_orphans = []
            repaired.append(msg)
        else:
            repaired.append(msg)

        if role == "assistant" and i in orphans_by_msg:
            pending_orphans = orphans_by_msg[i]

    # ── Handle trailing orphan tool_uses (no subsequent user message) ──
    if pending_orphans:
        dummy_results = []
        for tool_id, tool_name in pending_orphans:
            dummy_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"[Tool execution interrupted - no response received for {tool_name}]",
                "is_error": True,
            })
        repaired.append({"role": "user", "content": dummy_results})
        logger.info(f"Added {len(dummy_results)} dummy tool_results at end of messages")

    return repaired


def save_tool_result(
    session_id: str,
    tool_use_id: str,
    result: str,
    tool_name: str = None,
) -> Dict[str, Any]:
    """
    Save large tool result to file and return reference.
    Small results are returned inline; large results (>MAX_INLINE_OUTPUT_SIZE)
    are written to disk with a truncated preview.

    Args:
        session_id: The session ID
        tool_use_id: The tool use ID (unique identifier)
        result: The tool result content string
        tool_name: Optional tool name for metadata

    Returns:
        Dict with:
        - {"inline": True, "content": result, "size": int}  if small
        - {"inline": False, "file_path": str, "size": int, "preview": str}  if large
    """
    result_bytes = result.encode('utf-8')
    result_size = len(result_bytes)

    # Small result: return inline
    if result_size <= MAX_INLINE_OUTPUT_SIZE:
        return {"inline": True, "content": result, "size": result_size}

    # Large result: save to file
    tool_results_dir = get_tool_results_dir(session_id)
    os.makedirs(tool_results_dir, exist_ok=True)

    result_path = get_tool_result_path(session_id, tool_use_id, tool_name)

    try:
        with open(result_path, 'w', encoding='utf-8') as f:
            metadata = {
                "type": "tool_result",
                "session_id": session_id,
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "timestamp": datetime.now().isoformat(),
                "size": result_size,
            }
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            f.write("---\n")
            f.write(result)
    except Exception as e:
        logger.error(f"Failed to save tool result to {result_path}: {e}")
        return {"inline": True, "content": result, "size": result_size}

    preview = result[:500] + "..." if len(result) > 500 else result

    return {
        "inline": False,
        "file_path": result_path,
        "size": result_size,
        "preview": preview,
    }


# ============================================================================
# 工具结果文件管理
# ============================================================================

def get_tool_results_dir(session_id: str) -> str:
    """获取工具结果目录"""
    sessions_dir = os.path.expanduser("~/.springo/sessions")
    return os.path.join(sessions_dir, session_id, "tool-results")


def get_tool_result_path(session_id: str, tool_use_id: str, tool_name: str = None) -> str:
    """获取工具结果文件路径

    命名约定：
    - Bedrock: toolu_bdrk_{id}.txt
    - MCP: mcp-{server}-{tool}-{ts}.txt
    - 默认: {tool_use_id}_{tool_name}.json
    """
    tool_results_dir = get_tool_results_dir(session_id)

    if tool_use_id.startswith("toolu_bdrk_"):
        filename = f"{tool_use_id}.txt"
    elif tool_name and tool_name.startswith("mcp_"):
        parts = tool_name.split("_", 2)
        server = parts[1] if len(parts) > 1 else "unknown"
        tool = parts[2] if len(parts) > 2 else "unknown"
        ts = int(datetime.now().timestamp())
        filename = f"mcp-{server}-{tool}-{ts}.txt"
    else:
        safe_name = (tool_name or "unknown").replace("/", "_").replace("\\", "_")[:50]
        filename = f"{tool_use_id}_{safe_name}.json"

    return os.path.join(tool_results_dir, filename)


def find_tool_result_file(session_id: str, tool_use_id: str) -> Optional[str]:
    """查找工具结果文件"""
    tool_results_dir = get_tool_results_dir(session_id)

    if not os.path.exists(tool_results_dir):
        return None

    # 直接匹配
    for pattern in [f"{tool_use_id}*", f"*{tool_use_id}*"]:
        matches = glob.glob(os.path.join(tool_results_dir, pattern))
        if matches:
            return matches[0]

    return None


def load_tool_result(file_path: str) -> Optional[str]:
    """加载工具结果内容"""
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 跳过元数据头
        if "\n---\n" in content:
            _, result = content.split("\n---\n", 1)
            return result
        return content
    except Exception as e:
        logger.error(f"Failed to load tool result from {file_path}: {e}")
        return None


def list_tool_results(session_id: str) -> List[Dict[str, Any]]:
    """列出会话的所有工具结果文件"""
    tool_results_dir = get_tool_results_dir(session_id)

    if not os.path.exists(tool_results_dir):
        return []

    results = []
    for filename in os.listdir(tool_results_dir):
        if filename.startswith('.'):
            continue
        filepath = os.path.join(tool_results_dir, filename)
        try:
            stat = os.stat(filepath)
            # 尝试读取元数据
            metadata = {}
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line:
                    try:
                        metadata = json.loads(first_line)
                    except json.JSONDecodeError:
                        pass

            results.append({
                "filename": filename,
                "path": filepath,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "tool_use_id": metadata.get("tool_use_id", ""),
                "tool_name": metadata.get("tool_name", ""),
            })
        except Exception:
            continue

    return sorted(results, key=lambda x: x.get("modified", ""), reverse=True)


def cleanup_old_tool_results(max_age_days: int = 7) -> int:
    """清理过期的工具结果文件"""
    sessions_dir = os.path.expanduser("~/.springo/sessions")
    if not os.path.exists(sessions_dir):
        return 0

    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed = 0

    for session_id in os.listdir(sessions_dir):
        tool_results_dir = os.path.join(sessions_dir, session_id, "tool-results")
        if not os.path.isdir(tool_results_dir):
            continue

        for filename in os.listdir(tool_results_dir):
            if filename.startswith('.'):
                continue
            filepath = os.path.join(tool_results_dir, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    removed += 1
            except Exception:
                continue

    if removed:
        logger.info(f"Cleaned up {removed} old tool result files (>{max_age_days} days)")
    return removed


# ============================================================================
# 摘要事件记录
# ============================================================================

def save_summary_event(
    session_id: str,
    summary: str,
    old_count: int,
    new_count: int,
) -> None:
    """记录摘要事件到会话目录"""
    sessions_dir = os.path.expanduser("~/.springo/sessions")
    session_dir = os.path.join(sessions_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)

    event_file = os.path.join(session_dir, "summary_events.jsonl")
    event = {
        "type": "summary_event",
        "timestamp": datetime.now().isoformat(),
        "old_message_count": old_count,
        "new_message_count": new_count,
        "summary_length": len(summary),
        "summary_preview": summary[:200],
    }

    try:
        with open(event_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to save summary event: {e}")


# 导出
__all__ = [
    'count_tokens', 'count_message_tokens', 'count_messages_tokens',
    'compute_breakdown', 'get_context_stats', 'get_context_breakdown',
    'summarize_context', 'auto_check_context', 'should_summarize',
    'check_and_prepare_auto_summary',
    'split_messages_for_summary', 'create_summary_messages',
    'prepare_summary_prompt', 'prepare_structured_summary_prompt',
    'extract_structured_info',
    'truncate_tool_results', 'prepare_messages_for_api', 'repair_orphan_tool_uses',
    'save_tool_result',
    'get_tool_results_dir', 'get_tool_result_path', 'find_tool_result_file',
    'load_tool_result', 'list_tool_results', 'cleanup_old_tool_results',
    'save_summary_event',
    'TokenBreakdown', 'MAX_TOKENS', 'SUMMARY_THRESHOLD', 'TARGET_AFTER_SUMMARY',
    'RECENT_MESSAGES_TO_KEEP',
    'MAX_TOOL_RESULT_CONTEXT_SIZE', 'MAX_INLINE_OUTPUT_SIZE',
]
