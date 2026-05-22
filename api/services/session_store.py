"""
Session Store Service for FastAPI
会话存储服务 - 集成 Memory Sync
"""
import os
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)


MAX_SESSION_FILE_SIZE = 10 * 1024 * 1024  # 10MB warning threshold
MAX_SESSION_FILE_HARD_LIMIT = 50 * 1024 * 1024  # 50MB hard limit


class SessionStore:
    """会话存储管理器"""

    def __init__(self):
        """初始化会话存储"""
        self.sessions_dir = settings.session_storage_path
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        """确保会话目录存在"""
        os.makedirs(self.sessions_dir, exist_ok=True)

    def get_session_dir(self, session_id: str) -> str:
        """获取会话目录路径"""
        return os.path.join(self.sessions_dir, session_id)

    def get_session_path(self, session_id: str) -> str:
        """获取会话 JSONL 文件路径"""
        return os.path.join(self.get_session_dir(session_id), f"{session_id}.jsonl")

    def get_session_hash(self, working_dir: str) -> str:
        """根据工作目录生成会话哈希"""
        return hashlib.md5(working_dir.encode()).hexdigest()[:12]

    def list_sessions(self, working_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Args:
            working_dir: 可选的工作目录过滤

        Returns:
            会话列表
        """
        sessions = []

        if not os.path.exists(self.sessions_dir):
            return sessions

        for session_id in os.listdir(self.sessions_dir):
            session_dir = self.get_session_dir(session_id)
            session_file = self.get_session_path(session_id)

            if not os.path.isdir(session_dir) or not os.path.exists(session_file):
                continue

            try:
                # 读取会话元数据
                stat = os.stat(session_file)

                # 读取第一条消息获取元数据
                metadata = {}
                with open(session_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line:
                        first_entry = json.loads(first_line)
                        if first_entry.get("type") == "metadata":
                            metadata = first_entry

                session_info = {
                    "session_id": session_id,
                    "created": metadata.get("created_at", stat.st_ctime),
                    "modified": stat.st_mtime * 1000,  # Convert to milliseconds for JS Date compatibility
                    "working_dir": metadata.get("working_dir") or metadata.get("workingDir", ""),
                    "title": metadata.get("title", ""),
                    "message_count": metadata.get("message_count", 0),
                    "session_mode": metadata.get("session_mode", "general"),
                    "pinned": bool(metadata.get("pinned", False)),
                    "pinned_at": metadata.get("pinnedAt") or metadata.get("pinned_at"),
                    "folder_id": metadata.get("folder_id") or metadata.get("folderId"),
                }

                # 过滤工作目录
                if working_dir and session_info["working_dir"] != working_dir:
                    continue

                sessions.append(session_info)

            except Exception as e:
                logger.warning(f"Failed to read session {session_id}: {e}")
                continue

        # 按修改时间排序
        return sorted(sessions, key=lambda x: x["modified"], reverse=True)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话详情 - 兼容两种 JSONL 条目格式

        格式 1: {timestamp, message} - 新格式 (save_message/save_messages)
        格式 2: {type, index, timestamp, message} - 扩展格式
        格式 3: {role, content, ...} - 直接消息格式 (save_session)

        Args:
            session_id: 会话 ID

        Returns:
            会话详情，包含消息列表
        """
        session_file = self.get_session_path(session_id)

        if not os.path.exists(session_file):
            return {"error": f"Session not found: {session_id}"}

        messages = []
        metadata = {}

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    entry = json.loads(line)
                    entry_type = entry.get("type", "")

                    if entry_type == "metadata":
                        metadata = entry
                    elif entry_type in ["user", "assistant", "message"]:
                        # 格式 3: 直接消息格式
                        messages.append(entry)
                    elif "message" in entry and isinstance(entry["message"], dict):
                        # 格式 1/2: {timestamp, message} or {type, index, timestamp, message}
                        messages.append(entry["message"])
                    elif "role" in entry and entry.get("type") != "metadata":
                        # 含 role 的直接消息
                        messages.append(entry)

            return {
                "session_id": session_id,
                "messages": messages,
                "metadata": metadata,
                "message_count": len(messages)
            }

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return {"error": str(e)}

    def get_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Read just the first-line metadata entry from a session JSONL file.

        Returns the metadata dict, or None if the session doesn't exist.
        """
        session_file = self.get_session_path(session_id)
        if not os.path.exists(session_file):
            return None
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            if first_line:
                entry = json.loads(first_line)
                if entry.get("type") == "metadata":
                    return entry
        except Exception as e:
            logger.warning(f"Failed to read metadata for {session_id}: {e}")
        return None

    def append_session_messages(
        self,
        session_id: str,
        new_messages: List[Dict[str, Any]],
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Incrementally append new messages to session JSONL and sync only the delta.

        Unlike save_session_complete which rewrites the entire file, this method:
        - Appends only new messages (open mode 'a')
        - Only queues new messages to memory sync (not the full history)
        - Optionally updates metadata (first-line) without touching messages

        Args:
            session_id: Session ID
            new_messages: Only the new messages to append
            metadata_updates: Optional metadata fields to update (title, tokens, etc.)

        Returns:
            Dict with success status and counts
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        if not os.path.exists(session_file):
            # File doesn't exist yet — fall back to full write
            return self.save_session_complete(session_id, new_messages, metadata=metadata_updates)

        try:
            # Append new messages
            if new_messages:
                with open(session_file, 'a', encoding='utf-8') as f:
                    for msg in new_messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            # Update metadata if needed (rewrite first line only)
            if metadata_updates:
                self.update_metadata(session_id, metadata_updates)

            # Plan B: per-message sync removed — archives handle AgentCore sync
            return {
                "success": True,
                "session_id": session_id,
                "appended": len(new_messages),
            }

        except Exception as e:
            logger.error(f"Failed to append messages to {session_id}: {e}")
            return {"error": str(e)}

    def update_metadata(
        self,
        session_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        只更新 JSONL 第一行的 metadata，不动消息内容。
        用于重命名等只修改元数据的场景，避免消息丢失。

        Args:
            session_id: 会话 ID
            metadata_updates: 要合并的元数据字段

        Returns:
            更新结果
        """
        session_file = self.get_session_path(session_id)

        if not os.path.exists(session_file):
            return {"error": f"Session not found: {session_id}"}

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                return {"error": f"Session file is empty: {session_id}"}

            # Parse first line as metadata
            first_entry = json.loads(lines[0].strip())
            if first_entry.get("type") == "metadata":
                first_entry.update(metadata_updates)
                lines[0] = json.dumps(first_entry, ensure_ascii=False) + "\n"
            else:
                # No metadata line — prepend one
                meta = {"type": "metadata", "session_id": session_id}
                meta.update(metadata_updates)
                lines.insert(0, json.dumps(meta, ensure_ascii=False) + "\n")

            with open(session_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return {"success": True, "session_id": session_id}

        except Exception as e:
            logger.error(f"Failed to update metadata for {session_id}: {e}")
            return {"error": str(e)}

    def save_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        保存会话（完整覆盖模式 - 不触发 sync 重置）

        Args:
            session_id: 会话 ID
            messages: 消息列表
            metadata: 可选元数据

        Returns:
            保存结果
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        try:
            os.makedirs(session_dir, exist_ok=True)

            with open(session_file, 'w', encoding='utf-8') as f:
                # 写入元数据
                meta = metadata or {}
                meta.update({
                    "type": "metadata",
                    "session_id": session_id,
                    "created_at": meta.get("created_at", datetime.now().isoformat()),
                    "message_count": len(messages)
                })
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

                # 写入消息
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            # Check file size
            file_size = os.path.getsize(session_file)
            if file_size > MAX_SESSION_FILE_HARD_LIMIT:
                logger.error(f"Session {session_id} file exceeds hard limit: {file_size:,} bytes")
            elif file_size > MAX_SESSION_FILE_SIZE:
                logger.warning(f"Session {session_id} file is large: {file_size:,} bytes")

            return {
                "success": True,
                "session_id": session_id,
                "message_count": len(messages),
                "file_size": file_size
            }

        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            return {"error": str(e)}

    def save_message(self, session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        追加单条消息到 JSONL，触发 memory sync queue

        Args:
            session_id: 会话 ID
            message: 消息内容

        Returns:
            保存结果
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        try:
            os.makedirs(session_dir, exist_ok=True)

            entry = {
                "timestamp": datetime.now().isoformat(),
                "message": message,
            }

            with open(session_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # Plan B: per-message sync removed — archives handle AgentCore sync
            return {"success": True, "session_id": session_id}

        except Exception as e:
            logger.error(f"Failed to save message to {session_id}: {e}")
            return {"error": str(e)}

    def save_messages(self, session_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量追加消息，调用 sync_mgr.queue_conversation()

        Args:
            session_id: 会话 ID
            messages: 消息列表

        Returns:
            保存结果
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        try:
            os.makedirs(session_dir, exist_ok=True)

            with open(session_file, 'a', encoding='utf-8') as f:
                for msg in messages:
                    entry = {
                        "timestamp": datetime.now().isoformat(),
                        "message": msg,
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # Plan B: per-message sync removed — archives handle AgentCore sync
            return {
                "success": True,
                "session_id": session_id,
                "message_count": len(messages),
            }

        except Exception as e:
            logger.error(f"Failed to save messages to {session_id}: {e}")
            return {"error": str(e)}

    def save_session_complete(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        完整覆写 JSONL，重置 .sync_state.json，重新队列所有消息到 memory sync

        用于 context compaction 后需要完整重写会话的场景。

        Args:
            session_id: 会话 ID
            messages: 新的完整消息列表
            metadata: 可选元数据

        Returns:
            保存结果
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        try:
            os.makedirs(session_dir, exist_ok=True)

            # 写入完整会话
            with open(session_file, 'w', encoding='utf-8') as f:
                meta = metadata or {}
                meta.update({
                    "type": "metadata",
                    "session_id": session_id,
                    "created_at": meta.get("created_at", datetime.now().isoformat()),
                    "message_count": len(messages),
                    "compacted": True,
                    "compacted_at": datetime.now().isoformat(),
                })
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            # Plan B: per-message sync removed — archives handle AgentCore sync

            # Reset archive watermark — compaction rewrites the JSONL with fewer
            # messages, which invalidates the old message index watermark.
            try:
                from .memory_archiver import _save_archive_watermark
                _save_archive_watermark(session_id, -1)
            except Exception:
                pass

            file_size = os.path.getsize(session_file)
            if file_size > MAX_SESSION_FILE_HARD_LIMIT:
                logger.error(f"Session {session_id} file exceeds hard limit: {file_size:,} bytes")
            elif file_size > MAX_SESSION_FILE_SIZE:
                logger.warning(f"Session {session_id} file is large: {file_size:,} bytes")

            return {
                "success": True,
                "session_id": session_id,
                "message_count": len(messages),
                "file_size": file_size,
            }

        except Exception as e:
            logger.error(f"Failed to save session complete {session_id}: {e}")
            return {"error": str(e)}

    def save_summary_event(
        self,
        session_id: str,
        summary: str,
        old_count: int,
        new_count: int,
    ) -> None:
        """记录摘要事件"""
        try:
            from .context_manager import save_summary_event as _save_event
            _save_event(session_id, summary, old_count, new_count)
        except Exception as e:
            logger.warning(f"Failed to save summary event: {e}")

    def append_message(self, session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        追加消息到会话（旧接口，不触发 sync）

        Args:
            session_id: 会话 ID
            message: 消息内容

        Returns:
            追加结果
        """
        session_dir = self.get_session_dir(session_id)
        session_file = self.get_session_path(session_id)

        try:
            os.makedirs(session_dir, exist_ok=True)

            with open(session_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

            return {"success": True, "session_id": session_id}

        except Exception as e:
            logger.error(f"Failed to append message to {session_id}: {e}")
            return {"error": str(e)}

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            删除结果
        """
        session_dir = self.get_session_dir(session_id)

        if not os.path.exists(session_dir):
            return {"error": f"Session not found: {session_id}"}

        try:
            import shutil
            shutil.rmtree(session_dir)
            return {"success": True, "session_id": session_id}
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return {"error": str(e)}

    def get_session_by_number(self, number: int, working_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        通过编号获取会话

        Args:
            number: 会话编号
            working_dir: 可选工作目录过滤

        Returns:
            会话详情
        """
        sessions = self.list_sessions(working_dir)
        total = len(sessions)

        # 编号从 1 开始，最新的是最大号
        index = total - number

        if index < 0 or index >= total:
            return {"error": f"Session #{number} not found"}

        session = sessions[index]
        return self.get_session(session["session_id"])


# 全局单例
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取会话存储单例"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
