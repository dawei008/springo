"""Authentication Configuration Manager - 核心认证配置管理器"""

import os
import json
import time
import logging
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import boto3
from botocore.config import Config

from .aws_profiles import list_profiles, get_profile_details, get_profile_credentials, is_sso_profile
from .sso_handler import SSOHandler

logger = logging.getLogger(__name__)


class AuthMethod(Enum):
    """认证方式枚举"""
    AWS_PROFILE = "aws_profile"
    MANUAL_KEYS = "manual_keys"
    SSO = "sso"


@dataclass
class AuthConfig:
    """认证配置数据类"""
    method: AuthMethod = AuthMethod.AWS_PROFILE
    profile_name: Optional[str] = "default"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    region: str = "us-east-1"
    # SSO 相关
    sso_start_url: Optional[str] = None
    sso_region: Optional[str] = None
    sso_account_id: Optional[str] = None
    sso_role_name: Optional[str] = None
    sso_access_token: Optional[str] = None
    sso_token_expiry: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，处理枚举类型"""
        d = asdict(self)
        d['method'] = self.method.value
        # 不保存敏感信息到字典（用于显示）
        if d.get('secret_access_key'):
            d['secret_access_key'] = '***'
        if d.get('sso_access_token'):
            d['sso_access_token'] = '***'
        return d

    def to_save_dict(self) -> Dict[str, Any]:
        """转换为可保存的字典"""
        d = asdict(self)
        d['method'] = self.method.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'AuthConfig':
        """从字典创建"""
        if 'method' in d:
            d['method'] = AuthMethod(d['method'])
        return cls(**d)


class AuthConfigManager:
    """认证配置管理器 - 单例模式"""

    _instance = None
    CONFIG_DIR = Path.home() / '.claude-bedrock-proxy'
    CONFIG_FILE = CONFIG_DIR / 'config.json'

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._config: AuthConfig = AuthConfig()
        self._bedrock_client = None
        self._sso_handler: Optional[SSOHandler] = None
        self._sso_device_auth: Optional[Dict] = None

        # 确保配置目录存在
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # 加载已保存的配置
        self.load_config()

        self._initialized = True

    @property
    def config(self) -> AuthConfig:
        """获取当前配置"""
        return self._config

    def load_config(self) -> AuthConfig:
        """从文件加载配置"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self._config = AuthConfig.from_dict(data)
                    logger.info(f"Loaded config: method={self._config.method.value}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self._config = AuthConfig()

        return self._config

    def save_config(self, config: Optional[AuthConfig] = None) -> None:
        """保存配置到文件"""
        if config:
            self._config = config

        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self._config.to_save_dict(), f, indent=2)
            # 设置文件权限为仅所有者可读写
            os.chmod(self.CONFIG_FILE, 0o600)
            logger.info("Config saved")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

        # 重置 bedrock client，下次调用时重新创建
        self._bedrock_client = None

    def update_config(self, **kwargs) -> None:
        """更新配置的部分字段"""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                if key == 'method' and isinstance(value, str):
                    value = AuthMethod(value)
                setattr(self._config, key, value)

        self.save_config()

    def get_bedrock_client(self):
        """获取配置好的 Bedrock client"""
        # 检查是否需要刷新 SSO 凭证
        if self._config.method == AuthMethod.SSO:
            if self._config.sso_token_expiry and time.time() > self._config.sso_token_expiry - 300:
                logger.info("SSO token expired or expiring soon, need to re-authenticate")
                self._bedrock_client = None

        if self._bedrock_client:
            return self._bedrock_client

        boto_config = Config(
            region_name=self._config.region,
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )

        try:
            if self._config.method == AuthMethod.AWS_PROFILE:
                # 使用 AWS Profile
                session = boto3.Session(profile_name=self._config.profile_name)
                self._bedrock_client = session.client('bedrock-runtime', config=boto_config)

            elif self._config.method == AuthMethod.MANUAL_KEYS:
                # 使用手动输入的 Access Key
                self._bedrock_client = boto3.client(
                    'bedrock-runtime',
                    aws_access_key_id=self._config.access_key_id,
                    aws_secret_access_key=self._config.secret_access_key,
                    aws_session_token=self._config.session_token,
                    config=boto_config
                )

            elif self._config.method == AuthMethod.SSO:
                # 使用 SSO 凭证
                if not self._config.sso_access_token:
                    raise Exception("SSO 未登录，请先完成 SSO 认证")

                # 获取 SSO 临时凭证
                sso_handler = SSOHandler(self._config.sso_region or self._config.region)
                creds = sso_handler.get_role_credentials(
                    self._config.sso_access_token,
                    self._config.sso_account_id,
                    self._config.sso_role_name
                )

                self._bedrock_client = boto3.client(
                    'bedrock-runtime',
                    aws_access_key_id=creds['access_key_id'],
                    aws_secret_access_key=creds['secret_access_key'],
                    aws_session_token=creds['session_token'],
                    config=boto_config
                )

            else:
                # 默认：使用环境变量或默认凭证链
                self._bedrock_client = boto3.client('bedrock-runtime', config=boto_config)

            logger.info(f"Bedrock client created with method: {self._config.method.value}")
            return self._bedrock_client

        except Exception as e:
            logger.error(f"Failed to create Bedrock client: {e}")
            raise

    def validate_credentials(self) -> Dict[str, Any]:
        """验证当前凭证是否有效"""
        try:
            # 使用 STS GetCallerIdentity 验证
            boto_config = Config(
                region_name=self._config.region,
                retries={'max_attempts': 1, 'mode': 'standard'}
            )

            if self._config.method == AuthMethod.AWS_PROFILE:
                session = boto3.Session(profile_name=self._config.profile_name)
                sts = session.client('sts', config=boto_config)

            elif self._config.method == AuthMethod.MANUAL_KEYS:
                sts = boto3.client(
                    'sts',
                    aws_access_key_id=self._config.access_key_id,
                    aws_secret_access_key=self._config.secret_access_key,
                    aws_session_token=self._config.session_token,
                    config=boto_config
                )

            elif self._config.method == AuthMethod.SSO:
                if not self._config.sso_access_token:
                    return {"valid": False, "error": "SSO 未登录"}

                sso_handler = SSOHandler(self._config.sso_region or self._config.region)
                creds = sso_handler.get_role_credentials(
                    self._config.sso_access_token,
                    self._config.sso_account_id,
                    self._config.sso_role_name
                )

                sts = boto3.client(
                    'sts',
                    aws_access_key_id=creds['access_key_id'],
                    aws_secret_access_key=creds['secret_access_key'],
                    aws_session_token=creds['session_token'],
                    config=boto_config
                )
            else:
                sts = boto3.client('sts', config=boto_config)

            identity = sts.get_caller_identity()
            return {
                "valid": True,
                "account": identity['Account'],
                "arn": identity['Arn'],
                "user_id": identity['UserId']
            }

        except Exception as e:
            logger.error(f"Credential validation failed: {e}")
            return {"valid": False, "error": str(e)}

    def get_current_identity(self) -> Dict[str, Any]:
        """获取当前 AWS 身份信息"""
        return self.validate_credentials()

    def get_status(self) -> Dict[str, Any]:
        """获取当前认证状态"""
        status = {
            "method": self._config.method.value,
            "region": self._config.region,
            "configured": False,
            "connected": False
        }

        if self._config.method == AuthMethod.AWS_PROFILE:
            status["profile_name"] = self._config.profile_name
            status["configured"] = bool(self._config.profile_name)

        elif self._config.method == AuthMethod.MANUAL_KEYS:
            status["access_key_id"] = self._config.access_key_id[:8] + "***" if self._config.access_key_id else None
            status["configured"] = bool(self._config.access_key_id and self._config.secret_access_key)

        elif self._config.method == AuthMethod.SSO:
            status["sso_start_url"] = self._config.sso_start_url
            status["sso_account_id"] = self._config.sso_account_id
            status["sso_role_name"] = self._config.sso_role_name
            status["configured"] = bool(self._config.sso_access_token)

            if self._config.sso_token_expiry:
                status["token_expires_at"] = self._config.sso_token_expiry
                status["token_valid"] = time.time() < self._config.sso_token_expiry

        # 验证连接
        if status["configured"]:
            validation = self.validate_credentials()
            status["connected"] = validation.get("valid", False)
            if validation.get("valid"):
                status["identity"] = {
                    "account": validation.get("account"),
                    "arn": validation.get("arn")
                }
            else:
                status["error"] = validation.get("error")

        return status

    # ==================== SSO 相关方法 ====================

    def start_sso_login(self, start_url: str, sso_region: Optional[str] = None) -> Dict:
        """启动 SSO 登录流程"""
        region = sso_region or self._config.region
        self._sso_handler = SSOHandler(region)

        self._sso_device_auth = self._sso_handler.start_device_authorization(start_url)

        # 保存 SSO 配置
        self._config.sso_start_url = start_url
        self._config.sso_region = region

        return self._sso_device_auth

    def poll_sso_login(self) -> Dict:
        """轮询 SSO 登录状态"""
        if not self._sso_handler or not self._sso_device_auth:
            raise Exception("请先调用 start_sso_login")

        result = self._sso_handler.poll_for_token(self._sso_device_auth['device_code'])

        if result:
            # 登录成功，保存 token
            self._config.sso_access_token = result['access_token']
            self._config.sso_token_expiry = result['expires_at']
            return {"status": "success", "message": "SSO 登录成功"}

        return {"status": "pending", "message": "等待用户授权..."}

    def list_sso_accounts(self) -> list:
        """列出 SSO 可用账户"""
        if not self._config.sso_access_token:
            raise Exception("请先完成 SSO 登录")

        sso_handler = SSOHandler(self._config.sso_region or self._config.region)
        return sso_handler.list_accounts(self._config.sso_access_token)

    def list_sso_roles(self, account_id: str) -> list:
        """列出指定账户的可用角色"""
        if not self._config.sso_access_token:
            raise Exception("请先完成 SSO 登录")

        sso_handler = SSOHandler(self._config.sso_region or self._config.region)
        return sso_handler.list_account_roles(self._config.sso_access_token, account_id)

    def select_sso_role(self, account_id: str, role_name: str) -> None:
        """选择 SSO 角色"""
        self._config.sso_account_id = account_id
        self._config.sso_role_name = role_name
        self._config.method = AuthMethod.SSO
        self.save_config()
        # 重置 client
        self._bedrock_client = None
