"""
MCP Blueprint
External MCP server management endpoints
"""

import json
import logging
from flask import Blueprint, request

from mcp_client import (
    get_mcp_manager,
    initialize_mcp_servers,
    get_mcp_tools,
    shutdown_mcp_servers,
)
from tool_registry import get_tool_registry
from .shared import json_response

logger = logging.getLogger(__name__)

mcp_bp = Blueprint('mcp', __name__)


@mcp_bp.route('/v1/mcp/servers', methods=['GET'])
def list_mcp_servers():
    """List configured MCP servers"""
    try:
        manager = get_mcp_manager()
        servers = manager.list_servers()
        return json_response({"servers": servers})
    except Exception as e:
        logger.error(f"List MCP servers error: {e}")
        return json_response({"error": str(e)}, status=500)


@mcp_bp.route('/v1/mcp/servers', methods=['POST'])
def add_mcp_server():
    """Add a new MCP server"""
    try:
        data = request.get_json()
        name = data.get('name')
        config = data.get('config', {})

        if not name:
            return json_response({"error": "Server name is required"}, status=400)

        manager = get_mcp_manager()
        success = manager.add_server(name, config)

        if success:
            return json_response({"success": True, "name": name})
        else:
            return json_response({"error": "Failed to add server"}, status=500)

    except Exception as e:
        logger.error(f"Add MCP server error: {e}")
        return json_response({"error": str(e)}, status=500)


@mcp_bp.route('/v1/mcp/servers/<server_name>', methods=['DELETE'])
def remove_mcp_server(server_name: str):
    """Remove an MCP server"""
    try:
        manager = get_mcp_manager()
        success = manager.remove_server(server_name)

        if success:
            return json_response({"success": True})
        else:
            return json_response({"error": "Server not found"}, status=404)

    except Exception as e:
        logger.error(f"Remove MCP server error: {e}")
        return json_response({"error": str(e)}, status=500)


@mcp_bp.route('/v1/mcp/tools', methods=['GET'])
def list_mcp_tools():
    """List tools from MCP servers"""
    try:
        registry = get_tool_registry()

        # Get active and deferred tools
        active = registry.get_active_tools()
        deferred = registry.get_deferred_tools()

        return json_response({
            "active_tools": active,
            "deferred_tools": deferred,
            "active_count": len(active),
            "deferred_count": len(deferred)
        })
    except Exception as e:
        logger.error(f"List MCP tools error: {e}")
        return json_response({"error": str(e)}, status=500)


@mcp_bp.route('/v1/mcp/initialize', methods=['POST'])
def init_mcp():
    """Initialize MCP servers"""
    try:
        initialize_mcp_servers()
        return json_response({"success": True, "message": "MCP servers initialized"})
    except Exception as e:
        logger.error(f"Initialize MCP error: {e}")
        return json_response({"error": str(e)}, status=500)
