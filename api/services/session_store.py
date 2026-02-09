"""
Session Store Service for FastAPI
会话存储服务 - 集成 Memory Sync
"""
import os
import json
import hashlib
import logging
import threading
from typing import Any, Dict, List, Optional
from pathlib import Path
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
        # Memory sync lazy init
        self._memory_sync_enabled = False
        self._memory_sync_init_started = False
        self._memory_sync_lock = threading.Lock()

    def _ensure_dir_exists(self):
        """确保会话目录存在"""
        os.makedirs(self.sessions_dir, exist_ok=True)

    def _ensure_memory_sync_initialized(self):
        """后台线程懒初始化 memory sync（非阻塞）"""
        if self._memory_sync_enabled or self._memory_sync_init_started:
            return
        with self._memory_sync_lock:
            if self._memory_sync_init_started:
                return
            self._memory_sync_init_started = True
            try:
                from .memory_sync import get_sync_manager
                mgr = get_sync_manager()
                if mgr and mgr._initialized:
                    self._memory_sync_enabled = True
                    logger.debug("SessionStore: memory sync integration enabled")
            except Exception as e:
                logger.debug(f"SessionStore: memory sync not available: {e}")

    def _get_sync_manager(self):
        """获取 memory sync manager（懒导入避免循环依赖）"""
        self._ensure_memory_sync_initialized()
        if not self._memory_sync_enabled:
            return None
        try:
            from .memory_sync import get_sync_manager
            return get_sync_manager()
        except Exception:
            return None

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
                    "working_dir": metadata.get("working_dir", ""),
                    "title": metadata.get("title", ""),
                    "message_count": metadata.get("message_count", 0)
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

            # Trigger memory sync
            sync_mgr = self._get_sync_manager()
            if sync_mgr:
                actor = "assistant" if message.get("role") == "assistant" else "user"
                sync_mgr.queue_message(session_id, message, actor)

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

            # Trigger memory sync (batch)
            sync_mgr = self._get_sync_manager()
            queued = 0
            if sync_mgr:
                queued = sync_mgr.queue_conversation(session_id, messages)

            return {
                "success": True,
                "session_id": session_id,
                "message_count": len(messages),
                "synced": queued,
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

            # 重置 sync state
            sync_state_file = os.path.join(session_dir, ".sync_state.json")
            try:
                reset_state = {
                    "last_synced_index": -1,
                    "last_sync_time": datetime.now().isoformat(),
                    "total_synced": 0,
                    "reset_reason": "session_complete_rewrite",
                }
                with open(sync_state_file, 'w') as f:
                    json.dump(reset_state, ensure_ascii=False, fp=f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to reset sync state for {session_id}: {e}")

            # 重新队列所有消息到 memory sync
            sync_mgr = self._get_sync_manager()
            queued = 0
            if sync_mgr:
                queued = sync_mgr.queue_conversation(session_id, messages)

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
                "synced": queued,
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
