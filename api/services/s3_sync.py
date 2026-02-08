"""
S3 Sync Module for Springo FastAPI

上传会话文件（图片、工具结果等）到 S3
S3 结构: s3://springo/{account-id}/sessions/{session_id}/images|tool-results/...
"""

import os
import json
import time
import base64
import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.springo")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SESSIONS_DIR = os.path.join(CONFIG_DIR, "sessions")

DEFAULT_S3_CONFIG = {
    "s3_bucket": "springo",
    "s3_region": "",
    "s3_enabled": True,
    "s3_upload_on_sync": True,
    "max_retries": 3,
    "retry_delay": 2,
}


def _get_memory_region() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f).get("memory", {}).get("memory_region", "us-west-2")
        except Exception:
            pass
    return "us-west-2"


def load_s3_config() -> Dict[str, Any]:
    config = DEFAULT_S3_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f).get("s3", {}))
        except Exception as e:
            logger.warning(f"Failed to load S3 config: {e}")
    if not config.get("s3_region"):
        config["s3_region"] = _get_memory_region()
    env_mappings = {
        "SPRINGO_S3_BUCKET": ("s3_bucket", str),
        "SPRINGO_S3_REGION": ("s3_region", str),
        "SPRINGO_S3_ENABLED": ("s3_enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "SPRINGO_S3_UPLOAD_ON_SYNC": ("s3_upload_on_sync", lambda v: v.lower() in ("true", "1", "yes")),
    }
    for env_key, (config_key, conv) in env_mappings.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            try:
                config[config_key] = conv(env_val)
            except (ValueError, TypeError):
                pass
    return config


def save_s3_config(s3_config: Dict[str, Any]) -> bool:
    try:
        file_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                file_config = json.load(f)
        file_config["s3"] = s3_config
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(file_config, ensure_ascii=False, fp=f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save S3 config: {e}")
        return False


def get_aws_account_id() -> Optional[str]:
    try:
        import boto3
        return boto3.client('sts').get_caller_identity().get('Account')
    except Exception as e:
        logger.warning(f"Failed to get AWS account ID: {e}")
        return None


class S3SyncManager:
    """管理会话文件到 S3 的同步"""

    def __init__(self, bucket: str = "springo", region: str = "us-west-2"):
        self.bucket = bucket
        self.region = region
        self._s3_client = None
        self._account_id: Optional[str] = None
        self._initialized = False
        self._upload_cache: Dict[str, str] = {}
        self._lock = threading.Lock()

    def initialize(self) -> bool:
        try:
            import boto3
            self._s3_client = boto3.client('s3', region_name=self.region)
            self._account_id = get_aws_account_id()
            if not self._account_id:
                logger.error("Cannot get AWS account ID")
                return False
            self._ensure_bucket_exists()
            self._initialized = True
            logger.info(f"S3SyncManager initialized: s3://{self.bucket}/{self._account_id}/")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize S3SyncManager: {e}")
            return False

    def _ensure_bucket_exists(self):
        try:
            self._s3_client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                if self.region == 'us-east-1':
                    self._s3_client.create_bucket(Bucket=self.bucket)
                else:
                    self._s3_client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={'LocationConstraint': self.region}
                    )
            except Exception as e:
                logger.warning(f"Failed to create bucket: {e}")

    def get_s3_prefix(self, session_id: str) -> str:
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
        if not self._initialized and not self.initialize():
            return None
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
        ext = ext_map.get(media_type, ".png")
        filename = f"{image_id}{ext}"
        s3_key = f"{self.get_s3_prefix(session_id)}/images/{filename}"
        s3_uri = f"s3://{self.bucket}/{s3_key}"
        cache_key = f"{session_id}/images/{filename}"
        with self._lock:
            if cache_key in self._upload_cache:
                return self._upload_cache[cache_key]
        config = load_s3_config()
        for attempt in range(config.get("max_retries", 3)):
            try:
                self._s3_client.put_object(Bucket=self.bucket, Key=s3_key, Body=image_data, ContentType=media_type)
                with self._lock:
                    self._upload_cache[cache_key] = s3_uri
                return s3_uri
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < config.get("max_retries", 3) - 1:
                    time.sleep(config.get("retry_delay", 2))
        return None

    def upload_image_from_base64(self, session_id: str, image_id: str,
                                  base64_data: str, media_type: str = "image/png") -> Optional[str]:
        try:
            return self.upload_image(session_id, image_id, base64.b64decode(base64_data), media_type)
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None

    def upload_image_from_file(self, session_id: str, local_path: str) -> Optional[str]:
        if not os.path.exists(local_path):
            return None
        filename = os.path.basename(local_path)
        image_id = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        media_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".gif": "image/gif", ".webp": "image/webp"}
        try:
            with open(local_path, 'rb') as f:
                return self.upload_image(session_id, image_id, f.read(), media_map.get(ext, "image/png"))
        except Exception as e:
            logger.error(f"Failed to read image: {e}")
            return None

    def upload_tool_result(self, session_id: str, tool_use_id: str,
                           result_data: Dict[str, Any]) -> Optional[str]:
        if not self._initialized and not self.initialize():
            return None
        filename = f"{tool_use_id}.json"
        s3_key = f"{self.get_s3_prefix(session_id)}/tool-results/{filename}"
        s3_uri = f"s3://{self.bucket}/{s3_key}"
        cache_key = f"{session_id}/tool-results/{filename}"
        with self._lock:
            if cache_key in self._upload_cache:
                return self._upload_cache[cache_key]
        try:
            json_data = json.dumps(result_data, ensure_ascii=False, indent=2)
        except Exception:
            return None
        config = load_s3_config()
        for attempt in range(config.get("max_retries", 3)):
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket, Key=s3_key,
                    Body=json_data.encode('utf-8'), ContentType="application/json"
                )
                with self._lock:
                    self._upload_cache[cache_key] = s3_uri
                return s3_uri
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < config.get("max_retries", 3) - 1:
                    time.sleep(config.get("retry_delay", 2))
        return None

    def sync_session_files(self, session_id: str) -> Dict[str, str]:
        if not self._initialized and not self.initialize():
            return {}
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(session_dir):
            return {}
        uploaded: Dict[str, str] = {}
        images_dir = os.path.join(session_dir, "images")
        if os.path.exists(images_dir):
            for f in os.listdir(images_dir):
                if not f.startswith('.'):
                    path = os.path.join(images_dir, f)
                    uri = self.upload_image_from_file(session_id, path)
                    if uri:
                        uploaded[path] = uri
        tool_results_dir = os.path.join(session_dir, "tool-results")
        if os.path.exists(tool_results_dir):
            for f in os.listdir(tool_results_dir):
                if f.endswith('.json') and not f.startswith('.'):
                    path = os.path.join(tool_results_dir, f)
                    tool_id = os.path.splitext(f)[0]
                    try:
                        with open(path, 'r') as fh:
                            data = json.load(fh)
                        uri = self.upload_tool_result(session_id, tool_id, data)
                        if uri:
                            uploaded[path] = uri
                    except Exception as e:
                        logger.warning(f"Failed to upload {f}: {e}")
        return uploaded

    def process_message_for_memory(self, session_id: str, message: Dict) -> Dict:
        """处理消息用于 memory 同步，上传图片和工具结果到 S3"""
        if not self._initialized and not self.initialize():
            return message
        content = message.get("content")
        if not content or not isinstance(content, list):
            return message
        processed = []
        for block in content:
            if isinstance(block, dict):
                processed.append(self._process_content_block(session_id, block))
            else:
                processed.append(block)
        return {**message, "content": processed}

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
        if block.get("s3_uri"):
            return block

        tool_use_id = block.get("tool_use_id")
        content = block.get("content")

        if not tool_use_id or not content:
            return block

        result_data = {
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": block.get("is_error", False),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        s3_uri = self.upload_tool_result(session_id, tool_use_id, result_data)
        if s3_uri:
            return {**block, "s3_uri": s3_uri}

        return block

    def get_stats(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized, "bucket": self.bucket,
            "region": self.region, "account_id": self._account_id,
            "cached_uploads": len(self._upload_cache),
        }


# Singleton
_s3_manager: Optional[S3SyncManager] = None


def get_s3_manager() -> Optional[S3SyncManager]:
    return _s3_manager


def init_s3_sync(bucket: str = None, region: str = None) -> bool:
    global _s3_manager
    config = load_s3_config()
    bucket = bucket or config.get("s3_bucket", "springo")
    region = region or config.get("s3_region", "us-west-2")
    if not config.get("s3_enabled", True):
        return False
    if _s3_manager:
        return True
    _s3_manager = S3SyncManager(bucket, region)
    if _s3_manager.initialize():
        return True
    _s3_manager = None
    return False


def shutdown_s3_sync():
    global _s3_manager
    _s3_manager = None


def get_s3_config() -> Dict[str, Any]:
    config = load_s3_config()
    return {
        "s3_bucket": config.get("s3_bucket", "springo"),
        "s3_region": config.get("s3_region", "us-west-2"),
        "s3_enabled": config.get("s3_enabled", True),
        "s3_upload_on_sync": config.get("s3_upload_on_sync", True),
        "config_file": CONFIG_FILE,
    }


def create_s3_bucket(region: str, bucket_prefix: str = "springo") -> Dict[str, Any]:
    try:
        import boto3
        account_id = get_aws_account_id()
        if not account_id:
            return {"success": False, "error": "Cannot get AWS account ID"}
        bucket_name = f"{bucket_prefix}-{account_id}-{region}"
        s3_client = boto3.client('s3', region_name=region)
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            config = load_s3_config()
            config.update({"s3_bucket": bucket_name, "s3_region": region, "s3_enabled": True})
            save_s3_config(config)
            return {"success": True, "bucket": bucket_name, "region": region, "already_exists": True}
        except Exception:
            pass
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(Bucket=bucket_name,
                                    CreateBucketConfiguration={'LocationConstraint': region})
        config = load_s3_config()
        config.update({"s3_bucket": bucket_name, "s3_region": region, "s3_enabled": True})
        save_s3_config(config)
        return {"success": True, "bucket": bucket_name, "region": region, "already_exists": False}
    except Exception as e:
        return {"success": False, "error": str(e)}


__all__ = [
    'S3SyncManager', 'get_s3_manager', 'init_s3_sync', 'shutdown_s3_sync',
    'get_s3_config', 'save_s3_config', 'load_s3_config', 'create_s3_bucket',
]
