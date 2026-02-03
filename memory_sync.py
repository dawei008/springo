"""
AgentCore Memory Sync Module for Springo

异步将本地会话同步到 AgentCore Memory，实现：
- 本地优先：消息先存本地 JSONL，确保不丢失
- 异步上传：后台线程批量上传到 AgentCore Memory
- 失败重试：上传失败自动重试，记录状态

配置项（~/.springo/config.json 中的 memory 节）：
- memory_id: Memory ID
- memory_region: Memory 所在区域
- memory_enabled: 是否启用 memory sync (默认 true)
- batch_size: 批量上传大小 (默认 5)
- batch_timeout: 批量超时秒数 (默认 30)

环境变量（优先级高于配置文件）：
- SPRINGO_MEMORY_ID
- SPRINGO_MEMORY_REGION
- SPRINGO_MEMORY_ENABLED
"""

import os
import json
import time
import logging
import threading
import hashlib
from queue import Queue, Empty
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# S3 sync integration (lazy import to avoid circular dependency)
_s3_sync_module = None

def _get_s3_manager():
    """Lazy load S3 manager to avoid circular import"""
    global _s3_sync_module
    if _s3_sync_module is None:
        try:
            import s3_sync as s3_module
            _s3_sync_module = s3_module
        except ImportError:
            return None
    return _s3_sync_module.get_s3_manager()

# 配置文件路径
CONFIG_DIR = os.path.expanduser("~/.springo")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SESSIONS_DIR = os.path.join(CONFIG_DIR, "sessions")

# 默认配置
DEFAULT_MEMORY_CONFIG = {
    "memory_id": "",  # 必须配置
    "memory_region": "us-west-2",
    "memory_enabled": True,
    "batch_size": 5,
    "batch_timeout": 30,
    "max_retries": 3,
    "retry_delay": 5,
    "sync_check_delay": 2
}

# 同步状态文件名
SYNC_STATE_FILE = ".sync_state.json"


def load_memory_config() -> Dict[str, Any]:
    """
    加载 Memory 配置
    优先级：环境变量 > 配置文件 > 默认值
    """
    config = DEFAULT_MEMORY_CONFIG.copy()

    # 1. 从配置文件读取
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                memory_config = file_config.get("memory", {})
                config.update(memory_config)
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")

    # 2. 环境变量覆盖
    env_mappings = {
        "SPRINGO_MEMORY_ID": "memory_id",
        "SPRINGO_MEMORY_REGION": "memory_region",
        "SPRINGO_MEMORY_ENABLED": "memory_enabled",
        "SPRINGO_MEMORY_BATCH_SIZE": "batch_size",
        "SPRINGO_MEMORY_BATCH_TIMEOUT": "batch_timeout"
    }

    for env_key, config_key in env_mappings.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            # 类型转换
            if config_key == "memory_enabled":
                config[config_key] = env_value.lower() in ("true", "1", "yes")
            elif config_key in ("batch_size", "batch_timeout"):
                try:
                    config[config_key] = int(env_value)
                except ValueError:
                    pass
            else:
                config[config_key] = env_value

    return config


def save_memory_config(memory_config: Dict[str, Any]) -> bool:
    """保存 Memory 配置到配置文件（合并而非覆盖）"""
    try:
        # 读取现有配置
        file_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

        # 获取现有的 memory 节（保留 ltm 等子配置）
        existing_memory = file_config.get("memory", {})

        # 更新基础字段，保留其他子配置（如 ltm）
        existing_memory.update({
            "memory_id": memory_config.get("memory_id", existing_memory.get("memory_id", "")),
            "memory_region": memory_config.get("memory_region", existing_memory.get("memory_region", "us-west-2")),
            "memory_enabled": memory_config.get("memory_enabled", existing_memory.get("memory_enabled", True))
        })

        file_config["memory"] = existing_memory

        # 确保目录存在
        os.makedirs(CONFIG_DIR, exist_ok=True)

        # 写入配置
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(file_config, ensure_ascii=False, fp=f, indent=2)

        return True
    except Exception as e:
        logger.error(f"Failed to save memory config: {e}")
        return False


# 加载配置
_config = load_memory_config()

# 导出配置常量（供其他模块使用）
MEMORY_ID = _config["memory_id"]
MEMORY_REGION = _config["memory_region"]
MEMORY_ENABLED = _config["memory_enabled"]
BATCH_SIZE = _config["batch_size"]
BATCH_TIMEOUT = _config["batch_timeout"]
MAX_RETRIES = _config["max_retries"]
RETRY_DELAY = _config["retry_delay"]
SYNC_CHECK_DELAY = _config["sync_check_delay"]


class MemorySyncManager:
    """管理会话到 AgentCore Memory 的异步同步"""

    def __init__(self, memory_id: str = MEMORY_ID, region: str = MEMORY_REGION):
        self.memory_id = memory_id
        self.region = region
        self.upload_queue: Queue = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.sync_check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._batch: List[Dict] = []
        self._batch_start_time: float = 0
        self._initialized = False
        self._memory_client = None
        self._sync_check_done = False

    def initialize(self) -> bool:
        """初始化 Memory 客户端"""
        try:
            import boto3
            # 使用 boto3 直接调用 bedrock-agentcore API
            self._memory_client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region
            )
            self._initialized = True
            logger.info(f"MemorySyncManager initialized: {self.memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MemorySyncManager: {e}")
            return False

    def start(self) -> bool:
        """启动后台同步线程"""
        if not self._initialized:
            if not self.initialize():
                return False

        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return True

        self._stop_event.clear()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        logger.info("Memory sync worker started")

        # 启动异步同步检查线程
        self.sync_check_thread = threading.Thread(target=self._sync_check_worker, daemon=True)
        self.sync_check_thread.start()
        logger.info("Sync check worker started")

        return True

    def stop(self):
        """停止后台同步线程"""
        self._stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
            logger.info("Memory sync worker stopped")

    def queue_message(self, session_id: str, message: Dict[str, Any],
                      actor: str = "user", message_index: int = -1) -> bool:
        """
        将消息加入上传队列（非阻塞）

        Args:
            session_id: 会话 ID
            message: 消息内容 {"role": "user/assistant", "content": ...}
            actor: 消息发送者标识
            message_index: 消息在本地文件中的索引（用于同步状态跟踪）

        Returns:
            是否成功加入队列
        """
        if not self._initialized:
            return False

        try:
            event_data = {
                "session_id": session_id,
                "message": message,
                "actor": actor,
                "timestamp": datetime.utcnow().isoformat(),
                "event_id": self._generate_event_id(session_id, message),
                "message_index": message_index  # 用于上传成功后更新同步状态
            }
            self.upload_queue.put(event_data)
            logger.debug(f"Queued message for session {session_id}, index={message_index}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue message: {e}")
            return False

    def queue_conversation(self, session_id: str, messages: List[Dict[str, Any]]) -> int:
        """
        批量将整个会话加入上传队列

        Returns:
            成功加入队列的消息数
        """
        count = 0
        for msg in messages:
            actor = "assistant" if msg.get("role") == "assistant" else "user"
            if self.queue_message(session_id, msg, actor):
                count += 1
        return count

    def _generate_event_id(self, session_id: str, message: Dict) -> str:
        """生成唯一的事件 ID"""
        content = json.dumps(message, sort_keys=True, ensure_ascii=False)
        hash_input = f"{session_id}:{content}:{time.time()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

    def _worker(self):
        """后台工作线程：批量上传消息到 AgentCore Memory"""
        logger.info("Memory sync worker thread started")

        while not self._stop_event.is_set():
            try:
                # 尝试获取消息，超时 1 秒
                try:
                    item = self.upload_queue.get(timeout=1.0)
                    self._batch.append(item)
                    if not self._batch_start_time:
                        self._batch_start_time = time.time()
                except Empty:
                    pass

                # 检查是否需要上传批次
                should_upload = False
                if len(self._batch) >= BATCH_SIZE:
                    should_upload = True
                    logger.debug(f"Batch full ({len(self._batch)} items)")
                elif self._batch and (time.time() - self._batch_start_time) >= BATCH_TIMEOUT:
                    should_upload = True
                    logger.debug(f"Batch timeout ({len(self._batch)} items)")

                if should_upload and self._batch:
                    self._upload_batch()

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(1)

        # 停止前上传剩余批次
        if self._batch:
            logger.info(f"Uploading remaining {len(self._batch)} items before shutdown")
            self._upload_batch()

    def _upload_batch(self):
        """上传当前批次到 AgentCore Memory"""
        if not self._batch:
            return

        batch_to_upload = self._batch.copy()
        self._batch = []
        self._batch_start_time = 0

        for attempt in range(MAX_RETRIES):
            try:
                self._do_upload(batch_to_upload)
                logger.info(f"Uploaded {len(batch_to_upload)} events to AgentCore Memory")
                # 上传成功后更新同步状态
                self._update_sync_state_after_upload(batch_to_upload)
                return
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)

        # 所有重试失败，保存到本地失败队列
        logger.error(f"Failed to upload {len(batch_to_upload)} events after {MAX_RETRIES} attempts")
        self._save_failed_batch(batch_to_upload)

    def _do_upload(self, batch: List[Dict]):
        """执行实际的上传操作"""
        if not self._memory_client:
            raise RuntimeError("Memory client not initialized")

        # 获取 S3 manager（如果可用）
        s3_manager = _get_s3_manager()

        # 按 session_id 分组
        sessions: Dict[str, List[Dict]] = {}
        for item in batch:
            session_id = item["session_id"]
            if session_id not in sessions:
                sessions[session_id] = []

            # 如果 S3 同步可用，先处理消息中的文件引用
            if s3_manager:
                message = item.get("message", {})
                processed_message = s3_manager.process_message_for_memory(session_id, message)
                item = {**item, "message": processed_message}

            sessions[session_id].append(item)

        # 每个 session 创建一个 event
        for session_id, items in sessions.items():
            # 构建 messages 列表: List[Tuple[str, str]] (text, role)
            messages = []
            actor_id = "springo"  # 固定使用 "springo" 作为 actor ID

            for item in items:
                message = item["message"]
                role = message.get("role", "user").upper()
                if role == "ASSISTANT":
                    role = "ASSISTANT"
                elif role == "USER":
                    role = "USER"
                else:
                    role = "TOOL"

                content = self._extract_content(message.get("content", ""))
                if content:
                    messages.append((content, role))

            if messages:
                # 调用 boto3 create_event API
                # payload 格式: [{"conversational": {"content": {"text": "..."}, "role": "USER|ASSISTANT"}}]
                payload = [
                    {
                        "conversational": {
                            "content": {"text": text},
                            "role": role
                        }
                    }
                    for text, role in messages
                ]
                self._memory_client.create_event(
                    memoryId=self.memory_id,
                    actorId=actor_id,
                    sessionId=session_id,
                    eventTimestamp=datetime.utcnow(),
                    payload=payload
                )

    def _extract_content(self, content) -> str:
        """提取消息内容为字符串，包含 S3 URI 引用"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # 处理多部分内容
            texts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        texts.append(part.get("text", ""))
                    elif part.get("type") == "image":
                        # 包含 S3 URI（如果有）
                        s3_uri = part.get("s3_uri", "")
                        if s3_uri:
                            texts.append(f"[Image: {s3_uri}]")
                        else:
                            texts.append("[Image]")
                    elif part.get("type") == "tool_use":
                        texts.append(f"[Tool: {part.get('name', 'unknown')}]")
                    elif part.get("type") == "tool_result":
                        # 包含 S3 URI（如果有）
                        s3_uri = part.get("s3_uri", "")
                        tool_use_id = part.get('tool_use_id', '')
                        if s3_uri:
                            texts.append(f"[Tool Result: {tool_use_id}, {s3_uri}]")
                        else:
                            texts.append(f"[Tool Result: {tool_use_id}]")
                elif isinstance(part, str):
                    texts.append(part)
            return " ".join(texts)
        return str(content)

    def _save_failed_batch(self, batch: List[Dict]):
        """保存上传失败的批次到本地文件"""
        failed_dir = os.path.expanduser("~/.springo/failed_uploads")
        os.makedirs(failed_dir, exist_ok=True)

        filename = f"failed_{int(time.time())}.jsonl"
        filepath = os.path.join(failed_dir, filename)

        with open(filepath, 'w') as f:
            for item in batch:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        logger.info(f"Saved {len(batch)} failed events to {filepath}")

    def get_stats(self) -> Dict[str, Any]:
        """获取同步统计信息"""
        return {
            "initialized": self._initialized,
            "memory_id": self.memory_id,
            "region": self.region,
            "queue_size": self.upload_queue.qsize(),
            "batch_size": len(self._batch),
            "worker_running": self.worker_thread.is_alive() if self.worker_thread else False,
            "sync_check_done": self._sync_check_done
        }

    # ========== 异步同步检查功能 ==========

    def _sync_check_worker(self):
        """后台同步检查线程：扫描本地 sessions，对比云端，补充上传缺失消息"""
        logger.info("Sync check worker thread started")

        # 延迟启动，等待其他初始化完成
        time.sleep(SYNC_CHECK_DELAY)

        if self._stop_event.is_set():
            return

        try:
            # 1. 先重试之前失败的上传
            failed_count = self.retry_failed_uploads()
            if failed_count > 0:
                logger.info(f"Requeued {failed_count} previously failed events")

            # 2. 扫描本地 sessions 目录
            if not os.path.exists(SESSIONS_DIR):
                logger.info("No sessions directory found, skipping sync check")
                self._sync_check_done = True
                return

            session_dirs = [d for d in os.listdir(SESSIONS_DIR)
                          if os.path.isdir(os.path.join(SESSIONS_DIR, d))]

            logger.info(f"Found {len(session_dirs)} local sessions to check")

            # 3. 对每个 session 进行同步检查
            synced_count = 0
            for session_id in session_dirs:
                if self._stop_event.is_set():
                    break

                try:
                    count = self._sync_session(session_id)
                    if count > 0:
                        synced_count += count
                        logger.info(f"Session {session_id}: queued {count} missing messages")
                except Exception as e:
                    logger.warning(f"Failed to sync session {session_id}: {e}")

            logger.info(f"Sync check complete: queued {synced_count} missing messages from {len(session_dirs)} sessions")
            self._sync_check_done = True

        except Exception as e:
            logger.error(f"Sync check worker error: {e}")
            self._sync_check_done = True

    def _sync_session(self, session_id: str) -> int:
        """
        同步单个 session：对比本地和云端，补充上传缺失的消息

        Returns:
            补充上传的消息数
        """
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        session_file = os.path.join(session_dir, f"{session_id}.jsonl")

        if not os.path.exists(session_file):
            return 0

        # 1. 读取本地同步状态
        sync_state = self._load_sync_state(session_dir)
        last_synced_index = sync_state.get("last_synced_index", -1)

        # 2. 读取本地消息
        local_messages = self._load_local_messages(session_file)
        if not local_messages:
            return 0

        # 3. 查询云端事件数（可选，用于验证）
        # cloud_count = self._get_cloud_event_count(session_id)

        # 4. 找出未同步的消息（index > last_synced_index）
        unsent_messages = []
        for i, msg in enumerate(local_messages):
            if i > last_synced_index:
                unsent_messages.append((i, msg))

        if not unsent_messages:
            return 0

        # 5. 将缺失消息加入上传队列（传递 message_index 用于后续状态更新）
        queued_count = 0

        for idx, msg in unsent_messages:
            role = msg.get("role", "user")
            actor = "assistant" if role == "assistant" else "user"

            # 传递 message_index，同步状态将在 _update_sync_state_after_upload 中更新
            if self.queue_message(session_id, msg, actor, message_index=idx):
                queued_count += 1

        # 注意：不在这里更新同步状态！同步状态只在消息实际上传成功后才更新
        # 见 _update_sync_state_after_upload 方法
        if queued_count > 0:
            logger.info(f"Queued {queued_count} messages for session {session_id} (pending upload)")

        return queued_count

    def _load_local_messages(self, session_file: str) -> List[Dict[str, Any]]:
        """从本地 JSONL 文件加载消息"""
        messages = []
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        # 跳过元数据行
                        if entry.get("type") == "session_start":
                            continue
                        if entry.get("type") == "message":
                            messages.append(entry.get("message", {}))
                        elif "message" in entry:
                            messages.append(entry["message"])
                        elif "role" in entry:
                            # 直接是消息格式
                            messages.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to load messages from {session_file}: {e}")
        return messages

    def _load_sync_state(self, session_dir: str) -> Dict[str, Any]:
        """加载 session 的同步状态"""
        state_file = os.path.join(session_dir, SYNC_STATE_FILE)
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_synced_index": -1}

    def _save_sync_state(self, session_dir: str, state: Dict[str, Any]):
        """保存 session 的同步状态"""
        state_file = os.path.join(session_dir, SYNC_STATE_FILE)
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, ensure_ascii=False, fp=f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save sync state: {e}")

    def _get_cloud_event_count(self, session_id: str) -> int:
        """查询云端某个 session 的事件数"""
        if not self._memory_client:
            return 0

        try:
            response = self._memory_client.list_events(
                memoryId=self.memory_id,
                sessionId=session_id,
                maxResults=1000  # 获取最多 1000 条
            )
            events = response.get("events", [])
            return len(events)
        except Exception as e:
            logger.warning(f"Failed to get cloud event count for {session_id}: {e}")
            return 0

    def _update_sync_state_after_upload(self, batch: List[Dict]):
        """上传成功后更新同步状态（仅基于实际上传的消息）"""
        # 按 session_id 分组，记录 count 和 max_index
        sessions: Dict[str, Dict[str, int]] = {}
        for item in batch:
            session_id = item.get("session_id")
            msg_index = item.get("message_index", -1)
            if session_id:
                if session_id not in sessions:
                    sessions[session_id] = {"count": 0, "max_index": -1}
                sessions[session_id]["count"] += 1
                if msg_index > sessions[session_id]["max_index"]:
                    sessions[session_id]["max_index"] = msg_index

        # 更新每个 session 的同步状态
        for session_id, info in sessions.items():
            count = info["count"]
            max_index = info["max_index"]

            try:
                session_dir = os.path.join(SESSIONS_DIR, session_id)
                if not os.path.exists(session_dir):
                    continue

                sync_state = self._load_sync_state(session_dir)
                current_index = sync_state.get("last_synced_index", -1)

                # 只有当实际上传的消息索引大于当前同步索引时才更新
                if max_index > current_index:
                    sync_state["last_synced_index"] = max_index
                    sync_state["last_sync_time"] = datetime.utcnow().isoformat()
                    sync_state["total_synced"] = sync_state.get("total_synced", 0) + count
                    self._save_sync_state(session_dir, sync_state)
                    logger.info(f"Sync state updated for {session_id}: index {current_index} -> {max_index} (+{count} messages)")
                elif count > 0:
                    # 消息上传成功但索引没有更新（可能是旧消息的重试）
                    sync_state["total_synced"] = sync_state.get("total_synced", 0) + count
                    self._save_sync_state(session_dir, sync_state)
                    logger.debug(f"Uploaded {count} messages for {session_id} (no index change)")

            except Exception as e:
                logger.warning(f"Failed to update sync state for {session_id}: {e}")

    def retry_failed_uploads(self) -> int:
        """重试之前失败的上传"""
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
                        item = json.loads(line.strip())
                        self.upload_queue.put(item)
                        count += 1

                # 成功加入队列后删除文件
                os.remove(filepath)
                logger.info(f"Requeued {count} events from {filename}")
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")

        return count


# 全局实例
_sync_manager: Optional[MemorySyncManager] = None


def get_sync_manager() -> Optional[MemorySyncManager]:
    """获取全局同步管理器实例"""
    global _sync_manager
    return _sync_manager


def init_memory_sync(memory_id: str = None, region: str = None) -> bool:
    """
    初始化并启动内存同步

    在应用启动时调用一次。
    如果未配置 memory_id 或 memory_enabled=False，则跳过初始化。

    Args:
        memory_id: Memory ID (可选，默认从配置读取)
        region: Memory 区域 (可选，默认从配置读取)

    Returns:
        是否成功初始化
    """
    global _sync_manager

    # 使用传入的参数或配置值
    memory_id = memory_id or MEMORY_ID
    region = region or MEMORY_REGION

    # 检查是否启用
    if not MEMORY_ENABLED:
        logger.info("Memory sync is disabled in config")
        return False

    # 检查 memory_id 是否配置
    if not memory_id:
        logger.warning("Memory sync skipped: memory_id not configured. "
                      "Set 'memory.memory_id' in ~/.springo/config.json or "
                      "SPRINGO_MEMORY_ID environment variable.")
        return False

    if _sync_manager:
        logger.warning("Memory sync already initialized")
        return True

    _sync_manager = MemorySyncManager(memory_id, region)
    if _sync_manager.start():
        logger.info(f"Memory sync initialized: {memory_id} ({region})")
        return True
    else:
        _sync_manager = None
        return False


def shutdown_memory_sync():
    """关闭内存同步"""
    global _sync_manager
    if _sync_manager:
        _sync_manager.stop()
        _sync_manager = None
        logger.info("Memory sync shutdown complete")


def get_memory_config() -> Dict[str, Any]:
    """获取当前 Memory 配置"""
    config = {
        "memory_id": MEMORY_ID,
        "memory_region": MEMORY_REGION,
        "memory_enabled": MEMORY_ENABLED,
        "batch_size": BATCH_SIZE,
        "batch_timeout": BATCH_TIMEOUT,
        "max_retries": MAX_RETRIES,
        "sync_check_delay": SYNC_CHECK_DELAY,
        "config_file": CONFIG_FILE
    }

    # 加载 LTM 配置
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                memory_section = file_config.get("memory", {})
                config["ltm"] = memory_section.get("ltm", {
                    "enabled": False,
                    "strategies": [],
                    "sync_interval": 900
                })
    except Exception as e:
        logger.warning(f"Failed to load LTM config: {e}")
        config["ltm"] = {"enabled": False, "strategies": [], "sync_interval": 900}

    return config


def create_memory(region: str, name_prefix: str = "springo_memory") -> Dict[str, Any]:
    """
    配置 AgentCore Memory 区域

    注意：Memory 创建需要通过 AgentCore CLI 或 AWS Console 完成。
    此函数仅更新区域配置，并验证现有 Memory 是否可用。

    Args:
        region: Memory 所在区域
        name_prefix: Memory 名称前缀 (未使用，保留兼容性)

    Returns:
        {"success": True, "memory_id": "...", "region": "..."} 或
        {"success": False, "error": "..."}
    """
    try:
        # 检查是否已有 Memory 配置
        config = load_memory_config()
        existing_memory_id = config.get('memory_id', '')

        if existing_memory_id:
            # Memory 已配置，更新区域并验证
            logger.info(f"Using existing Memory: {existing_memory_id}, updating region to {region}")

            # 更新配置
            config['memory_region'] = region
            config['memory_enabled'] = True
            save_memory_config(config)

            # 验证 Memory 是否可用
            import boto3
            client = boto3.client('bedrock-agentcore', region_name=region)

            try:
                # 尝试列出 sessions 来验证 Memory 可用
                client.list_sessions(memoryId=existing_memory_id, maxResults=1)
                logger.info(f"Memory {existing_memory_id} is accessible in {region}")

                return {
                    "success": True,
                    "memory_id": existing_memory_id,
                    "region": region,
                    "already_exists": True
                }
            except Exception as e:
                logger.warning(f"Memory validation failed: {e}")
                # Memory 可能在不同区域，仍然返回成功让用户尝试
                return {
                    "success": True,
                    "memory_id": existing_memory_id,
                    "region": region,
                    "already_exists": True,
                    "warning": f"Memory may not be accessible: {str(e)}"
                }
        else:
            # 没有配置 Memory，提示用户创建
            return {
                "success": False,
                "error": "Memory ID not configured. Please create Memory using AgentCore CLI:\n"
                         "  agentcore memory create --name springo_memory --region " + region,
                "region": region
            }

    except Exception as e:
        logger.error(f"Failed to configure Memory: {e}")
        return {"success": False, "error": str(e)}
