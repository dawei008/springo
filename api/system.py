"""
System Blueprint
Health check and system endpoints
"""

import json
import logging
from flask import Blueprint, Response, request

from mcp_tools import set_working_dir, get_working_dir
from .shared import json_response

logger = logging.getLogger(__name__)

system_bp = Blueprint('system', __name__)


@system_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return json_response({"status": "healthy", "backend": "bedrock"})


@system_bp.route('/', methods=['GET'])
def index():
    """API information"""
    return json_response({
        "name": "Springo API",
        "version": "1.0.0",
        "backend": "AWS Bedrock",
        "endpoints": {
            "/v1/messages": "Claude Messages API",
            "/v1/messages-auto": "Auto tool execution API",
            "/v1/models": "List available models",
            "/v1/context/*": "Context management",
            "/v1/sessions/*": "Session management",
            "/v1/tools/*": "Tool management",
            "/v1/skills/*": "Skill management",
            "/v1/mcp/*": "MCP server management",
            "/health": "Health check"
        }
    })


@system_bp.route('/v1/config/working-dir', methods=['GET', 'POST'])
def config_working_dir():
    """Get or set working directory"""
    try:
        if request.method == 'POST':
            data = request.get_json()
            path = data.get('path', '')
            set_working_dir(path)
            return json_response({"success": True, "path": get_working_dir()})
        else:
            return json_response({"path": get_working_dir()})
    except Exception as e:
        logger.error(f"Config working-dir error: {e}")
        return json_response({"error": str(e)}, status=500)


@system_bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def catch_all(path):
    """Catch-all for unknown routes"""
    return json_response({"error": f"Unknown endpoint: /{path}"}, status=404)
