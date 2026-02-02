"""
S3 Sync Module for Springo

上传会话文件（图片、工具结果等）到 S3，用于云端分析和 AgentCore Memory 引用。

S3 结构：
  s3://springo/{account-id}/sessions/{session_id}/images/{image_id}.png
  s3://springo/{account-id}/sessions/{session_id}/tool-results/{result_id}.json

流程：
  1. 本地会话有图片或工具结果文件
  2. 上传到 S3，获取 S3 URI
  3. 将 S3 URI 更新到 AgentCore Memory 的事件数据中

配置项（~/.springo/config.json 中的 s3 节）：
- s3_bucket: S3 桶名 (默认 "springo")
- s3_region: S3 桶区域 (默认 "us-east-1")
- s3_enabled: 是否启用 S3 同步 (默认 true)
- s3_upload_on_sync: 同步到 Memory 时自动上传文件 (默认 true)

环境变量（优先级高于配置文件）：
- SPRINGO_S3_BUCKET
- SPRINGO_S3_REGION
- SPRINGO_S3_ENABLED
"""

import os
import json
import time
import logging
import threading
import base64
from queue import Queue, Empty
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_DIR = os.path.expanduser("~/.springo")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SESSIONS_DIR = os.path.join(CONFIG_DIR, "sessions")

# 默认配置
# 注意：s3_region 会从 memory 配置同步，确保两者在同一区域
DEFAULT_S3_CONFIG = {
    "s3_bucket": "springo",
    "s3_region": "",  # 从 memory_region 同步
    "s3_enabled": True,
    "s3_upload_on_sync": True,
    "max_retries": 3,
    "retry_delay": 2
}


def _get_memory_region() -> str:
    """从 memory 配置获取区域，确保 S3 和 Memory 在同一区域"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                memory_config = file_config.get("memory", {})
                return memory_config.get("memory_region", "us-west-2")
        except Exception:
            pass
    return "us-west-2"


def load_s3_config() -> Dict[str, Any]:
    """
    加载 S3 配置
    优先级：环境变量 > 配置文件 > memory_region > 默认值

    注意：s3_region 默认从 memory_region 同步，确保两者在同一区域
    """
    config = DEFAULT_S3_CONFIG.copy()

    # 1. 从配置文件读取
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                s3_config = file_config.get("s3", {})
                config.update(s3_config)
        except Exception as e:
            logger.warning(f"Failed to load S3 config from file: {e}")

    # 2. 如果 s3_region 未设置，从 memory_region 同步
    if not config.get("s3_region"):
        config["s3_region"] = _get_memory_region()

    # 3. 环境变量覆盖
    env_mappings = {
        "SPRINGO_S3_BUCKET": "s3_bucket",
        "SPRINGO_S3_REGION": "s3_region",
        "SPRINGO_S3_ENABLED": "s3_enabled",
        "SPRINGO_S3_UPLOAD_ON_SYNC": "s3_upload_on_sync"
    }

    for env_key, config_key in env_mappings.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            if config_key in ("s3_enabled", "s3_upload_on_sync"):
                config[config_key] = env_value.lower() in ("true", "1", "yes")
            else:
                config[config_key] = env_value

    return config


def save_s3_config(s3_config: Dict[str, Any]) -> bool:
    """保存 S3 配置到配置文件"""
    try:
        file_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

        file_config["s3"] = s3_config
        os.makedirs(CONFIG_DIR, exist_ok=True)

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(file_config, ensure_ascii=False, fp=f, indent=2)

        return True
    except Exception as e:
        logger.error(f"Failed to save S3 config: {e}")
        return False


# 加载配置
_config = load_s3_config()

# 导出配置常量
S3_BUCKET = _config["s3_bucket"]
S3_REGION = _config["s3_region"]
S3_ENABLED = _config["s3_enabled"]
S3_UPLOAD_ON_SYNC = _config["s3_upload_on_sync"]
MAX_RETRIES = _config["max_retries"]
RETRY_DELAY = _config["retry_delay"]


def get_aws_account_id() -> Optional[str]:
    """获取当前 AWS 账号 ID"""
    try:
        import boto3
        sts = boto3.client('sts')
        response = sts.get_caller_identity()
        return response.get('Account')
    except Exception as e:
        logger.warning(f"Failed to get AWS account ID: {e}")
        return None


class S3SyncManager:
    """管理会话文件到 S3 的同步"""

    def __init__(self, bucket: str = S3_BUCKET, region: str = S3_REGION):
        self.bucket = bucket
        self.region = region
        self._s3_client = None
        self._account_id: Optional[str] = None
        self._initialized = False
        self._upload_cache: Dict[str, str] = {}  # local_path -> s3_uri 缓存
        self._lock = threading.Lock()

    def initialize(self) -> bool:
        """初始化 S3 客户端"""
        try:
            import boto3
            self._s3_client = boto3.client('s3', region_name=self.region)
            self._account_id = get_aws_account_id()

            if not self._account_id:
                logger.error("Cannot get AWS account ID, S3 sync disabled")
                return False

            # 检查桶是否存在，不存在则创建
            self._ensure_bucket_exists()

            self._initialized = True
            logger.info(f"S3SyncManager initialized: s3://{self.bucket}/{self._account_id}/")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize S3SyncManager: {e}")
            return False

    def _ensure_bucket_exists(self):
        """确保 S3 桶存在"""
        try:
            self._s3_client.head_bucket(Bucket=self.bucket)
            logger.debug(f"S3 bucket exists: {self.bucket}")
        except Exception as e:
            # 桶不存在，尝试创建
            logger.info(f"Creating S3 bucket: {self.bucket}")
            try:
                if self.region == 'us-east-1':
                    self._s3_client.create_bucket(Bucket=self.bucket)
                else:
                    self._s3_client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={'LocationConstraint': self.region}
                    )
                logger.info(f"S3 bucket created: {self.bucket}")
            except Exception as create_error:
                logger.warning(f"Failed to create bucket (may already exist): {create_error}")

    def get_s3_prefix(self, session_id: str) -> str:
        """获取会话的 S3 前缀路径"""
        return f"{self._account_id}/sessions/{session_id}"

    def get_s3_uri(self, session_id: str, file_type: str, filename: str) -> str:
        """
        生成 S3 URI

        Args:
            session_id: 会话 ID
            file_type: 文件类型 ("images" 或 "tool-results")
            filename: 文件名

        Returns:
            S3 URI，如 s3://springo/123456789012/sessions/xxx/images/img_abc.png
        """
        prefix = self.get_s3_prefix(session_id)
        return f"s3://{self.bucket}/{prefix}/{file_type}/{filename}"

    def upload_image(self, session_id: str, image_id: str,
                     image_data: bytes, media_type: str = "image/png") -> Optional[str]:
        """
        上传图片到 S3

        Args:
            session_id: 会话 ID
            image_id: 图片 ID
            image_data: 图片二进制数据
            media_type: 媒体类型

        Returns:
            S3 URI 或 None（失败时）
        """
        if not self._initialized:
            if not self.initialize():
                return None

        # 确定文件扩展名
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp"
        }
        ext = ext_map.get(media_type, ".png")
        filename = f"{image_id}{ext}"

        s3_key = f"{self.get_s3_prefix(session_id)}/images/{filename}"
        s3_uri = f"s3://{self.bucket}/{s3_key}"

        # 检查缓存
        cache_key = f"{session_id}/images/{filename}"
        with self._lock:
            if cache_key in self._upload_cache:
                logger.debug(f"Image already uploaded (cached): {s3_uri}")
                return self._upload_cache[cache_key]

        # 上传到 S3
        for attempt in range(MAX_RETRIES):
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=image_data,
                    ContentType=media_type
                )
                logger.info(f"Uploaded image to S3: {s3_uri}")

                # 更新缓存
                with self._lock:
                    self._upload_cache[cache_key] = s3_uri

                return s3_uri
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)

        logger.error(f"Failed to upload image after {MAX_RETRIES} attempts")
        return None

    def upload_image_from_base64(self, session_id: str, image_id: str,
                                  base64_data: str, media_type: str = "image/png") -> Optional[str]:
        """
        从 base64 数据上传图片到 S3

        Args:
            session_id: 会话 ID
            image_id: 图片 ID
            base64_data: base64 编码的图片数据
            media_type: 媒体类型

        Returns:
            S3 URI 或 None
        """
        try:
            image_data = base64.b64decode(base64_data)
            return self.upload_image(session_id, image_id, image_data, media_type)
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None

    def upload_image_from_file(self, session_id: str, local_path: str) -> Optional[str]:
        """
        从本地文件上传图片到 S3

        Args:
            session_id: 会话 ID
            local_path: 本地文件路径

        Returns:
            S3 URI 或 None
        """
        if not os.path.exists(local_path):
            logger.error(f"Image file not found: {local_path}")
            return None

        # 从路径提取 image_id
        filename = os.path.basename(local_path)
        image_id = os.path.splitext(filename)[0]

        # 确定媒体类型
        ext = os.path.splitext(filename)[1].lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(ext, "image/png")

        try:
            with open(local_path, 'rb') as f:
                image_data = f.read()
            return self.upload_image(session_id, image_id, image_data, media_type)
        except Exception as e:
            logger.error(f"Failed to read image file: {e}")
            return None

    def upload_tool_result(self, session_id: str, tool_use_id: str,
                           result_data: Dict[str, Any]) -> Optional[str]:
        """
        上传工具结果到 S3

        Args:
            session_id: 会话 ID
            tool_use_id: 工具调用 ID
            result_data: 工具结果数据

        Returns:
            S3 URI 或 None
        """
        if not self._initialized:
            if not self.initialize():
                return None

        filename = f"{tool_use_id}.json"
        s3_key = f"{self.get_s3_prefix(session_id)}/tool-results/{filename}"
        s3_uri = f"s3://{self.bucket}/{s3_key}"

        # 检查缓存
        cache_key = f"{session_id}/tool-results/{filename}"
        with self._lock:
            if cache_key in self._upload_cache:
                logger.debug(f"Tool result already uploaded (cached): {s3_uri}")
                return self._upload_cache[cache_key]

        # 序列化数据
        try:
            json_data = json.dumps(result_data, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to serialize tool result: {e}")
            return None

        # 上传到 S3
        for attempt in range(MAX_RETRIES):
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=json_data.encode('utf-8'),
                    ContentType="application/json"
                )
                logger.info(f"Uploaded tool result to S3: {s3_uri}")

                with self._lock:
                    self._upload_cache[cache_key] = s3_uri

                return s3_uri
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)

        logger.error(f"Failed to upload tool result after {MAX_RETRIES} attempts")
        return None

    def sync_session_files(self, session_id: str) -> Dict[str, str]:
        """
        同步会话的所有文件到 S3

        扫描本地会话目录，上传所有图片和工具结果文件

        Args:
            session_id: 会话 ID

        Returns:
            本地路径 -> S3 URI 的映射
        """
        if not self._initialized:
            if not self.initialize():
                return {}

        session_dir = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(session_dir):
            logger.warning(f"Session directory not found: {session_dir}")
            return {}

        uploaded: Dict[str, str] = {}

        # 上传图片
        images_dir = os.path.join(session_dir, "images")
        if os.path.exists(images_dir):
            for filename in os.listdir(images_dir):
                if filename.startswith('.'):
                    continue
                local_path = os.path.join(images_dir, filename)
                s3_uri = self.upload_image_from_file(session_id, local_path)
                if s3_uri:
                    uploaded[local_path] = s3_uri

        # 上传工具结果
        tool_results_dir = os.path.join(session_dir, "tool-results")
        if os.path.exists(tool_results_dir):
            for filename in os.listdir(tool_results_dir):
                if not filename.endswith('.json') or filename.startswith('.'):
                    continue
                local_path = os.path.join(tool_results_dir, filename)
                tool_use_id = os.path.splitext(filename)[0]

                try:
                    with open(local_path, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    s3_uri = self.upload_tool_result(session_id, tool_use_id, result_data)
                    if s3_uri:
                        uploaded[local_path] = s3_uri
                except Exception as e:
                    logger.warning(f"Failed to upload tool result {filename}: {e}")

        logger.info(f"Synced {len(uploaded)} files for session {session_id}")
        return uploaded

    def process_message_for_memory(self, session_id: str,
                                    message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理消息，将本地文件引用替换为 S3 URI

        用于在上传到 AgentCore Memory 之前处理消息

        Args:
            session_id: 会话 ID
            message: 原始消息

        Returns:
            处理后的消息（带 S3 URI）
        """
        if not self._initialized:
            if not self.initialize():
                return message

        content = message.get("content")
        if not content:
            return message

        # 处理 content 列表中的各种类型
        if isinstance(content, list):
            processed_content = []
            for block in content:
                if isinstance(block, dict):
                    processed_block = self._process_content_block(session_id, block)
                    processed_content.append(processed_block)
                else:
                    processed_content.append(block)

            return {**message, "content": processed_content}

        return message

    def _process_content_block(self, session_id: str,
                                block: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个内容块，上传文件并替换为 S3 URI"""
        block_type = block.get("type")

        if block_type == "image":
            return self._process_image_block(session_id, block)
        elif block_type == "tool_result":
            return self._process_tool_result_block(session_id, block)

        return block

    def _process_image_block(self, session_id: str,
                              block: Dict[str, Any]) -> Dict[str, Any]:
        """处理图片块，上传到 S3 并添加 S3 URI"""
        source = block.get("source", {})
        source_type = source.get("type")

        # 如果已经有 S3 URI，直接返回
        if block.get("s3_uri"):
            return block

        # 处理 base64 数据
        if source_type == "base64" and source.get("data"):
            image_ref = block.get("_imageRef", {})
            image_id = image_ref.get("image_id", f"img_{int(time.time())}")
            media_type = source.get("media_type", "image/png")

            s3_uri = self.upload_image_from_base64(
                session_id, image_id, source["data"], media_type
            )

            if s3_uri:
                return {**block, "s3_uri": s3_uri}

        # 处理 file_ref 类型
        elif source_type == "file_ref":
            image_ref = source.get("image_ref", {})
            relative_path = image_ref.get("relative_path", "")

            if relative_path:
                local_path = os.path.join(SESSIONS_DIR, session_id, relative_path)
                s3_uri = self.upload_image_from_file(session_id, local_path)

                if s3_uri:
                    return {**block, "s3_uri": s3_uri}

        return block

    def _process_tool_result_block(self, session_id: str,
                                    block: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具结果块，上传到 S3 并添加 S3 URI"""
        # 如果已经有 S3 URI，直接返回
        if block.get("s3_uri"):
            return block

        tool_use_id = block.get("tool_use_id")
        content = block.get("content")

        if not tool_use_id or not content:
            return block

        # 构建结果数据
        result_data = {
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": block.get("is_error", False),
            "timestamp": datetime.utcnow().isoformat()
        }

        s3_uri = self.upload_tool_result(session_id, tool_use_id, result_data)

        if s3_uri:
            return {**block, "s3_uri": s3_uri}

        return block

    def get_stats(self) -> Dict[str, Any]:
        """获取同步统计信息"""
        return {
            "initialized": self._initialized,
            "bucket": self.bucket,
            "region": self.region,
            "account_id": self._account_id,
            "cached_uploads": len(self._upload_cache)
        }


# 全局实例
_s3_manager: Optional[S3SyncManager] = None


def get_s3_manager() -> Optional[S3SyncManager]:
    """获取全局 S3 同步管理器实例"""
    global _s3_manager
    return _s3_manager


def init_s3_sync(bucket: str = None, region: str = None) -> bool:
    """
    初始化 S3 同步

    在应用启动时调用一次。

    Args:
        bucket: S3 桶名 (可选，默认从配置读取)
        region: S3 区域 (可选，默认从配置读取)

    Returns:
        是否成功初始化
    """
    global _s3_manager

    bucket = bucket or S3_BUCKET
    region = region or S3_REGION

    if not S3_ENABLED:
        logger.info("S3 sync is disabled in config")
        return False

    if _s3_manager:
        logger.warning("S3 sync already initialized")
        return True

    _s3_manager = S3SyncManager(bucket, region)
    if _s3_manager.initialize():
        logger.info(f"S3 sync initialized: s3://{bucket}/")
        return True
    else:
        _s3_manager = None
        return False


def shutdown_s3_sync():
    """关闭 S3 同步"""
    global _s3_manager
    if _s3_manager:
        _s3_manager = None
        logger.info("S3 sync shutdown complete")


def get_s3_config() -> Dict[str, Any]:
    """获取当前 S3 配置"""
    return {
        "s3_bucket": S3_BUCKET,
        "s3_region": S3_REGION,
        "s3_enabled": S3_ENABLED,
        "s3_upload_on_sync": S3_UPLOAD_ON_SYNC,
        "config_file": CONFIG_FILE
    }


def create_s3_bucket(region: str, bucket_prefix: str = "springo") -> Dict[str, Any]:
    """
    在指定区域创建 S3 桶

    桶名格式: {bucket_prefix}-{account_id}-{region}
    确保全局唯一且与账号/区域关联

    Args:
        region: 要创建桶的区域
        bucket_prefix: 桶名前缀

    Returns:
        {"success": True, "bucket": "...", "region": "..."} 或
        {"success": False, "error": "..."}
    """
    try:
        import boto3

        # 获取账号 ID
        account_id = get_aws_account_id()
        if not account_id:
            return {"success": False, "error": "Cannot get AWS account ID"}

        # 生成桶名: springo-{account_id}-{region}
        bucket_name = f"{bucket_prefix}-{account_id}-{region}"

        logger.info(f"Creating S3 bucket: {bucket_name} in {region}")

        s3_client = boto3.client('s3', region_name=region)

        # 检查桶是否已存在
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"S3 bucket already exists: {bucket_name}")

            # 桶已存在，保存配置
            config = load_s3_config()
            config['s3_bucket'] = bucket_name
            config['s3_region'] = region
            config['s3_enabled'] = True
            save_s3_config(config)

            return {
                "success": True,
                "bucket": bucket_name,
                "region": region,
                "already_exists": True
            }
        except Exception:
            pass  # 桶不存在，继续创建

        # 创建桶
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )

        logger.info(f"Created S3 bucket: {bucket_name}")

        # 保存配置
        config = load_s3_config()
        config['s3_bucket'] = bucket_name
        config['s3_region'] = region
        config['s3_enabled'] = True
        save_s3_config(config)

        return {
            "success": True,
            "bucket": bucket_name,
            "region": region,
            "already_exists": False
        }

    except Exception as e:
        logger.error(f"Failed to create S3 bucket: {e}")
        return {"success": False, "error": str(e)}
