"""Configuration UI Routes - Flask Blueprint for config UI"""

import logging
from flask import Blueprint, request, Response, render_template, jsonify
import json

from auth.config_manager import AuthConfigManager, AuthMethod, AuthConfig
from auth.aws_profiles import list_profiles

logger = logging.getLogger(__name__)

config_bp = Blueprint('config', __name__, url_prefix='/config',
                      template_folder='templates',
                      static_folder='../static')

# 获取认证管理器实例
auth_manager = AuthConfigManager()


@config_bp.route('/')
def settings_page():
    """渲染设置页面"""
    return render_template('config.html')


@config_bp.route('/api/status')
def get_status():
    """获取当前认证状态"""
    try:
        status = auth_manager.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/profiles')
def get_profiles():
    """获取可用的 AWS Profiles 列表"""
    try:
        profiles = list_profiles()
        return jsonify({"profiles": profiles})
    except Exception as e:
        logger.error(f"Failed to list profiles: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/save', methods=['POST'])
def save_config():
    """保存认证配置"""
    try:
        data = request.get_json()
        method = data.get('method')

        if method == 'aws_profile':
            config = AuthConfig(
                method=AuthMethod.AWS_PROFILE,
                profile_name=data.get('profile_name', 'default'),
                region=data.get('region', 'us-east-1')
            )
        elif method == 'manual_keys':
            config = AuthConfig(
                method=AuthMethod.MANUAL_KEYS,
                access_key_id=data.get('access_key_id'),
                secret_access_key=data.get('secret_access_key'),
                session_token=data.get('session_token'),
                region=data.get('region', 'us-east-1')
            )
        elif method == 'sso':
            # SSO 配置通过 SSO 流程保存，这里只更新基本信息
            current = auth_manager.config
            config = AuthConfig(
                method=AuthMethod.SSO,
                sso_start_url=data.get('sso_start_url', current.sso_start_url),
                sso_region=data.get('sso_region', current.sso_region),
                sso_account_id=data.get('sso_account_id', current.sso_account_id),
                sso_role_name=data.get('sso_role_name', current.sso_role_name),
                sso_access_token=current.sso_access_token,
                sso_token_expiry=current.sso_token_expiry,
                region=data.get('region', 'us-east-1')
            )
        else:
            return jsonify({"error": f"未知的认证方式: {method}"}), 400

        auth_manager.save_config(config)
        return jsonify({"status": "ok", "message": "配置已保存"})

    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/test')
def test_connection():
    """测试当前配置的连接"""
    try:
        result = auth_manager.validate_credentials()
        if result.get('valid'):
            return jsonify({
                "status": "ok",
                "message": "连接成功",
                "identity": {
                    "account": result.get('account'),
                    "arn": result.get('arn'),
                    "user_id": result.get('user_id')
                }
            })
        else:
            return jsonify({
                "status": "error",
                "message": "连接失败",
                "error": result.get('error')
            }), 400
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


# ==================== SSO 相关路由 ====================

@config_bp.route('/api/sso/start', methods=['POST'])
def start_sso():
    """启动 SSO 登录流程"""
    try:
        data = request.get_json()
        start_url = data.get('start_url')
        sso_region = data.get('sso_region')

        if not start_url:
            return jsonify({"error": "请提供 SSO Start URL"}), 400

        result = auth_manager.start_sso_login(start_url, sso_region)
        return jsonify({
            "status": "ok",
            "user_code": result['user_code'],
            "verification_uri": result['verification_uri'],
            "verification_uri_complete": result['verification_uri_complete'],
            "expires_in": result['expires_in'],
            "interval": result['interval']
        })
    except Exception as e:
        logger.error(f"Failed to start SSO: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/sso/poll', methods=['POST'])
def poll_sso():
    """轮询 SSO 登录状态"""
    try:
        result = auth_manager.poll_sso_login()
        return jsonify(result)
    except Exception as e:
        logger.error(f"SSO poll failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@config_bp.route('/api/sso/accounts')
def list_sso_accounts():
    """列出 SSO 可用账户"""
    try:
        accounts = auth_manager.list_sso_accounts()
        return jsonify({"accounts": accounts})
    except Exception as e:
        logger.error(f"Failed to list SSO accounts: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/sso/roles/<account_id>')
def list_sso_roles(account_id):
    """列出指定账户的可用角色"""
    try:
        roles = auth_manager.list_sso_roles(account_id)
        return jsonify({"roles": roles})
    except Exception as e:
        logger.error(f"Failed to list SSO roles: {e}")
        return jsonify({"error": str(e)}), 500


@config_bp.route('/api/sso/select', methods=['POST'])
def select_sso_role():
    """选择 SSO 账户和角色"""
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        role_name = data.get('role_name')

        if not account_id or not role_name:
            return jsonify({"error": "请选择账户和角色"}), 400

        auth_manager.select_sso_role(account_id, role_name)
        return jsonify({"status": "ok", "message": "已选择 SSO 角色"})
    except Exception as e:
        logger.error(f"Failed to select SSO role: {e}")
        return jsonify({"error": str(e)}), 500
