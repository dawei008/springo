"""AWS SSO Handler - 实现 AWS SSO OIDC 设备授权流程"""

import time
import logging
from typing import Dict, Optional
import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)


class SSOHandler:
    """处理 AWS SSO 认证流程"""

    CLIENT_NAME = "springo"

    def __init__(self, sso_region: str = "us-east-1"):
        """
        初始化 SSO Handler

        Args:
            sso_region: SSO 服务所在的 region
        """
        self.sso_region = sso_region
        self._oidc_client = None
        self._sso_client = None
        self._client_id = None
        self._client_secret = None
        self._client_expiry = 0

    def _get_oidc_client(self):
        """获取 SSO OIDC client"""
        if self._oidc_client is None:
            config = Config(
                region_name=self.sso_region,
                signature_version='v4'
            )
            self._oidc_client = boto3.client(
                'sso-oidc',
                config=config,
                # 不需要凭证来获取设备授权
                aws_access_key_id='',
                aws_secret_access_key='',
            )
        return self._oidc_client

    def _get_sso_client(self):
        """获取 SSO client"""
        if self._sso_client is None:
            config = Config(region_name=self.sso_region)
            self._sso_client = boto3.client(
                'sso',
                config=config,
                aws_access_key_id='',
                aws_secret_access_key='',
            )
        return self._sso_client

    def _register_client(self) -> tuple:
        """
        注册 OIDC 客户端

        Returns:
            (client_id, client_secret)
        """
        # 检查是否已有有效的客户端注册
        if self._client_id and self._client_expiry > time.time():
            return self._client_id, self._client_secret

        oidc = self._get_oidc_client()

        try:
            response = oidc.register_client(
                clientName=self.CLIENT_NAME,
                clientType='public',
                scopes=['sso:account:access']
            )

            self._client_id = response['clientId']
            self._client_secret = response['clientSecret']
            self._client_expiry = response['clientSecretExpiresAt']

            logger.info(f"SSO client registered: {self._client_id}")
            return self._client_id, self._client_secret

        except Exception as e:
            logger.error(f"Failed to register SSO client: {e}")
            raise

    def start_device_authorization(self, start_url: str) -> Dict:
        """
        启动设备授权流程

        Args:
            start_url: SSO Start URL (e.g., https://d-xxxxxxxxxx.awsapps.com/start)

        Returns:
            {
                "device_code": "...",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://device.sso.us-east-1.amazonaws.com/",
                "verification_uri_complete": "https://device.sso.../...",
                "expires_in": 600,
                "interval": 5
            }
        """
        client_id, client_secret = self._register_client()
        oidc = self._get_oidc_client()

        try:
            response = oidc.start_device_authorization(
                clientId=client_id,
                clientSecret=client_secret,
                startUrl=start_url
            )

            return {
                "device_code": response['deviceCode'],
                "user_code": response['userCode'],
                "verification_uri": response['verificationUri'],
                "verification_uri_complete": response['verificationUriComplete'],
                "expires_in": response['expiresIn'],
                "interval": response['interval'],
                "start_url": start_url
            }

        except Exception as e:
            logger.error(f"Failed to start device authorization: {e}")
            raise

    def poll_for_token(self, device_code: str) -> Optional[Dict]:
        """
        轮询检查用户是否已完成授权

        Args:
            device_code: 设备授权码

        Returns:
            成功时返回 access_token 信息，等待时返回 None

        Raises:
            Exception: 授权失败或过期
        """
        client_id, client_secret = self._register_client()
        oidc = self._get_oidc_client()

        try:
            response = oidc.create_token(
                clientId=client_id,
                clientSecret=client_secret,
                grantType='urn:ietf:params:oauth:grant-type:device_code',
                deviceCode=device_code
            )

            return {
                "access_token": response['accessToken'],
                "token_type": response.get('tokenType', 'Bearer'),
                "expires_in": response['expiresIn'],
                "refresh_token": response.get('refreshToken'),
                "expires_at": time.time() + response['expiresIn']
            }

        except oidc.exceptions.AuthorizationPendingException:
            # 用户还没有完成授权，继续等待
            return None

        except oidc.exceptions.SlowDownException:
            # 需要降低轮询频率
            logger.warning("SSO polling too fast, slowing down")
            return None

        except oidc.exceptions.ExpiredTokenException:
            logger.error("Device code expired")
            raise Exception("设备授权码已过期，请重新开始 SSO 登录")

        except oidc.exceptions.AccessDeniedException:
            logger.error("Access denied")
            raise Exception("SSO 登录被拒绝")

        except Exception as e:
            logger.error(f"Failed to poll for token: {e}")
            raise

    def list_accounts(self, access_token: str) -> list:
        """
        列出用户可访问的 AWS 账户

        Args:
            access_token: SSO access token

        Returns:
            账户列表
        """
        sso = self._get_sso_client()

        try:
            accounts = []
            paginator = sso.get_paginator('list_accounts')

            for page in paginator.paginate(accessToken=access_token):
                accounts.extend(page.get('accountList', []))

            return accounts

        except Exception as e:
            logger.error(f"Failed to list accounts: {e}")
            raise

    def list_account_roles(self, access_token: str, account_id: str) -> list:
        """
        列出指定账户中用户可用的角色

        Args:
            access_token: SSO access token
            account_id: AWS 账户 ID

        Returns:
            角色列表
        """
        sso = self._get_sso_client()

        try:
            roles = []
            paginator = sso.get_paginator('list_account_roles')

            for page in paginator.paginate(accessToken=access_token, accountId=account_id):
                roles.extend(page.get('roleList', []))

            return roles

        except Exception as e:
            logger.error(f"Failed to list roles: {e}")
            raise

    def get_role_credentials(self, access_token: str, account_id: str, role_name: str) -> Dict:
        """
        获取指定角色的临时凭证

        Args:
            access_token: SSO access token
            account_id: AWS 账户 ID
            role_name: 角色名称

        Returns:
            {
                "access_key_id": "...",
                "secret_access_key": "...",
                "session_token": "...",
                "expiration": timestamp
            }
        """
        sso = self._get_sso_client()

        try:
            response = sso.get_role_credentials(
                accessToken=access_token,
                accountId=account_id,
                roleName=role_name
            )

            creds = response['roleCredentials']
            return {
                "access_key_id": creds['accessKeyId'],
                "secret_access_key": creds['secretAccessKey'],
                "session_token": creds['sessionToken'],
                "expiration": creds['expiration']
            }

        except Exception as e:
            logger.error(f"Failed to get role credentials: {e}")
            raise
