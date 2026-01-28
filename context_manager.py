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

# Optional memory sync import
try:
    from memory_sync import get_sync_manager, init_memory_sync
    HAS_MEMORY_SYNC = True
except ImportError:
    HAS_MEMORY_SYNC = False
    get_sync_manager = lambda: None
    init_memory_sync = lambda *args, **kwargs: False


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
    # Structure: sessions/{session_id}/{session_id}.jsonl
    #            sessions/{session_id}/tool-results/toolu_bdrk_{id}.txt      (Bedrock tools)
    #            sessions/{session_id}/tool-results/mcp-{server}-{tool}-{ts}.txt  (MCP tools)
    SESSIONS_DIR = os.path.expanduser("~/.springo/sessions")

    # Max tool result size before saving to file (30KB)
    MAX_INLINE_OUTPUT_SIZE = 30 * 1024

    def __init__(self):
        if HAS_TIKTOKEN:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self._encoder = None

        # Ensure base directory exists
        Path(self.SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

        # In-memory context state per session
        self._session_contexts: Dict[str, Dict] = {}

        # OPTIMIZATION 2: Token count cache (message hash -> token count)
        self._token_cache: Dict[str, int] = {}
        self._token_cache_max_size = 1000  # Limit cache size

        # Initialize memory sync (async upload to AgentCore Memory)
        self._memory_sync_enabled = False
        if HAS_MEMORY_SYNC:
            try:
                self._memory_sync_enabled = init_memory_sync()
            except Exception as e:
                print(f"[ContextManager] Memory sync init failed: {e}")

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

    def get_session_dir(self, session_id: str) -> str:
        """Get the directory path for a session"""
        return os.path.join(self.SESSIONS_DIR, session_id)

    def get_session_path(self, session_id: str) -> str:
        """Get the JSONL file path for a session: sessions/{session_id}/{session_id}.jsonl"""
        return os.path.join(self.get_session_dir(session_id), f"{session_id}.jsonl")

    def get_session_hash(self, working_dir: str) -> str:
        """Generate a hash for the working directory (like Claude Code project hash)"""
        return hashlib.md5(working_dir.encode()).hexdigest()[:12]

    def save_message(self, session_id: str, message: Dict[str, Any]):
        """Append a single message to the session JSONL file"""
        session_dir = self.get_session_dir(session_id)
        Path(session_dir).mkdir(parents=True, exist_ok=True)
        session_path = self.get_session_path(session_id)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        with open(session_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Async upload to AgentCore Memory (non-blocking)
        if self._memory_sync_enabled:
            sync_mgr = get_sync_manager()
            if sync_mgr:
                actor = "assistant" if message.get("role") == "assistant" else "user"
                sync_mgr.queue_message(session_id, message, actor)

    def save_messages(self, session_id: str, messages: List[Dict[str, Any]]):
        """Save multiple messages to the session JSONL file (append mode)"""
        session_dir = self.get_session_dir(session_id)
        Path(session_dir).mkdir(parents=True, exist_ok=True)
        session_path = self.get_session_path(session_id)
        with open(session_path, "a", encoding="utf-8") as f:
            for message in messages:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "message": message
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Async upload to AgentCore Memory (non-blocking)
        if self._memory_sync_enabled:
            sync_mgr = get_sync_manager()
            if sync_mgr:
                sync_mgr.queue_conversation(session_id, messages)

    def save_session_complete(self, session_id: str, messages: List[Dict[str, Any]], metadata: Dict[str, Any] = None):
        """Save complete session to JSONL file (overwrite mode, like Claude Code)

        Format:
        - First line: session metadata (title, workingDir, timestamps)
        - Following lines: each message with timestamp
        """
        session_dir = self.get_session_dir(session_id)
        Path(session_dir).mkdir(parents=True, exist_ok=True)
        session_path = self.get_session_path(session_id)

        # Write complete session (overwrite)
        with open(session_path, "w", encoding="utf-8") as f:
            # Write session header/metadata
            header = {
                "type": "session_start",
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            f.write(json.dumps(header, ensure_ascii=False) + "\n")

            # Write each message
            for i, message in enumerate(messages):
                entry = {
                    "type": "message",
                    "index": i,
                    "timestamp": message.get("timestamp") or datetime.now().isoformat(),
                    "message": message
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Load all messages from a session JSONL file

        Format: sessions/{session_id}/{session_id}.jsonl
        """
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
        """List all saved sessions, optionally filtered by working directory

        Format: sessions/{session_id}/{session_id}.jsonl
        """
        sessions = []
        project_hash = self.get_session_hash(working_dir) if working_dir else None

        for entry in os.listdir(self.SESSIONS_DIR):
            entry_path = os.path.join(self.SESSIONS_DIR, entry)

            # Only support directory format: sessions/{session_id}/
            if not os.path.isdir(entry_path):
                continue

            session_id = entry
            session_path = os.path.join(entry_path, f"{session_id}.jsonl")
            if not os.path.exists(session_path):
                continue

            # Filter by project hash if specified
            if project_hash and not session_id.startswith(project_hash):
                continue

            stat = os.stat(session_path)

            # Read metadata from first line of JSONL file
            metadata = {}
            try:
                with open(session_path, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line:
                        first_entry = json.loads(first_line)
                        if first_entry.get('type') == 'session_start':
                            metadata = first_entry.get('metadata', {})
            except Exception:
                pass  # Ignore errors, use empty metadata

            sessions.append({
                "session_id": session_id,
                "file": f"{session_id}/{session_id}.jsonl",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "metadata": metadata
            })

        return sorted(sessions, key=lambda x: x["modified"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session directory

        Format: sessions/{session_id}/
        """
        import shutil

        session_dir = self.get_session_dir(session_id)
        if os.path.isdir(session_dir):
            shutil.rmtree(session_dir)
            return True

        return False

    # ========== Tool Result Management (like Claude Code) ==========

    def get_tool_results_dir(self, session_id: str) -> str:
        """Get the tool-results directory for a session: sessions/{session_id}/tool-results/"""
        return os.path.join(self.get_session_dir(session_id), "tool-results")

    def get_tool_result_path(self, session_id: str, tool_use_id: str, tool_name: str = None) -> str:
        """
        Get file path for storing large tool result.

        Naming convention:
        - Bedrock tools: toolu_bdrk_{id}.txt
        - MCP tools: mcp-{server}-{tool}-{timestamp}.txt

        Args:
            session_id: Session ID
            tool_use_id: Tool use ID (e.g., "toolu_bdrk_01Abc123")
            tool_name: Tool name (e.g., "read_file" or "web-search__brave_web_search")
        """
        tool_results_dir = self.get_tool_results_dir(session_id)
        Path(tool_results_dir).mkdir(parents=True, exist_ok=True)

        # Generate filename based on tool type
        if tool_name and '__' in tool_name:
            # MCP tool: mcp-{server}-{tool}-{timestamp}.txt
            parts = tool_name.split('__', 1)
            server = parts[0]
            tool = parts[1] if len(parts) > 1 else 'unknown'
            # Use last 8 chars of tool_use_id as timestamp substitute
            ts = tool_use_id[-8:] if len(tool_use_id) >= 8 else tool_use_id
            filename = f"mcp-{server}-{tool}-{ts}.txt"
        elif tool_use_id.startswith('toolu_bdrk_'):
            # Bedrock tool: toolu_bdrk_{id}.txt
            filename = f"{tool_use_id}.txt"
        else:
            # Fallback: use tool_use_id with .txt extension
            filename = f"{tool_use_id}.txt"

        return os.path.join(tool_results_dir, filename)

    def find_tool_result_file(self, session_id: str, tool_use_id: str) -> Optional[str]:
        """
        Find tool result file by tool_use_id.
        Searches tool-results directory for files containing the tool_use_id.

        Returns:
            File path if found, None otherwise
        """
        tool_results_dir = self.get_tool_results_dir(session_id)
        if not os.path.exists(tool_results_dir):
            return None

        # For Bedrock tools: toolu_bdrk_{id}.txt - exact match
        if tool_use_id.startswith('toolu_bdrk_'):
            exact_path = os.path.join(tool_results_dir, f"{tool_use_id}.txt")
            if os.path.exists(exact_path):
                return exact_path

        # For MCP tools or fallback: search for files containing tool_use_id or its suffix
        tool_id_suffix = tool_use_id[-8:] if len(tool_use_id) >= 8 else tool_use_id
        for filename in os.listdir(tool_results_dir):
            if tool_id_suffix in filename or tool_use_id in filename:
                return os.path.join(tool_results_dir, filename)

        return None

    def save_tool_result(self, session_id: str, tool_use_id: str, result: str, tool_name: str = None) -> Dict[str, Any]:
        """
        Save large tool result to file and return reference.
        Like Claude Code's task output handling.

        Args:
            session_id: The session ID
            tool_use_id: The tool use ID (unique identifier)
            result: The tool result content
            tool_name: Optional tool name for metadata

        Returns:
            Dict with result info:
            - If result is small: {"inline": True, "content": result}
            - If result is large: {"inline": False, "file_path": path, "size": size, "preview": first_500_chars}
        """
        result_size = len(result.encode('utf-8'))

        # If result is small enough, return inline
        if result_size <= self.MAX_INLINE_OUTPUT_SIZE:
            return {
                "inline": True,
                "content": result,
                "size": result_size
            }

        # Save large result to file
        result_path = self.get_tool_result_path(session_id, tool_use_id, tool_name)

        with open(result_path, 'w', encoding='utf-8') as f:
            # Write metadata header
            metadata = {
                "type": "tool_result",
                "session_id": session_id,
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "timestamp": datetime.now().isoformat(),
                "size": result_size
            }
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            f.write("---\n")
            f.write(result)

        # Return reference with preview
        preview = result[:500] + "..." if len(result) > 500 else result

        return {
            "inline": False,
            "file_path": result_path,
            "size": result_size,
            "preview": preview,
            "truncated_message": f"[Result saved to file: {result_path}] ({result_size:,} bytes)"
        }

    def load_tool_result(self, file_path: str) -> str:
        """Load tool result from file"""
        if not os.path.exists(file_path):
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Skip metadata header if present
            if content.startswith('{'):
                lines = content.split('\n', 2)
                if len(lines) > 2 and lines[1] == '---':
                    return lines[2]
            return content

    def list_tool_results(self, session_id: str) -> List[Dict[str, Any]]:
        """List all tool results for a session"""
        tool_results_dir = self.get_tool_results_dir(session_id)
        if not os.path.exists(tool_results_dir):
            return []

        results = []
        for filename in os.listdir(tool_results_dir):
            if filename.endswith('.output'):
                file_path = os.path.join(tool_results_dir, filename)
                stat = os.stat(file_path)
                results.append({
                    "tool_use_id": filename[:-7],  # Remove .output
                    "file_path": file_path,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        return sorted(results, key=lambda x: x["modified"], reverse=True)

    def cleanup_old_tool_results(self, max_age_days: int = 7) -> int:
        """Clean up tool results in sessions older than max_age_days"""
        import shutil
        cleaned = 0
        now = datetime.now()
        max_age = max_age_days * 24 * 60 * 60  # Convert to seconds

        for session_dir_name in os.listdir(self.SESSIONS_DIR):
            session_dir = os.path.join(self.SESSIONS_DIR, session_dir_name)
            if os.path.isdir(session_dir):
                tool_results_dir = os.path.join(session_dir, "tool-results")
                if os.path.isdir(tool_results_dir):
                    dir_mtime = os.path.getmtime(tool_results_dir)
                    if (now.timestamp() - dir_mtime) > max_age:
                        shutil.rmtree(tool_results_dir)
                        cleaned += 1

        return cleaned

    # ========== Auto-Summarization ==========

    def summarize_messages(self, messages: List[Dict[str, Any]], model: str = "claude-haiku-4-5-20251001") -> List[Dict[str, Any]]:
        """
        Perform automatic summarization of messages using the specified model.
        Returns a new message list with summary + recent messages.

        Args:
            messages: The full message list to summarize
            model: The model to use for summarization (default: Haiku 4.5 for cost efficiency)

        Returns:
            New message list with summary replacing old messages
        """
        import boto3
        import json
        from botocore.config import Config

        # Model mapping for Bedrock
        model_mapping = {
            "claude-haiku-4-5-20251001": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "claude-3-5-haiku-20241022": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
            "claude-3-5-sonnet-20241022": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "claude-sonnet-4-20250514": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        }

        bedrock_model_id = model_mapping.get(model, model_mapping["claude-haiku-4-5-20251001"])

        # Split messages
        old_messages, recent_messages = self.split_messages_for_summary(messages)

        if not old_messages:
            return messages  # Nothing to summarize

        # Prepare summary prompt
        summary_prompt = self.prepare_summary_prompt(old_messages)

        # Call Bedrock for summarization
        try:
            from auth.config_manager import AuthConfigManager
            auth_manager = AuthConfigManager()
            bedrock_client = auth_manager.get_bedrock_client()
        except Exception:
            config = Config(
                region_name="us-east-1",
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
            bedrock_client = boto3.client('bedrock-runtime', config=config)

        try:
            response = bedrock_client.invoke_model(
                modelId=bedrock_model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": summary_prompt}],
                    "temperature": 0.3  # Lower temperature for more consistent summaries
                }),
                contentType="application/json",
                accept="application/json"
            )

            result = json.loads(response['body'].read())
            summary_text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    summary_text += block.get("text", "")

            # Create new message list with summary
            return self.create_summary_messages(summary_text, recent_messages)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Summarization failed: {e}")
            # Return original messages if summarization fails
            return messages

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
