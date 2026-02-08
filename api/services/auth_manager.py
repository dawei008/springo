"""
AWS Auth Manager for Springo FastAPI
支持 5 种认证方式：AWS_PROFILE, MANUAL_KEYS, SSO, ENV_VARS, ENV_FILE
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.springo")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


class AuthMethod(str, Enum):
    AWS_PROFILE = "aws_profile"
    MANUAL_KEYS = "manual_keys"
    SSO = "sso"
    ENV_VARS = "env_vars"
    ENV_FILE = "env_file"


def _load_config() -> Dict[str, Any]:
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
    return {}


def _save_config(config: Dict[str, Any]) -> bool:
    """保存配置文件"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, ensure_ascii=False, fp=f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def get_aws_config() -> Dict[str, Any]:
    """获取当前 AWS 配置"""
    config = _load_config()
    aws_config = config.get("aws", {})

    # 检测当前激活的认证方式
    active_method = aws_config.get("auth_method", "")

    # 检查环境变量
    env_region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", ""))
    env_profile = os.environ.get("AWS_PROFILE", "")
    env_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")

    has_env_credentials = bool(env_access_key)
    has_profile = bool(env_profile) or bool(aws_config.get("profile", ""))

    # 尝试检测连接状态和身份
    connected = False
    identity = {}
    method = active_method
    try:
        import boto3
        sts = boto3.client('sts')
        caller = sts.get_caller_identity()
        connected = True
        identity = {
            "account": caller.get("Account", ""),
            "arn": caller.get("Arn", ""),
            "user_id": caller.get("UserId", ""),
        }
        # 自动检测认证方式
        if not method:
            if has_env_credentials:
                method = "env_vars"
            elif has_profile:
                method = "aws_profile"
    except Exception:
        pass

    return {
        "auth_method": active_method,
        "method": method,
        "region": aws_config.get("region", env_region or "us-west-2"),
        "profile": aws_config.get("profile", env_profile),
        "has_credentials": has_env_credentials or bool(aws_config.get("access_key_id")),
        "has_profile": has_profile,
        "sso_configured": bool(aws_config.get("sso_start_url")),
        "available_methods": _get_available_methods(),
        "connected": connected,
        "identity": identity,
    }


def _get_available_methods() -> List[str]:
    """获取可用的认证方式"""
    methods = []

    # 检查 AWS_PROFILE
    aws_dir = os.path.expanduser("~/.aws")
    if os.path.exists(os.path.join(aws_dir, "credentials")) or os.path.exists(os.path.join(aws_dir, "config")):
        methods.append(AuthMethod.AWS_PROFILE.value)

    # 手动配置总是可用
    methods.append(AuthMethod.MANUAL_KEYS.value)

    # SSO 总是可用（需要用户配置）
    methods.append(AuthMethod.SSO.value)

    # 检查环境变量
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        methods.append(AuthMethod.ENV_VARS.value)

    # 检查 .env 文件
    env_file = os.path.join(CONFIG_DIR, ".env")
    if os.path.exists(env_file):
        methods.append(AuthMethod.ENV_FILE.value)

    return methods


def set_aws_config(
    auth_method: str = None,
    region: str = None,
    profile: str = None,
    access_key_id: str = None,
    secret_access_key: str = None,
    session_token: str = None,
    sso_start_url: str = None,
    sso_account_id: str = None,
    sso_role_name: str = None,
) -> Dict[str, Any]:
    """设置 AWS 配置

    注意：secret_access_key 不会持久化到磁盘，只在内存中使用。
    """
    config = _load_config()
    aws_config = config.get("aws", {})

    if auth_method:
        aws_config["auth_method"] = auth_method
    if region:
        aws_config["region"] = region
    if profile:
        aws_config["profile"] = profile
    if access_key_id:
        aws_config["access_key_id"] = access_key_id
        # 注意：secret key 不持久化
    if sso_start_url:
        aws_config["sso_start_url"] = sso_start_url
    if sso_account_id:
        aws_config["sso_account_id"] = sso_account_id
    if sso_role_name:
        aws_config["sso_role_name"] = sso_role_name

    config["aws"] = aws_config
    _save_config(config)

    # 如果提供了凭证，设置环境变量（内存中）
    if access_key_id and secret_access_key:
        os.environ["AWS_ACCESS_KEY_ID"] = access_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_access_key
        if session_token:
            os.environ["AWS_SESSION_TOKEN"] = session_token

    if region:
        os.environ["AWS_DEFAULT_REGION"] = region

    if profile:
        os.environ["AWS_PROFILE"] = profile

    logger.info(f"AWS config updated: method={auth_method}, region={region}")
    return get_aws_config()


async def test_aws_connection() -> Dict[str, Any]:
    """测试 AWS 连接"""
    try:
        import boto3

        # 测试 STS
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()

        # 测试 Bedrock
        bedrock_status = "unknown"
        try:
            region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
            bedrock = boto3.client('bedrock', region_name=region)
            models = bedrock.list_foundation_models(byProvider="anthropic")
            model_count = len(models.get("modelSummaries", []))
            bedrock_status = f"ok ({model_count} Anthropic models available)"
        except Exception as e:
            bedrock_status = f"error: {str(e)[:100]}"

        account = identity.get("Account", "")
        return {
            "success": True,
            "valid": True,
            "account": account,
            "account_id": account,
            "arn": identity.get("Arn"),
            "user_id": identity.get("UserId"),
            "bedrock_status": bedrock_status,
        }
    except Exception as e:
        logger.error(f"AWS connection test failed: {e}")
        return {
            "success": False,
            "valid": False,
            "error": str(e),
        }


def get_aws_profiles() -> List[Dict[str, str]]:
    """获取可用的 AWS profiles"""
    profiles = []
    aws_dir = os.path.expanduser("~/.aws")

    # 从 credentials 文件
    creds_file = os.path.join(aws_dir, "credentials")
    if os.path.exists(creds_file):
        try:
            import configparser
            parser = configparser.ConfigParser()
            parser.read(creds_file)
            for section in parser.sections():
                profiles.append({
                    "name": section,
                    "source": "credentials",
                })
        except Exception as e:
            logger.warning(f"Failed to parse credentials file: {e}")

    # 从 config 文件
    config_file = os.path.join(aws_dir, "config")
    if os.path.exists(config_file):
        try:
            import configparser
            parser = configparser.ConfigParser()
            parser.read(config_file)
            existing_names = {p["name"] for p in profiles}
            for section in parser.sections():
                name = section.replace("profile ", "")
                if name not in existing_names:
                    profiles.append({
                        "name": name,
                        "source": "config",
                    })
        except Exception as e:
            logger.warning(f"Failed to parse config file: {e}")

    return profiles


async def start_sso_login(
    start_url: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """启动 SSO 设备授权流程

    Returns:
        {
            "client_id": "...",
            "client_secret": "...",
            "device_code": "...",
            "user_code": "...",
            "verification_uri": "...",
            "verification_uri_complete": "...",
            "interval": 5
        }
    """
    try:
        import boto3

        sso_oidc = boto3.client('sso-oidc', region_name=region)

        # Step 1: Register client
        client_reg = sso_oidc.register_client(
            clientName="springo",
            clientType="public",
            scopes=["sso:account:access"]
        )

        client_id = client_reg["clientId"]
        client_secret = client_reg["clientSecret"]

        # Step 2: Start device authorization
        device_auth = sso_oidc.start_device_authorization(
            clientId=client_id,
            clientSecret=client_secret,
            startUrl=start_url,
        )

        return {
            "success": True,
            "client_id": client_id,
            "client_secret": client_secret,
            "device_code": device_auth["deviceCode"],
            "user_code": device_auth["userCode"],
            "verification_uri": device_auth["verificationUri"],
            "verification_uri_complete": device_auth.get("verificationUriComplete", ""),
            "interval": device_auth.get("interval", 5),
            "expires_in": device_auth.get("expiresIn", 600),
        }
    except Exception as e:
        logger.error(f"SSO login start failed: {e}")
        return {"success": False, "error": str(e)}


async def poll_sso_token(
    client_id: str,
    client_secret: str,
    device_code: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """轮询 SSO token"""
    try:
        import boto3

        sso_oidc = boto3.client('sso-oidc', region_name=region)

        token_response = sso_oidc.create_token(
            clientId=client_id,
            clientSecret=client_secret,
            grantType="urn:ietf:params:oauth:grant-type:device_code",
            deviceCode=device_code,
        )

        return {
            "success": True,
            "access_token": token_response["accessToken"],
            "token_type": token_response.get("tokenType", "Bearer"),
            "expires_in": token_response.get("expiresIn", 28800),
        }
    except Exception as e:
        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
        if error_code == 'AuthorizationPendingException':
            return {"success": False, "pending": True, "error": "Waiting for user authorization"}
        elif error_code == 'SlowDownException':
            return {"success": False, "pending": True, "error": "Slow down, polling too fast"}
        elif error_code == 'ExpiredTokenException':
            return {"success": False, "pending": False, "error": "Device code expired"}
        return {"success": False, "pending": False, "error": str(e)}


async def list_sso_accounts(
    access_token: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """列出 SSO 账户"""
    try:
        import boto3

        sso = boto3.client('sso', region_name=region)
        response = sso.list_accounts(accessToken=access_token)
        accounts = response.get("accountList", [])

        return {
            "success": True,
            "accounts": [
                {
                    "account_id": a.get("accountId", ""),
                    "account_name": a.get("accountName", ""),
                    "email_address": a.get("emailAddress", ""),
                }
                for a in accounts
            ],
        }
    except Exception as e:
        logger.error(f"List SSO accounts failed: {e}")
        return {"success": False, "error": str(e)}


async def list_sso_roles(
    access_token: str,
    account_id: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """列出 SSO 角色"""
    try:
        import boto3

        sso = boto3.client('sso', region_name=region)
        response = sso.list_account_roles(
            accessToken=access_token,
            accountId=account_id,
        )
        roles = response.get("roleList", [])

        return {
            "success": True,
            "roles": [
                {
                    "role_name": r.get("roleName", ""),
                    "account_id": r.get("accountId", ""),
                }
                for r in roles
            ],
        }
    except Exception as e:
        logger.error(f"List SSO roles failed: {e}")
        return {"success": False, "error": str(e)}


async def select_sso_role(
    access_token: str,
    account_id: str,
    role_name: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """选择 SSO 角色并获取临时凭证"""
    try:
        import boto3

        sso = boto3.client('sso', region_name=region)
        creds = sso.get_role_credentials(
            roleName=role_name,
            accountId=account_id,
            accessToken=access_token,
        )
        role_creds = creds.get("roleCredentials", {})

        # Set credentials in environment
        os.environ["AWS_ACCESS_KEY_ID"] = role_creds.get("accessKeyId", "")
        os.environ["AWS_SECRET_ACCESS_KEY"] = role_creds.get("secretAccessKey", "")
        session_token = role_creds.get("sessionToken", "")
        if session_token:
            os.environ["AWS_SESSION_TOKEN"] = session_token

        # Update config
        set_aws_config(
            auth_method="sso",
            sso_account_id=account_id,
            sso_role_name=role_name,
        )

        logger.info(f"SSO role selected: {role_name} in account {account_id}")
        return {
            "success": True,
            "account_id": account_id,
            "role_name": role_name,
            "expires_at": role_creds.get("expiration", 0),
        }
    except Exception as e:
        logger.error(f"Select SSO role failed: {e}")
        return {"success": False, "error": str(e)}


ENV_FILE = os.path.join(CONFIG_DIR, ".env")


def save_env_file(access_key_id: str, secret_access_key: str, region: str = "us-east-1") -> None:
    """保存 AWS 凭证到 .env 文件"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        content = f"""# AWS Credentials for Springo
# This file is auto-generated. Do not edit manually.
AWS_ACCESS_KEY_ID={access_key_id}
AWS_SECRET_ACCESS_KEY={secret_access_key}
AWS_DEFAULT_REGION={region}
"""
        with open(ENV_FILE, 'w') as f:
            f.write(content)
        os.chmod(ENV_FILE, 0o600)
        os.environ['AWS_ACCESS_KEY_ID'] = access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = secret_access_key
        os.environ['AWS_DEFAULT_REGION'] = region
        logger.info("Saved credentials to .env file")
    except Exception as e:
        logger.error(f"Failed to save .env file: {e}")
        raise


__all__ = [
    'get_aws_config', 'set_aws_config', 'test_aws_connection',
    'get_aws_profiles', 'start_sso_login', 'poll_sso_token',
    'list_sso_accounts', 'list_sso_roles', 'select_sso_role',
    'save_env_file', 'AuthMethod',
]
