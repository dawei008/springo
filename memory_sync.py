"""
AgentCore Memory Sync Module for Springo

异步将本地会话同步到 AgentCore Memory，实现：
- 本地优先：消息先存本地 JSONL，确保不丢失
- 异步上传：后台线程批量上传到 AgentCore Memory
- 失败重试：上传失败自动重试，记录状态
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

# AgentCore Memory 配置
MEMORY_ID = "springo_memory-b6trnrDLSN"
MEMORY_REGION = "us-west-2"

# 同步配置
BATCH_SIZE = 5  # 每批上传消息数
BATCH_TIMEOUT = 30  # 批量超时秒数
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 5  # 重试延迟秒数


class MemorySyncManager:
    """管理会话到 AgentCore Memory 的异步同步"""

    def __init__(self, memory_id: str = MEMORY_ID, region: str = MEMORY_REGION):
        self.memory_id = memory_id
        self.region = region
        self.upload_queue: Queue = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._batch: List[Dict] = []
        self._batch_start_time: float = 0
        self._initialized = False
        self._memory_client = None

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
        return True

    def stop(self):
        """停止后台同步线程"""
        self._stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
            logger.info("Memory sync worker stopped")

    def queue_message(self, session_id: str, message: Dict[str, Any],
                      actor: str = "user") -> bool:
        """
        将消息加入上传队列（非阻塞）

        Args:
            session_id: 会话 ID
            message: 消息内容 {"role": "user/assistant", "content": ...}
            actor: 消息发送者标识

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
                "event_id": self._generate_event_id(session_id, message)
            }
            self.upload_queue.put(event_data)
            logger.debug(f"Queued message for session {session_id}")
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

        # 按 session_id 分组
        sessions: Dict[str, List[Dict]] = {}
        for item in batch:
            session_id = item["session_id"]
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(item)

        # 每个 session 创建一个 event
        for session_id, items in sessions.items():
            # 构建 messages 列表: List[Tuple[str, str]] (text, role)
            messages = []
            actor_id = "user"  # 默认 actor

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

                # 使用第一个 actor
                if item.get("actor"):
                    actor_id = item["actor"]

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
        """提取消息内容为字符串"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # 处理多部分内容
            texts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        texts.append(part.get("text", ""))
                    elif part.get("type") == "tool_use":
                        texts.append(f"[Tool: {part.get('name', 'unknown')}]")
                    elif part.get("type") == "tool_result":
                        texts.append(f"[Tool Result: {part.get('tool_use_id', '')}]")
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
            "worker_running": self.worker_thread.is_alive() if self.worker_thread else False
        }

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


def init_memory_sync(memory_id: str = MEMORY_ID, region: str = MEMORY_REGION) -> bool:
    """
    初始化并启动内存同步

    在应用启动时调用一次
    """
    global _sync_manager

    if _sync_manager:
        logger.warning("Memory sync already initialized")
        return True

    _sync_manager = MemorySyncManager(memory_id, region)
    if _sync_manager.start():
        logger.info("Memory sync initialized and started")
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
