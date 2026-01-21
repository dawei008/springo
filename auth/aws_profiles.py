"""AWS Profile Parser - 解析 ~/.aws/credentials 和 ~/.aws/config"""

import os
import configparser
from pathlib import Path
from typing import List, Dict, Optional


def get_aws_credentials_path() -> Path:
    """获取 AWS credentials 文件路径"""
    return Path.home() / '.aws' / 'credentials'


def get_aws_config_path() -> Path:
    """获取 AWS config 文件路径"""
    return Path.home() / '.aws' / 'config'


def list_profiles() -> List[Dict]:
    """
    列出所有可用的 AWS Profiles

    Returns:
        List[Dict]: 包含 profile 信息的列表
        [{"name": "default", "has_credentials": True, "has_sso": False, "region": "us-east-1"}, ...]
    """
    profiles = {}

    # 解析 credentials 文件
    credentials_path = get_aws_credentials_path()
    if credentials_path.exists():
        creds_parser = configparser.ConfigParser()
        creds_parser.read(credentials_path)

        for section in creds_parser.sections():
            profile_name = section
            profiles[profile_name] = {
                "name": profile_name,
                "has_credentials": True,
                "has_sso": False,
                "region": None,
                "sso_start_url": None,
                "sso_region": None,
                "sso_account_id": None,
                "sso_role_name": None
            }

    # 解析 config 文件
    config_path = get_aws_config_path()
    if config_path.exists():
        config_parser = configparser.ConfigParser()
        config_parser.read(config_path)

        for section in config_parser.sections():
            # config 文件中的 profile 格式: [profile xxx] 或 [default]
            if section.startswith('profile '):
                profile_name = section[8:]  # 去掉 "profile " 前缀
            else:
                profile_name = section

            if profile_name not in profiles:
                profiles[profile_name] = {
                    "name": profile_name,
                    "has_credentials": False,
                    "has_sso": False,
                    "region": None,
                    "sso_start_url": None,
                    "sso_region": None,
                    "sso_account_id": None,
                    "sso_role_name": None
                }

            # 获取 region
            if config_parser.has_option(section, 'region'):
                profiles[profile_name]["region"] = config_parser.get(section, 'region')

            # 检查是否为 SSO profile
            if config_parser.has_option(section, 'sso_start_url'):
                profiles[profile_name]["has_sso"] = True
                profiles[profile_name]["sso_start_url"] = config_parser.get(section, 'sso_start_url')

                if config_parser.has_option(section, 'sso_region'):
                    profiles[profile_name]["sso_region"] = config_parser.get(section, 'sso_region')
                if config_parser.has_option(section, 'sso_account_id'):
                    profiles[profile_name]["sso_account_id"] = config_parser.get(section, 'sso_account_id')
                if config_parser.has_option(section, 'sso_role_name'):
                    profiles[profile_name]["sso_role_name"] = config_parser.get(section, 'sso_role_name')

    # 转换为列表并排序，default 排在最前面
    result = list(profiles.values())
    result.sort(key=lambda x: (0 if x['name'] == 'default' else 1, x['name']))

    return result


def get_profile_details(profile_name: str) -> Optional[Dict]:
    """
    获取指定 profile 的详细信息

    Args:
        profile_name: Profile 名称

    Returns:
        Dict 或 None: Profile 详情
    """
    profiles = list_profiles()
    for profile in profiles:
        if profile['name'] == profile_name:
            return profile
    return None


def is_sso_profile(profile_name: str) -> bool:
    """
    判断指定 profile 是否为 SSO profile

    Args:
        profile_name: Profile 名称

    Returns:
        bool: 是否为 SSO profile
    """
    profile = get_profile_details(profile_name)
    if profile:
        return profile.get('has_sso', False)
    return False


def get_profile_credentials(profile_name: str) -> Optional[Dict]:
    """
    获取指定 profile 的凭证（仅限非 SSO profile）

    Args:
        profile_name: Profile 名称

    Returns:
        Dict 或 None: {"access_key_id": "...", "secret_access_key": "...", "session_token": "..."}
    """
    credentials_path = get_aws_credentials_path()
    if not credentials_path.exists():
        return None

    creds_parser = configparser.ConfigParser()
    creds_parser.read(credentials_path)

    if profile_name not in creds_parser.sections():
        return None

    result = {}
    if creds_parser.has_option(profile_name, 'aws_access_key_id'):
        result['access_key_id'] = creds_parser.get(profile_name, 'aws_access_key_id')
    if creds_parser.has_option(profile_name, 'aws_secret_access_key'):
        result['secret_access_key'] = creds_parser.get(profile_name, 'aws_secret_access_key')
    if creds_parser.has_option(profile_name, 'aws_session_token'):
        result['session_token'] = creds_parser.get(profile_name, 'aws_session_token')

    return result if result else None
