"""
Tools Blueprint
Tool listing and execution endpoints
"""

import json
import logging
from flask import Blueprint, request

from mcp_tools import get_tool_definitions, execute_tool
from .shared import json_response

logger = logging.getLogger(__name__)

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/v1/tools', methods=['GET'])
def list_tools():
    """List all available tools"""
    try:
        tools = get_tool_definitions()
        return json_response({"tools": tools, "count": len(tools)})
    except Exception as e:
        logger.error(f"List tools error: {e}")
        return json_response({"error": str(e)}, status=500)


@tools_bp.route('/v1/tools/execute', methods=['POST'])
def execute_tool_endpoint():
    """Execute a specific tool"""
    try:
        data = request.get_json()
        tool_name = data.get('name')
        tool_input = data.get('input', {})

        if not tool_name:
            return json_response({"error": "Tool name is required"}, status=400)

        result = execute_tool(tool_name, tool_input)

        # Truncate result if too large
        result_str = json.dumps(result)
        if len(result_str) > 100000:
            result = {
                "truncated": True,
                "message": "Result too large, truncated",
                "partial_result": result_str[:100000]
            }

        return json_response({"result": result, "tool": tool_name})

    except Exception as e:
        logger.error(f"Execute tool error: {e}")
        return json_response({"error": str(e)}, status=500)
