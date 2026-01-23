"""
Context Manager for Springo
Enhanced version with Claude Code-like features:
- Automatic summarization
- Structured summaries
- Session persistence (JSONL)
- Layered context management
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional tiktoken import
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


class ContextManager:
    """
    Manages conversation context with Claude Code-like features:
    - Token counting and automatic summarization
    - Structured summary format (preserves files, decisions, code)
    - JSONL session persistence
    - Layered context (system + summary + recent)
    """

    # Claude's context window configuration
    MAX_TOKENS = 200000  # Claude 3.5 Sonnet/Opus context window
    SUMMARY_THRESHOLD = 120000  # Trigger at 60% to leave room for response
    TARGET_AFTER_SUMMARY = 40000  # Target size after summarization
    RECENT_MESSAGES_TO_KEEP = 10  # Always keep last N messages in full

    # Session storage directory
    SESSIONS_DIR = os.path.expanduser("~/.springo/sessions")

    def __init__(self):
        if HAS_TIKTOKEN:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self._encoder = None

        # Ensure sessions directory exists
        Path(self.SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

        # In-memory context state per session
        self._session_contexts: Dict[str, Dict] = {}

        # OPTIMIZATION 2: Token count cache (message hash -> token count)
        self._token_cache: Dict[str, int] = {}
        self._token_cache_max_size = 1000  # Limit cache size

    # ========== Token Counting ==========

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string"""
        if not text:
            return 0
        if self._encoder:
            return len(self._encoder.encode(text))
        else:
            # Fallback: rough estimation (1 token ≈ 4 characters for English, 2 for Chinese)
            return len(text) // 3

    def _get_message_hash(self, message: Dict[str, Any]) -> str:
        """Generate a hash for a message for caching purposes"""
        # Use a fast hash of the JSON representation
        content = json.dumps(message, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()

    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a single message (with caching)"""
        # OPTIMIZATION 2: Check cache first
        msg_hash = self._get_message_hash(message)
        if msg_hash in self._token_cache:
            return self._token_cache[msg_hash]

        # Calculate tokens
        content = message.get("content", "")
        total = 0

        if isinstance(content, str):
            total = self.count_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += self.count_tokens(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        total += self.count_tokens(json.dumps(block.get("input", {})))
                        total += self.count_tokens(block.get("name", ""))
                    elif block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            total += self.count_tokens(result_content)
                        else:
                            total += self.count_tokens(json.dumps(result_content))
                    elif block.get("type") == "image":
                        total += 1500  # Image tokens estimate
                elif isinstance(block, str):
                    total += self.count_tokens(block)

        # Store in cache (with size limit)
        if len(self._token_cache) >= self._token_cache_max_size:
            # Remove oldest entries (simple FIFO-like cleanup)
            keys_to_remove = list(self._token_cache.keys())[:100]
            for key in keys_to_remove:
                del self._token_cache[key]
        self._token_cache[msg_hash] = total

        return total

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in all messages"""
        total = 0
        for message in messages:
            total += self.count_message_tokens(message)
            total += 4  # Message structure overhead
        return total

    # ========== Context Statistics ==========

    def get_context_stats(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get detailed statistics about the current context"""
        total_tokens = self.count_messages_tokens(messages)
        usage_percent = round((total_tokens / self.MAX_TOKENS) * 100, 1)

        # Determine status level
        if usage_percent >= 80:
            status = "critical"
        elif usage_percent >= 60:
            status = "warning"
        else:
            status = "normal"

        return {
            "total_tokens": total_tokens,
            "max_tokens": self.MAX_TOKENS,
            "usage_percent": usage_percent,
            "threshold_tokens": self.SUMMARY_THRESHOLD,
            "needs_summarization": total_tokens > self.SUMMARY_THRESHOLD,
            "messages_count": len(messages),
            "tiktoken_available": HAS_TIKTOKEN,
            "status": status,
            "can_auto_summarize": total_tokens > self.SUMMARY_THRESHOLD
        }

    def should_summarize(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if messages exceed the threshold and need summarization"""
        return self.count_messages_tokens(messages) > self.SUMMARY_THRESHOLD

    # ========== Structured Summary Generation ==========

    def extract_structured_info(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract structured information from messages for better summarization.
        Claude Code style: preserve file paths, code snippets, and decisions.
        """
        info = {
            "files_mentioned": set(),
            "code_snippets": [],
            "tools_used": [],
            "key_decisions": [],
            "user_goals": [],
            "errors_encountered": [],
        }

        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Handle string content
            if isinstance(content, str):
                self._extract_from_text(content, info, role)

            # Handle content blocks
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            self._extract_from_text(block.get("text", ""), info, role)
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tool_input = block.get("input", {})
                            info["tools_used"].append({
                                "name": tool_name,
                                "input_summary": self._summarize_tool_input(tool_name, tool_input)
                            })
                            # Extract file paths from tool inputs
                            self._extract_files_from_tool(tool_name, tool_input, info)

        # Convert sets to lists for JSON serialization
        info["files_mentioned"] = list(info["files_mentioned"])

        return info

    def _extract_from_text(self, text: str, info: Dict, role: str):
        """Extract information from text content"""
        import re

        # Extract file paths (Unix and Windows style)
        file_patterns = [
            r'(/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',  # Unix paths
            r'([a-zA-Z]:\\[a-zA-Z0-9_\-\\]+\.[a-zA-Z0-9]+)',  # Windows paths
            r'`([^`]+\.[a-zA-Z]{1,5})`',  # Backtick quoted files
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) < 200:  # Sanity check
                    info["files_mentioned"].add(match)

        # Extract code blocks (first 500 chars of each)
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', text, re.DOTALL)
        for code in code_blocks[:5]:  # Limit to 5 code blocks
            if len(code.strip()) > 20:
                info["code_snippets"].append(code.strip()[:500])

        # Extract user goals (from user messages)
        if role == "user":
            goal_keywords = ["帮我", "请", "我想", "需要", "help me", "please", "I want", "I need", "create", "创建", "实现", "implement"]
            for keyword in goal_keywords:
                if keyword in text.lower():
                    # Take the sentence containing the keyword
                    sentences = re.split(r'[。.!?！？\n]', text)
                    for sentence in sentences:
                        if keyword in sentence.lower() and len(sentence) > 10:
                            info["user_goals"].append(sentence.strip()[:200])
                            break
                    break

        # Extract errors
        error_patterns = [r'error[:\s]+(.*?)(?:\n|$)', r'错误[：:\s]+(.*?)(?:\n|$)', r'failed[:\s]+(.*?)(?:\n|$)']
        for pattern in error_patterns:
            errors = re.findall(pattern, text, re.IGNORECASE)
            for error in errors[:3]:
                if len(error.strip()) > 10:
                    info["errors_encountered"].append(error.strip()[:200])

    def _extract_files_from_tool(self, tool_name: str, tool_input: Dict, info: Dict):
        """Extract file paths from tool inputs"""
        file_keys = ["path", "file_path", "filename", "file", "directory", "dir"]
        for key in file_keys:
            if key in tool_input:
                path = tool_input[key]
                if isinstance(path, str) and len(path) < 500:
                    info["files_mentioned"].add(path)

    def _summarize_tool_input(self, tool_name: str, tool_input: Dict) -> str:
        """Create a brief summary of tool input"""
        if tool_name in ["read_file", "write_file", "edit"]:
            return tool_input.get("path", tool_input.get("file_path", ""))[:100]
        elif tool_name in ["bash", "execute_command"]:
            return tool_input.get("command", "")[:100]
        elif tool_name == "web_search":
            return tool_input.get("query", "")[:100]
        else:
            return str(tool_input)[:100]

    def prepare_structured_summary_prompt(self, messages: List[Dict[str, Any]], structured_info: Dict) -> str:
        """
        Prepare a Claude Code-style structured summary prompt.
        This produces a summary that preserves critical information.
        """
        # Build conversation text (condensed)
        conversation_parts = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if isinstance(content, str):
                text = content[:800]
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", "")[:400])
                        elif block.get("type") == "tool_use":
                            text_parts.append(f"[Tool: {block.get('name', '')}]")
                        elif block.get("type") == "tool_result":
                            text_parts.append("[Tool Result]")
                text = " ".join(text_parts)
            else:
                text = ""

            if text:
                conversation_parts.append(f"[{i+1}] {role.upper()}: {text}")

        conversation_text = "\n".join(conversation_parts[-50:])  # Last 50 messages

        # Format structured info
        files_list = "\n".join(f"  - {f}" for f in structured_info.get("files_mentioned", [])[:20])
        goals_list = "\n".join(f"  - {g}" for g in structured_info.get("user_goals", [])[:5])
        tools_list = "\n".join(f"  - {t['name']}: {t['input_summary']}" for t in structured_info.get("tools_used", [])[:10])

        return f"""请为以下对话生成一个**结构化摘要**，这个摘要将用于保持对话的连续性。

## 提取的关键信息

### 提到的文件路径
{files_list if files_list else "  (无)"}

### 用户目标
{goals_list if goals_list else "  (无)"}

### 使用的工具
{tools_list if tools_list else "  (无)"}

## 对话内容
{conversation_text}

---

请按以下格式生成摘要：

## 对话摘要

### 1. 项目背景
[描述用户正在做什么项目，使用什么技术栈]

### 2. 用户目标
[列出用户的主要目标和需求]

### 3. 已完成的工作
[列出已经完成的任务]

### 4. 关键文件
[列出重要的文件路径，保持完整路径]

### 5. 重要代码/命令
[如果有关键代码片段或命令，简要记录]

### 6. 技术决策
[记录做出的重要技术决策]

### 7. 待完成任务
[列出尚未完成的任务]

### 8. 注意事项
[任何需要注意的问题或限制]

请用简洁的中文生成摘要（控制在 1500 字以内）："""

    def prepare_summary_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Prepare summary prompt - now uses structured version"""
        structured_info = self.extract_structured_info(messages)
        return self.prepare_structured_summary_prompt(messages, structured_info)

    # ========== Message Splitting ==========

    def split_messages_for_summary(self, messages: List[Dict[str, Any]]) -> Tuple[List, List]:
        """
        Split messages into old (to summarize) and recent (to keep intact).
        Claude Code style: always keep recent messages for context continuity.
        """
        total_tokens = self.count_messages_tokens(messages)

        if total_tokens <= self.SUMMARY_THRESHOLD:
            return [], messages

        # Always keep at least RECENT_MESSAGES_TO_KEEP messages
        min_keep = min(self.RECENT_MESSAGES_TO_KEEP, len(messages))

        # Calculate how many tokens to keep in recent messages
        recent_tokens = 0
        split_index = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = self.count_message_tokens(messages[i])
            if recent_tokens + msg_tokens > self.TARGET_AFTER_SUMMARY:
                split_index = i + 1
                break
            recent_tokens += msg_tokens

        # Ensure we keep minimum messages
        split_index = min(split_index, len(messages) - min_keep)
        split_index = max(split_index, 0)

        # Make sure we split at user message boundary for coherence
        while split_index > 0 and messages[split_index].get("role") != "user":
            split_index -= 1

        old_messages = messages[:split_index]
        recent_messages = messages[split_index:]

        return old_messages, recent_messages

    def create_summary_messages(self, summary: str, recent_messages: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Create new message list with summary as context"""
        result = [
            {
                "role": "user",
                "content": f"""[系统：对话历史摘要]

以下是之前对话的摘要，请基于此继续我们的讨论：

{summary}

---
[摘要结束，以下是最近的对话]"""
            },
            {
                "role": "assistant",
                "content": "我已了解之前的对话背景。让我们继续。"
            }
        ]

        if recent_messages:
            result.extend(recent_messages)

        return result

    # ========== Session Persistence (JSONL) ==========

    def get_session_path(self, session_id: str) -> str:
        """Get the JSONL file path for a session"""
        return os.path.join(self.SESSIONS_DIR, f"{session_id}.jsonl")

    def get_session_hash(self, working_dir: str) -> str:
        """Generate a hash for the working directory (like Claude Code project hash)"""
        return hashlib.md5(working_dir.encode()).hexdigest()[:12]

    def save_message(self, session_id: str, message: Dict[str, Any]):
        """Append a single message to the session JSONL file"""
        session_path = self.get_session_path(session_id)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        with open(session_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save_messages(self, session_id: str, messages: List[Dict[str, Any]]):
        """Save multiple messages to the session JSONL file"""
        session_path = self.get_session_path(session_id)
        with open(session_path, "a", encoding="utf-8") as f:
            for message in messages:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "message": message
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Load all messages from a session JSONL file"""
        session_path = self.get_session_path(session_id)
        messages = []

        if os.path.exists(session_path):
            with open(session_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            messages.append(entry.get("message", entry))
                        except json.JSONDecodeError:
                            continue

        return messages

    def save_summary_event(self, session_id: str, summary: str, old_count: int, new_count: int):
        """Save a summarization event to the session log"""
        session_path = self.get_session_path(session_id)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "context_summarized",
            "summary": summary,
            "messages_summarized": old_count,
            "messages_after": new_count
        }
        with open(session_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list_sessions(self, working_dir: str = None) -> List[Dict[str, Any]]:
        """List all saved sessions, optionally filtered by working directory"""
        sessions = []
        project_hash = self.get_session_hash(working_dir) if working_dir else None

        for filename in os.listdir(self.SESSIONS_DIR):
            if filename.endswith(".jsonl"):
                session_id = filename[:-6]

                # Filter by project hash if specified
                if project_hash and not session_id.startswith(project_hash):
                    continue

                session_path = os.path.join(self.SESSIONS_DIR, filename)
                stat = os.stat(session_path)

                sessions.append({
                    "session_id": session_id,
                    "file": filename,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        return sorted(sessions, key=lambda x: x["modified"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session file"""
        session_path = self.get_session_path(session_id)
        if os.path.exists(session_path):
            os.remove(session_path)
            return True
        return False

    # ========== Auto-Summarization ==========

    def check_and_prepare_auto_summary(self, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Check if auto-summarization is needed and prepare the summary request.
        Returns None if no summarization needed, otherwise returns summary request data.
        """
        if not self.should_summarize(messages):
            return None

        old_messages, recent_messages = self.split_messages_for_summary(messages)

        if not old_messages:
            return None

        structured_info = self.extract_structured_info(old_messages)
        summary_prompt = self.prepare_structured_summary_prompt(old_messages, structured_info)

        return {
            "needs_summary": True,
            "summary_prompt": summary_prompt,
            "old_messages_count": len(old_messages),
            "recent_messages": recent_messages,
            "structured_info": structured_info
        }


# Singleton instance
_context_manager = None


def get_context_manager() -> ContextManager:
    """Get the singleton context manager instance"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


# Convenience functions
def count_tokens(messages: List[Dict[str, Any]]) -> int:
    """Count tokens in messages"""
    return get_context_manager().count_messages_tokens(messages)


def get_stats(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get context statistics"""
    return get_context_manager().get_context_stats(messages)


def should_summarize(messages: List[Dict[str, Any]]) -> bool:
    """Check if summarization is needed"""
    return get_context_manager().should_summarize(messages)


def save_message(session_id: str, message: Dict[str, Any]):
    """Save a message to session"""
    return get_context_manager().save_message(session_id, message)


def load_session(session_id: str) -> List[Dict[str, Any]]:
    """Load messages from session"""
    return get_context_manager().load_session(session_id)
