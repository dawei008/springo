"""
AgentCore Memory Sync Module for Springo FastAPI

异步将本地会话同步到 AgentCore Memory：
- 本地优先：消息先存本地 JSONL
- 异步上传：后台线程批量上传
- 失败重试：自动重试，记录状态
- S3 集成：上传前处理消息中的图片等资源
"""

import os
import json
import time
import hashlib
import logging
import threading
from queue import Queue, Empty
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.springo")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SESSIONS_DIR = os.path.join(CONFIG_DIR, "sessions")
SYNC_STATE_FILE = ".sync_state.json"

DEFAULT_MEMORY_CONFIG = {
    "memory_id": "",
    "memory_region": "us-west-2",
    "memory_enabled": True,
    "batch_size": 5,
    "batch_timeout": 30,
    "max_retries": 3,
    "retry_delay": 5,
    "sync_check_delay": 2,
    # Local memory files (memory/*.md)
    "local_memory_enabled": True,
    "workspace_path": "~/.springo/workspace",
    "retention_days": 7,
    "auto_archive_on_reset": True,
    # File sync worker (Plan B) — syncs memory files to AgentCore
    "file_sync_interval": 86400,     # 24h between scheduled scans
    "file_sync_initial_delay": 60,   # 1 min delay before first scan
}

# Module-level config constants (loaded once)
_config = None

def _get_config() -> Dict[str, Any]:
    global _config
    if _config is None:
        _config = load_memory_config()
    return _config

def _get_config_value(key: str, default=None):
    return _get_config().get(key, default)

# Lazy S3 manager
_s3_sync_module = None

def _get_s3_manager():
    """懒加载 S3 manager"""
    global _s3_sync_module
    try:
        if _s3_sync_module is None:
            from . import s3_sync as _mod
            _s3_sync_module = _mod
        return _s3_sync_module.get_s3_manager()
    except Exception:
        return None


def load_memory_config() -> Dict[str, Any]:
    """加载 Memory 配置（环境变量 > 配置文件 > 默认值）"""
    config = DEFAULT_MEMORY_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config.get("memory", {}))
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
    env_mappings = {
        "SPRINGO_MEMORY_ID": ("memory_id", str),
        "SPRINGO_MEMORY_REGION": ("memory_region", str),
        "SPRINGO_MEMORY_ENABLED": ("memory_enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "SPRINGO_MEMORY_BATCH_SIZE": ("batch_size", int),
        "SPRINGO_MEMORY_BATCH_TIMEOUT": ("batch_timeout", int),
    }
    for env_key, (config_key, conv) in env_mappings.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            try:
                config[config_key] = conv(env_val)
            except (ValueError, TypeError):
                pass
    return config


def save_memory_config(memory_config: Dict[str, Any]) -> bool:
    """保存 Memory 配置（合并）"""
    try:
        file_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
        existing = file_config.get("memory", {})
        existing.update({
            "memory_id": memory_config.get("memory_id", existing.get("memory_id", "")),
            "memory_region": memory_config.get("memory_region", existing.get("memory_region", "us-west-2")),
            "memory_enabled": memory_config.get("memory_enabled", existing.get("memory_enabled", True)),
            "memory_backend": memory_config.get("memory_backend", existing.get("memory_backend", "agentcore")),
        })
        file_config["memory"] = existing
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(file_config, ensure_ascii=False, fp=f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save memory config: {e}")
        return False


class MemorySyncManager:
    """管理会话到 AgentCore Memory 的异步同步"""

    def __init__(self, memory_id: str, region: str):
        self.memory_id = memory_id
        self.region = region
        self.upload_queue: Queue = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.sync_check_thread: Optional[threading.Thread] = None
        self.file_sync_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._batch: List[Dict] = []
        self._batch_start_time: float = 0
        self._initialized = False
        self._memory_client = None
        self._sync_check_done = False
        self._config = load_memory_config()

    def initialize(self) -> bool:
        try:
            import boto3
            self._memory_client = boto3.client("bedrock-agentcore", region_name=self.region)
            self._initialized = True
            logger.info(f"MemorySyncManager initialized: {self.memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MemorySyncManager: {e}")
            return False

    def start(self) -> bool:
        if not self._initialized:
            if not self.initialize():
                return False
        if self.worker_thread and self.worker_thread.is_alive():
            return True
        self._stop_event.clear()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        # Plan B: disable startup full-rescan — archives handle sync now.
        # _sync_check_worker scans ALL sessions on startup and re-queues everything,
        # which caused repeated crashes from upload flooding.
        self._sync_check_done = True
        # Start file sync worker (periodic checkpoint-based sync of memory/*.md)
        self.file_sync_thread = threading.Thread(target=self._file_sync_worker, daemon=True)
        self.file_sync_thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        if self.file_sync_thread:
            self.file_sync_thread.join(timeout=5)

    def queue_message(self, session_id: str, message: Dict, actor: str = "user",
                      message_index: int = -1) -> bool:
        if not self._initialized:
            return False
        try:
            self.upload_queue.put({
                "session_id": session_id, "message": message, "actor": actor,
                "timestamp": datetime.utcnow().isoformat(),
                "event_id": hashlib.md5(
                    f"{session_id}:{json.dumps(message, sort_keys=True)}:{time.time()}".encode()
                ).hexdigest()[:16],
                "message_index": message_index,
            })
            return True
        except Exception as e:
            logger.error(f"Failed to queue message: {e}")
            return False

    def sync_archive(self, session_id: str, messages: List[Dict], slug: str = "") -> bool:
        """Sync curated archive content to AgentCore Memory (Plan B).

        Called by memory_archiver after writing a memory/*.md file.
        Sends conversation as a single create_event batch instead of per-message sync.

        Args:
            session_id: Original session ID
            messages: List of {"role": "user/assistant", "text": "..."} from archiver
            slug: Archive slug for logging

        Returns:
            True if synced successfully, False otherwise
        """
        if not self._initialized or not self._memory_client:
            return False

        try:
            payload = []
            for msg in messages:
                role = msg.get("role", "user").upper()
                if role not in ("USER", "ASSISTANT"):
                    role = "USER"
                text = msg.get("text", "")
                if text:
                    payload.append({
                        "conversational": {"content": {"text": text}, "role": role}
                    })

            if not payload:
                return False

            # Use a distinct sessionId prefix so archive events don't mix with any
            # remaining per-message events from before Plan B migration
            archive_session_id = f"archive-{session_id}"

            self._memory_client.create_event(
                memoryId=self.memory_id,
                actorId="springo",
                sessionId=archive_session_id,
                eventTimestamp=datetime.utcnow(),
                payload=payload,
            )
            logger.info(
                f"Archive synced to AgentCore: {len(payload)} events "
                f"(session={session_id}, slug={slug})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to sync archive to AgentCore: {e}")
            return False

    # -----------------------------------------------------------------------
    # File-based periodic sync (Plan B checkpoint worker)
    # -----------------------------------------------------------------------

    def trigger_file_sync(self):
        """Trigger an immediate file sync (called after distillation, etc.)."""
        if not self._memory_client:
            return
        try:
            self._sync_changed_files()
        except Exception as e:
            logger.warning(f"Triggered file sync failed: {e}")

    def _file_sync_worker(self):
        """Periodic worker that syncs changed memory/*.md files to AgentCore.

        Runs every `file_sync_interval` seconds (default 86400 = 24h).
        Also triggered on-demand after MEMORY.md distillation.
        Uses a checkpoint file to track which files have been synced.
        """
        # Wait a bit before first scan to let the system stabilize
        initial_delay = self._config.get("file_sync_initial_delay", 60)
        for _ in range(initial_delay):
            if self._stop_event.is_set():
                return
            time.sleep(1)

        interval = self._config.get("file_sync_interval", 86400)  # 24h
        logger.info(f"File sync worker started (interval={interval}s)")

        while not self._stop_event.is_set():
            try:
                self._sync_changed_files()
            except Exception as e:
                logger.error(f"File sync error: {e}")

            # Sleep in 1s increments so we can respond to stop quickly
            for _ in range(interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _sync_changed_files(self):
        """Scan memory files, sync new/modified ones to AgentCore."""
        workspace_path = os.path.expanduser(
            self._config.get("workspace_path", "~/.springo/workspace")
        )
        memory_dir = os.path.join(workspace_path, "memory")
        checkpoint_path = os.path.join(workspace_path, ".sync_checkpoint.json")

        checkpoint = self._load_file_checkpoint(checkpoint_path)

        # Collect all memory files
        files_to_check: List[tuple] = []

        # MEMORY.md
        memory_md = os.path.join(workspace_path, "MEMORY.md")
        if os.path.isfile(memory_md):
            files_to_check.append(("MEMORY.md", memory_md))

        # memory/*.md
        if os.path.isdir(memory_dir):
            for name in sorted(os.listdir(memory_dir)):
                if name.endswith(".md"):
                    files_to_check.append((f"memory/{name}", os.path.join(memory_dir, name)))

        if not files_to_check:
            return

        synced_count = 0
        for rel_path, abs_path in files_to_check:
            if self._stop_event.is_set():
                break
            try:
                stat = os.stat(abs_path)
                mtime = stat.st_mtime
                size = stat.st_size

                # Skip if unchanged since last sync
                prev = checkpoint.get("files", {}).get(rel_path)
                if prev and prev.get("mtime") == mtime and prev.get("size") == size:
                    continue

                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.strip():
                    continue

                success = self._sync_file_to_agentcore(rel_path, content)
                if success:
                    checkpoint.setdefault("files", {})[rel_path] = {
                        "mtime": mtime,
                        "size": size,
                        "synced_at": datetime.utcnow().isoformat(),
                    }
                    synced_count += 1
            except Exception as e:
                logger.warning(f"File sync: failed to process {rel_path}: {e}")

        if synced_count > 0:
            checkpoint["last_check"] = datetime.utcnow().isoformat()
            self._save_file_checkpoint(checkpoint_path, checkpoint)
            logger.info(f"File sync: synced {synced_count} changed file(s) to AgentCore")

    def _sync_file_to_agentcore(self, rel_path: str, content: str) -> bool:
        """Sync a single memory file to AgentCore as conversational event(s).

        AgentCore CreateEvent has a 100,000 char limit per text field.
        Large files are split into multiple chunks sent as separate events.
        """
        if not self._memory_client:
            return False

        MAX_CHUNK = 95000  # leave margin below 100k limit

        try:
            session_id = f"memfile-{rel_path.replace('/', '-').replace('.md', '')}"

            if len(content) <= MAX_CHUNK:
                chunks = [content]
            else:
                # Split on paragraph boundaries
                chunks = []
                remaining = content
                while remaining:
                    if len(remaining) <= MAX_CHUNK:
                        chunks.append(remaining)
                        break
                    # Find a good split point (double newline near the limit)
                    split_at = remaining.rfind('\n\n', 0, MAX_CHUNK)
                    if split_at < MAX_CHUNK // 2:
                        split_at = remaining.rfind('\n', 0, MAX_CHUNK)
                    if split_at < MAX_CHUNK // 2:
                        split_at = MAX_CHUNK
                    chunks.append(remaining[:split_at])
                    remaining = remaining[split_at:].lstrip('\n')
                logger.info(f"File sync: splitting {rel_path} into {len(chunks)} chunks ({len(content)} chars)")

            for i, chunk in enumerate(chunks):
                chunk_session = session_id if len(chunks) == 1 else f"{session_id}-part{i+1}"
                payload = [{
                    "conversational": {
                        "content": {"text": chunk},
                        "role": "USER",
                    }
                }]
                self._memory_client.create_event(
                    memoryId=self.memory_id,
                    actorId="springo",
                    sessionId=chunk_session,
                    eventTimestamp=datetime.utcnow(),
                    payload=payload,
                )

            logger.info(f"File sync: synced {rel_path} to AgentCore ({len(content)} chars, {len(chunks)} chunk(s))")
            return True
        except Exception as e:
            logger.error(f"File sync: failed to sync {rel_path}: {e}")
            return False

    def _load_file_checkpoint(self, path: str) -> Dict:
        """Load sync checkpoint from JSON file."""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": {}}

    def _save_file_checkpoint(self, path: str, data: Dict):
        """Save sync checkpoint to JSON file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, ensure_ascii=False, fp=f, indent=2)
        except Exception as e:
            logger.warning(f"File sync: failed to save checkpoint: {e}")

    def queue_conversation(self, session_id: str, messages: List[Dict]) -> int:
        """批量队列消息，返回成功入队数"""
        if not self._initialized:
            return 0
        count = 0
        for i, msg in enumerate(messages):
            actor = "assistant" if msg.get("role") == "assistant" else "user"
            if self.queue_message(session_id, msg, actor, message_index=i):
                count += 1
        if count:
            logger.info(f"Queued {count} messages for memory sync (session={session_id})")
        return count

    def _worker(self):
        batch_size = self._config.get("batch_size", 5)
        batch_timeout = self._config.get("batch_timeout", 30)
        while not self._stop_event.is_set():
            try:
                try:
                    item = self.upload_queue.get(timeout=1.0)
                    self._batch.append(item)
                    if not self._batch_start_time:
                        self._batch_start_time = time.time()
                except Empty:
                    pass
                should_upload = (
                    (len(self._batch) >= batch_size) or
                    (self._batch and (time.time() - self._batch_start_time) >= batch_timeout)
                )
                if should_upload and self._batch:
                    self._upload_batch()
            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(1)
        if self._batch:
            self._upload_batch()

    def _upload_batch(self):
        if not self._batch:
            return
        batch = self._batch.copy()
        self._batch = []
        self._batch_start_time = 0
        max_retries = self._config.get("max_retries", 3)
        retry_delay = self._config.get("retry_delay", 5)
        for attempt in range(max_retries):
            try:
                self._do_upload(batch)
                logger.info(f"Uploaded {len(batch)} events to AgentCore Memory")
                self._update_sync_state(batch)
                return
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        logger.error(f"Failed to upload {len(batch)} events after {max_retries} attempts")
        self._save_failed_batch(batch)

    def _do_upload(self, batch: List[Dict]):
        if not self._memory_client:
            raise RuntimeError("Memory client not initialized")
        sessions: Dict[str, List[Dict]] = {}
        for item in batch:
            sid = item["session_id"]
            sessions.setdefault(sid, []).append(item)
        for session_id, items in sessions.items():
            payload = []
            for item in items:
                msg = item["message"]

                # S3 integration: process message for memory (upload images etc.)
                s3_mgr = _get_s3_manager()
                if s3_mgr:
                    try:
                        msg = s3_mgr.process_message_for_memory(session_id, msg)
                    except Exception as e:
                        logger.debug(f"S3 processing skipped for message: {e}")

                role = msg.get("role", "user").upper()
                if role == "ASSISTANT":
                    role = "ASSISTANT"
                elif role == "USER":
                    role = "USER"
                else:
                    role = "TOOL"
                content = self._extract_content(msg.get("content", ""))
                if content:
                    payload.append({
                        "conversational": {"content": {"text": content}, "role": role}
                    })
            if payload:
                self._memory_client.create_event(
                    memoryId=self.memory_id, actorId="springo",
                    sessionId=session_id, eventTimestamp=datetime.utcnow(),
                    payload=payload
                )

    def _extract_content(self, content) -> str:
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            texts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        texts.append(part.get("text", ""))
                    elif part.get("type") == "image":
                        texts.append(f"[Image: {part.get('s3_uri', '')}]" if part.get('s3_uri') else "[Image]")
                    elif part.get("type") == "tool_use":
                        texts.append(f"[Tool: {part.get('name', 'unknown')}]")
                    elif part.get("type") == "tool_result":
                        s3_ref = f", {part['s3_uri']}" if part.get('s3_uri') else ""
                        texts.append(f"[Tool Result: {part.get('tool_use_id', '')}{s3_ref}]")
                elif isinstance(part, str):
                    texts.append(part)
            return " ".join(texts)
        return str(content)

    def _save_failed_batch(self, batch: List[Dict]):
        failed_dir = os.path.expanduser("~/.springo/failed_uploads")
        os.makedirs(failed_dir, exist_ok=True)
        filepath = os.path.join(failed_dir, f"failed_{int(time.time())}.jsonl")
        with open(filepath, 'w') as f:
            for item in batch:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

    def _update_sync_state(self, batch: List[Dict]):
        sessions: Dict[str, Dict[str, int]] = {}
        for item in batch:
            sid = item.get("session_id")
            idx = item.get("message_index", -1)
            if sid:
                if sid not in sessions:
                    sessions[sid] = {"count": 0, "max_index": -1}
                sessions[sid]["count"] += 1
                if idx > sessions[sid]["max_index"]:
                    sessions[sid]["max_index"] = idx
        for sid, info in sessions.items():
            try:
                session_dir = os.path.join(SESSIONS_DIR, sid)
                if not os.path.exists(session_dir):
                    continue
                state = self._load_sync_state(session_dir)
                current = state.get("last_synced_index", -1)
                if info["max_index"] > current:
                    state["last_synced_index"] = info["max_index"]
                    state["last_sync_time"] = datetime.utcnow().isoformat()
                state["total_synced"] = state.get("total_synced", 0) + info["count"]
                self._save_sync_state(session_dir, state)
            except Exception as e:
                logger.warning(f"Failed to update sync state for {sid}: {e}")

    def _load_sync_state(self, session_dir: str) -> Dict:
        """加载同步状态"""
        state_file = os.path.join(session_dir, SYNC_STATE_FILE)
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_sync_state(self, session_dir: str, state: Dict) -> None:
        """保存同步状态"""
        state_file = os.path.join(session_dir, SYNC_STATE_FILE)
        try:
            with open(state_file, 'w') as f:
                json.dump(state, ensure_ascii=False, fp=f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save sync state: {e}")

    def _load_local_messages(self, session_file: str) -> List[Dict]:
        """从 JSONL 文件加载消息列表"""
        messages = []
        try:
            with open(session_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") in ("session_start", "metadata"):
                            continue
                        if "role" in entry:
                            messages.append(entry)
                        elif "message" in entry:
                            messages.append(entry["message"])
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return messages

    def _sync_check_worker(self):
        time.sleep(self._config.get("sync_check_delay", 2))
        if self._stop_event.is_set():
            return
        try:
            self._retry_failed_uploads()
            if not os.path.exists(SESSIONS_DIR):
                self._sync_check_done = True
                return
            session_dirs = [d for d in os.listdir(SESSIONS_DIR)
                          if os.path.isdir(os.path.join(SESSIONS_DIR, d))]
            synced = 0
            for sid in session_dirs:
                if self._stop_event.is_set():
                    break
                try:
                    count = self._sync_session(sid)
                    synced += count
                except Exception as e:
                    logger.warning(f"Failed to sync session {sid}: {e}")
            logger.info(f"Sync check complete: queued {synced} missing messages")
            self._sync_check_done = True
        except Exception as e:
            logger.error(f"Sync check error: {e}")
            self._sync_check_done = True

    def _sync_session(self, session_id: str) -> int:
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        session_file = os.path.join(session_dir, f"{session_id}.jsonl")
        if not os.path.exists(session_file):
            return 0
        state = self._load_sync_state(session_dir)
        last_idx = state.get("last_synced_index", -1)
        messages = self._load_local_messages(session_file)
        count = 0
        for i, msg in enumerate(messages):
            if i > last_idx:
                actor = "assistant" if msg.get("role") == "assistant" else "user"
                if self.queue_message(session_id, msg, actor, message_index=i):
                    count += 1
        return count

    def _retry_failed_uploads(self) -> int:
        failed_dir = os.path.expanduser("~/.springo/failed_uploads")
        if not os.path.exists(failed_dir):
            return 0
        count = 0
        for filename in os.listdir(failed_dir):
            if not filename.endswith('.jsonl'):
                continue
            filepath = os.path.join(failed_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        self.upload_queue.put(json.loads(line.strip()))
                        count += 1
                os.remove(filepath)
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")
        return count

    def _get_cloud_event_count(self, session_id: str) -> int:
        """查询云端某个 session 的事件数"""
        if not self._memory_client:
            return 0
        try:
            response = self._memory_client.list_events(
                memoryId=self.memory_id,
                sessionId=session_id,
                maxResults=1000
            )
            events = response.get("events", [])
            return len(events)
        except Exception as e:
            logger.warning(f"Failed to get cloud event count for {session_id}: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "memory_id": self.memory_id,
            "region": self.region,
            "queue_size": self.upload_queue.qsize(),
            "batch_size": len(self._batch),
            "worker_running": self.worker_thread.is_alive() if self.worker_thread else False,
            "file_sync_running": self.file_sync_thread.is_alive() if self.file_sync_thread else False,
            "file_sync_interval": self._config.get("file_sync_interval", 86400),
            "sync_check_done": self._sync_check_done,
        }


# Singleton
_sync_manager: Optional[MemorySyncManager] = None


def get_sync_manager() -> Optional[MemorySyncManager]:
    return _sync_manager


def init_memory_sync(memory_id: str = None, region: str = None) -> bool:
    global _sync_manager
    config = load_memory_config()
    memory_id = memory_id or config.get("memory_id", "")
    region = region or config.get("memory_region", "us-west-2")
    if not config.get("memory_enabled", True):
        logger.info("Memory sync is disabled")
        return False
    if not memory_id:
        logger.warning("Memory sync skipped: memory_id not configured")
        return False
    if _sync_manager:
        return True
    _sync_manager = MemorySyncManager(memory_id, region)
    if _sync_manager.start():
        logger.info(f"Memory sync initialized: {memory_id} ({region})")
        return True
    _sync_manager = None
    return False


def shutdown_memory_sync():
    global _sync_manager
    if _sync_manager:
        _sync_manager.stop()
        _sync_manager = None


def get_memory_config() -> Dict[str, Any]:
    config = load_memory_config()
    result = {
        "memory_id": config.get("memory_id", ""),
        "memory_region": config.get("memory_region", "us-west-2"),
        "memory_enabled": config.get("memory_enabled", True),
        "memory_backend": config.get("memory_backend", "agentcore"),
        "batch_size": config.get("batch_size", 5),
        "batch_timeout": config.get("batch_timeout", 30),
        "max_retries": config.get("max_retries", 3),
        "sync_check_delay": config.get("sync_check_delay", 60),
        "config_file": CONFIG_FILE,
    }
    # LTM config — only return strategies when memory_id is configured
    try:
        if result["memory_id"] and os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                fc = json.load(f)
                result["ltm"] = fc.get("memory", {}).get("ltm", {
                    "enabled": False, "strategies": [], "sync_interval": 900
                })
        else:
            result["ltm"] = {"enabled": False, "strategies": [], "sync_interval": 900}
    except Exception:
        result["ltm"] = {"enabled": False, "strategies": [], "sync_interval": 900}
    return result


def create_memory(region: str, name_prefix: str = "springo_memory") -> Dict[str, Any]:
    """配置 Memory 区域"""
    try:
        config = load_memory_config()
        existing_id = config.get('memory_id', '')
        if existing_id:
            config['memory_region'] = region
            config['memory_enabled'] = True
            save_memory_config(config)
            try:
                import boto3
                client = boto3.client('bedrock-agentcore', region_name=region)
                client.list_sessions(memoryId=existing_id, maxResults=1)
                return {"success": True, "memory_id": existing_id, "region": region, "already_exists": True}
            except Exception as e:
                return {"success": True, "memory_id": existing_id, "region": region,
                        "already_exists": True, "warning": str(e)}
        return {
            "success": False,
            "error": f"Memory ID not configured. Create via AgentCore CLI:\n"
                     f"  agentcore memory create --name {name_prefix} --region {region}",
            "region": region
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


STRATEGY_TYPE_DISPLAY_MAP = {
    'SEMANTIC': 'SEMANTIC',
    'USER_PREFERENCE': 'USER_PREFERENCE',
    'SUMMARIZATION': 'SUMMARIZATION',
    'EPISODIC': 'EPISODIC',
}

REQUIRED_LTM_STRATEGIES = {
    'ConversationFacts': {'type': 'semanticMemoryStrategy', 'description': 'Extract semantic facts from conversations'},
    'UserPreferences': {'type': 'userPreferenceMemoryStrategy', 'description': 'Extract user preferences'},
    'ConversationSummary': {'type': 'summaryMemoryStrategy', 'description': 'Generate conversation summaries'},
}


def _parse_memory_strategy(mem_strategy: dict, actor_id: str) -> dict:
    """Parse a memory strategy from API response into internal format."""
    strategy_id = mem_strategy.get('strategyId', '')
    strategy_name = mem_strategy.get('name', '')
    strategy_type_raw = mem_strategy.get('type', 'SEMANTIC')
    strategy_description = mem_strategy.get('description', '')
    namespace_patterns = mem_strategy.get('namespaces', [])

    strategy_type = STRATEGY_TYPE_DISPLAY_MAP.get(strategy_type_raw, strategy_type_raw)

    if namespace_patterns:
        pattern = namespace_patterns[0]
        actual_namespace = pattern.replace('{memoryStrategyId}', strategy_id).replace('{actorId}', actor_id)
        if '{sessionId}' in actual_namespace:
            actual_namespace = actual_namespace.replace('/sessions/{sessionId}/', '/')
    else:
        actual_namespace = f"/strategies/{strategy_id}/actors/{actor_id}/"

    return {
        'id': strategy_id,
        'name': strategy_name,
        'type': strategy_type,
        'namespace': actual_namespace,
        'description': strategy_description or f'{strategy_name} strategy',
    }


def _parse_strategies_list(memory_strategies: list, actor_id: str) -> list:
    return [_parse_memory_strategy(s, actor_id) for s in memory_strategies]


def _create_missing_ltm_strategies(control_client, memory_id: str, strategies: list, actor_id: str) -> list:
    """Create any missing LTM strategies (semantic, summary, userPreference)."""
    existing_names = {s['name'] for s in strategies}
    strategies_to_create = [
        {config['type']: {'name': name, 'description': config['description']}}
        for name, config in REQUIRED_LTM_STRATEGIES.items()
        if name not in existing_names
    ]

    if not strategies_to_create:
        return strategies

    logger.info(f"Creating {len(strategies_to_create)} missing LTM strategies")
    try:
        response = control_client.update_memory(
            memoryId=memory_id,
            memoryStrategies={'addMemoryStrategies': strategies_to_create}
        )
        new_strategies = response.get('memory', {}).get('strategies', [])
        logger.info(f"After update, memory has {len(new_strategies)} strategies")
        return _parse_strategies_list(new_strategies, actor_id)
    except Exception as e:
        logger.warning(f"Failed to create missing LTM strategies: {e}")
        return strategies


def _create_episodic_strategy(control_client, memory_id: str, strategies: list, actor_id: str) -> list:
    """Create EPISODIC strategy with reflection."""
    if any(s['type'] == 'EPISODIC' for s in strategies):
        logger.info("EPISODIC strategy already exists")
        return strategies

    episodic_namespace = '/strategies/{memoryStrategyId}/actors/{actorId}/sessions/{sessionId}/'
    reflection_namespace = '/strategies/{memoryStrategyId}/actors/{actorId}/'

    logger.info(f"Creating EPISODIC strategy with reflection namespace: {reflection_namespace}")
    try:
        response = control_client.update_memory(
            memoryId=memory_id,
            memoryStrategies={
                'addMemoryStrategies': [{
                    'episodicMemoryStrategy': {
                        'name': 'ConversationEpisodes',
                        'namespaces': [episodic_namespace],
                        'reflectionConfiguration': {'namespaces': [reflection_namespace]}
                    }
                }]
            }
        )
        new_strategies = response.get('memory', {}).get('strategies', [])
        logger.info(f"Created EPISODIC strategy, memory now has {len(new_strategies)} strategies")
        return _parse_strategies_list(new_strategies, actor_id)
    except Exception as e:
        logger.warning(f"Failed to create EPISODIC strategy: {e}")
        return strategies


def auto_setup_memory_strategies(memory_id: str, region: str, create_missing: bool = True) -> Dict[str, Any]:
    """Auto-discover and setup LTM strategies for a memory.

    AgentCore Memory supports 4 strategy types:
    1. SEMANTIC (ConversationFacts) - Extract semantic facts from conversations
    2. USER_PREFERENCE (UserPreferences) - Extract user preferences
    3. SUMMARIZATION (ConversationSummary) - Generate conversation summaries
    4. EPISODIC (ConversationEpisodes) - Capture interactions as structured episodes with reflections
    """
    actor_id = "springo"
    strategies = []

    try:
        import boto3
        control_client = boto3.client('bedrock-agentcore-control', region_name=region)

        try:
            memory_response = control_client.get_memory(memoryId=memory_id)
            logger.info(f"Got memory details for {memory_id}")

            memory_strategies = memory_response.get('memory', {}).get('strategies', [])
            logger.info(f"Found {len(memory_strategies)} strategies in memory resource")

            strategies = _parse_strategies_list(memory_strategies, actor_id)
            for s in strategies:
                logger.info(f"Found strategy: {s['name']} (ID: {s['id']}) -> {s['namespace']}")

            if create_missing:
                strategies = _create_missing_ltm_strategies(control_client, memory_id, strategies, actor_id)
                strategies = _create_episodic_strategy(control_client, memory_id, strategies, actor_id)

        except Exception as e:
            logger.warning(f"Failed to get memory details via control plane: {e}")

        # Fallback default config if no strategies discovered
        if not strategies:
            logger.warning("No strategies discovered, using default configuration")
            default_strategies = [
                {'type': 'SEMANTIC', 'name': 'ConversationFacts', 'description': 'Extract semantic facts from conversations'},
                {'type': 'USER_PREFERENCE', 'name': 'UserPreferences', 'description': 'Extract user preferences'},
                {'type': 'SUMMARIZATION', 'name': 'ConversationSummary', 'description': 'Generate conversation summaries'},
                {'type': 'EPISODIC', 'name': 'ConversationEpisodes', 'description': 'Capture interactions as structured episodes'},
            ]
            for st in default_strategies:
                strategies.append({
                    'id': f"{st['name']}-{actor_id}",
                    'name': st['name'],
                    'type': st['type'],
                    'namespace': f"/strategies/{st['name']}/actors/{actor_id}/",
                    'description': st['description'],
                })

        # Update config with discovered strategies
        config = load_memory_config()
        config["ltm"] = {
            "enabled": len(strategies) > 0,
            "strategies": strategies,
        }
        save_memory_config(config)

        logger.info(f"Auto-setup memory strategies: {len(strategies)} strategies configured")
        return {
            "success": True,
            "strategies": strategies,
            "count": len(strategies),
        }
    except Exception as e:
        logger.error(f"Auto setup memory strategies failed: {e}")
        return {"success": False, "error": str(e), "strategies": []}


__all__ = [
    'MemorySyncManager', 'get_sync_manager', 'init_memory_sync',
    'shutdown_memory_sync', 'get_memory_config', 'save_memory_config',
    'load_memory_config', 'create_memory', 'auto_setup_memory_strategies',
]
