"""
ACP Tool Bridge
Executes Springo tools within ACP context.
Bridges tool calls between the ACP protocol and Springo's tool manager.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AcpToolBridge:
    """Executes Springo tools within ACP context, using IDE fs/terminal when needed."""

    def __init__(self):
        self._ide_capabilities: Dict[str, bool] = {}

    def set_ide_capabilities(self, caps: Dict[str, Any]):
        """Store IDE client capabilities for routing decisions."""
        self._ide_capabilities = {
            "fs_read": bool(caps.get("fs", {}).get("readTextFile", False)),
            "fs_write": bool(caps.get("fs", {}).get("writeTextFile", False)),
            "terminal": bool(caps.get("terminal", {}).get("executeCommand", False)),
        }

    async def execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session: Dict[str, Any],
        ide_request_fn=None,
    ) -> Dict[str, Any]:
        """Execute a tool call, routing to IDE or Springo as appropriate.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Tool arguments
            session: ACP session state dict
            ide_request_fn: Async function to send JSON-RPC requests to the IDE client
        """
        # Route file read/write to IDE if it supports fs operations
        if tool_name in ("read_file", "read_files") and self._ide_capabilities.get("fs_read") and ide_request_fn:
            return await self._ide_fs_read(tool_input, ide_request_fn)

        if tool_name == "write_file" and self._ide_capabilities.get("fs_write") and ide_request_fn:
            return await self._ide_fs_write(tool_input, ide_request_fn)

        if tool_name == "execute_command" and self._ide_capabilities.get("terminal") and ide_request_fn:
            return await self._ide_terminal(tool_input, ide_request_fn)

        # Default: execute via Springo's tool manager
        return self._execute_springo_tool(tool_name, tool_input)

    def _execute_springo_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool via Springo's built-in tool manager."""
        try:
            from mcp_tools.core import execute_tool
            return execute_tool(tool_name, tool_input)
        except Exception as e:
            logger.error(f"Springo tool execution failed: {tool_name}: {e}")
            return {"error": f"Tool execution failed: {e}"}

    async def _ide_fs_read(self, tool_input: Dict[str, Any], ide_request_fn) -> Dict[str, Any]:
        """Read a file via the IDE's fs/read_text_file capability."""
        path = tool_input.get("path", "")
        try:
            result = await ide_request_fn("fs/readTextFile", {"path": path})
            if result and "error" not in result:
                content = result.get("result", {}).get("content", "")
                return {"content": content, "path": path}
            # Fallback to Springo's own read
            return self._execute_springo_tool("read_file", tool_input)
        except Exception as e:
            logger.debug(f"IDE fs/read failed, falling back to Springo: {e}")
            return self._execute_springo_tool("read_file", tool_input)

    async def _ide_fs_write(self, tool_input: Dict[str, Any], ide_request_fn) -> Dict[str, Any]:
        """Write a file via the IDE's fs/write_text_file capability."""
        path = tool_input.get("path", "")
        content = tool_input.get("content", "")
        try:
            result = await ide_request_fn("fs/writeTextFile", {"path": path, "content": content})
            if result and "error" not in result:
                return {"success": True, "path": path}
            return self._execute_springo_tool("write_file", tool_input)
        except Exception as e:
            logger.debug(f"IDE fs/write failed, falling back to Springo: {e}")
            return self._execute_springo_tool("write_file", tool_input)

    async def _ide_terminal(self, tool_input: Dict[str, Any], ide_request_fn) -> Dict[str, Any]:
        """Execute a command via the IDE's terminal capability."""
        command = tool_input.get("command", "")
        cwd = tool_input.get("cwd", "")
        try:
            result = await ide_request_fn("terminal/executeCommand", {
                "command": command,
                "cwd": cwd,
            })
            if result and "error" not in result:
                return result.get("result", {})
            return self._execute_springo_tool("execute_command", tool_input)
        except Exception as e:
            logger.debug(f"IDE terminal failed, falling back to Springo: {e}")
            return self._execute_springo_tool("execute_command", tool_input)

    def get_tool_definitions_for_acp(self) -> list:
        """Get tool definitions formatted for ACP protocol."""
        try:
            from mcp_tools.core import get_tool_definitions
            springo_tools = get_tool_definitions()

            acp_tools = []
            for tool in springo_tools:
                acp_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
                })
            return acp_tools
        except Exception as e:
            logger.error(f"Failed to get tool definitions for ACP: {e}")
            return []
