"""
MCP Client for Springo
Supports connecting to external MCP servers via stdio
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import queue
import logging

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Connection to a single MCP server"""

    def __init__(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process: Optional[subprocess.Popen] = None
        self._message_id = 0
        self._pending_requests: Dict[int, queue.Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self.tools: List[Dict[str, Any]] = []

    def start(self) -> bool:
        """Start the MCP server process"""
        try:
            # Prepare environment
            process_env = os.environ.copy()
            process_env.update(self.env)

            # Start the process
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
                text=True,
                bufsize=1
            )

            self._running = True

            # Start reader thread
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()

            # Initialize the connection
            init_result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "claude-bedrock-proxy",
                    "version": "1.0.0"
                }
            })

            if init_result and "error" not in init_result:
                # Send initialized notification
                self._send_notification("notifications/initialized", {})

                # Discover tools
                self._discover_tools()
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to start MCP server {self.name}: {e}")
            return False

    def stop(self):
        """Stop the MCP server process"""
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None

    def _send_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 30) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request and wait for response"""
        if not self.process or not self._running:
            return {"error": "Server not running"}

        self._message_id += 1
        msg_id = self._message_id

        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method
        }
        if params:
            request["params"] = params

        # Create response queue
        response_queue = queue.Queue()
        self._pending_requests[msg_id] = response_queue

        try:
            # Send request
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str)
            self.process.stdin.flush()

            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                return response
            except queue.Empty:
                return {"error": "Request timed out"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            self._pending_requests.pop(msg_id, None)

    def _send_notification(self, method: str, params: Dict[str, Any] = None):
        """Send a JSON-RPC notification (no response expected)"""
        if not self.process or not self._running:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params:
            notification["params"] = params

        try:
            notification_str = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_str)
            self.process.stdin.flush()
        except:
            pass

    def _read_responses(self):
        """Reader thread to process responses from the server"""
        while self._running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break

                try:
                    response = json.loads(line.strip())

                    # Check if this is a response to a pending request
                    msg_id = response.get("id")
                    if msg_id and msg_id in self._pending_requests:
                        self._pending_requests[msg_id].put(response)
                    else:
                        # Handle notification or other message
                        logger.debug(f"MCP notification from {self.name}: {response}")

                except json.JSONDecodeError:
                    pass

            except Exception as e:
                if self._running:
                    logger.error(f"Error reading from MCP server {self.name}: {e}")
                break

    def _discover_tools(self):
        """Discover available tools from the server"""
        result = self._send_request("tools/list", {})

        if result and "result" in result:
            self.tools = result["result"].get("tools", [])
            logger.info(f"Discovered {len(self.tools)} tools from {self.name}")
        else:
            self.tools = []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on this server"""
        # Use 40 second timeout for tool calls (slightly less than frontend's 45s)
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        }, timeout=40)

        if result and "result" in result:
            return result["result"]
        elif result and "error" in result:
            return {"error": result["error"]}
        else:
            return {"error": "Unknown error"}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions in Claude format"""
        definitions = []
        for tool in self.tools:
            definitions.append({
                "name": f"{self.name}__{tool['name']}",  # Prefix with server name
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            })
        return definitions


class MCPManager:
    """Manages multiple MCP server connections"""

    def __init__(self, config_path: str = None):
        self.servers: Dict[str, MCPServerConnection] = {}
        self.config_path = config_path or os.path.expanduser("~/.springo/mcp_servers.json")

    def load_config(self) -> bool:
        """Load MCP server configuration from file"""
        if not os.path.exists(self.config_path):
            # Create default config
            self._create_default_config()
            return False

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            for server_config in config.get("servers", []):
                name = server_config.get("name")
                # Skip disabled servers
                if not server_config.get("enabled", True):
                    logger.info(f"Skipping disabled MCP server: {name}")
                    continue
                if name and name not in self.servers:
                    self.add_server(
                        name=name,
                        command=server_config.get("command"),
                        args=server_config.get("args", []),
                        env=server_config.get("env", {})
                    )

            return True

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return False

    def _create_default_config(self):
        """Create default configuration file"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        default_config = {
            "servers": [
                {
                    "name": "filesystem",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.expanduser("~")],
                    "env": {},
                    "enabled": False,
                    "description": "MCP Filesystem server for file operations"
                },
                {
                    "name": "github",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "your-token-here"},
                    "enabled": False,
                    "description": "MCP GitHub server for repository operations"
                }
            ]
        }

        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

        logger.info(f"Created default MCP config at {self.config_path}")

    def add_server(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None) -> bool:
        """Add and start an MCP server"""
        if name in self.servers:
            logger.warning(f"Server {name} already exists")
            return False

        server = MCPServerConnection(name, command, args, env)
        if server.start():
            self.servers[name] = server
            logger.info(f"Started MCP server: {name}")
            return True
        else:
            logger.error(f"Failed to start MCP server: {name}")
            return False

    def remove_server(self, name: str):
        """Stop and remove an MCP server"""
        if name in self.servers:
            self.servers[name].stop()
            del self.servers[name]

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tool definitions from all servers"""
        all_tools = []
        for server in self.servers.values():
            all_tools.extend(server.get_tool_definitions())
        return all_tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by its full name (server__toolname)"""
        if "__" not in tool_name:
            return {"error": f"Invalid tool name format: {tool_name}"}

        server_name, actual_tool_name = tool_name.split("__", 1)

        if server_name not in self.servers:
            return {"error": f"Server not found: {server_name}"}

        return self.servers[server_name].call_tool(actual_tool_name, arguments)

    def stop_all(self):
        """Stop all MCP servers"""
        for name in list(self.servers.keys()):
            self.remove_server(name)

    def get_status(self) -> Dict[str, Any]:
        """Get status of all servers"""
        status = {}
        for name, server in self.servers.items():
            status[name] = {
                "running": server._running,
                "tools_count": len(server.tools),
                "tools": [t.get("name") for t in server.tools]
            }
        return status

    def register_tools_as_deferred(self):
        """Register all MCP tools as deferred in the tool registry (lazy loading)"""
        try:
            from tool_registry import get_tool_registry
            registry = get_tool_registry()

            for server_name, server in self.servers.items():
                for tool in server.tools:
                    full_name = f"{server_name}__{tool['name']}"
                    description = tool.get("description", "")

                    # Extract keywords from tool name and description
                    keywords = tool['name'].replace('-', ' ').replace('_', ' ').split()

                    registry.register_deferred(
                        name=full_name,
                        description=description,
                        server_name=server_name,
                        keywords=keywords
                    )
                    logger.debug(f"Registered deferred tool: {full_name}")

            logger.info(f"Registered {sum(len(s.tools) for s in self.servers.values())} MCP tools as deferred")

        except Exception as e:
            logger.error(f"Failed to register deferred tools: {e}")


# Singleton instance
_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """Get the singleton MCP manager instance"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


def initialize_mcp_servers() -> bool:
    """Initialize MCP servers from configuration and register tools as deferred"""
    manager = get_mcp_manager()
    success = manager.load_config()

    # Register all discovered tools as deferred (lazy loading)
    if success:
        manager.register_tools_as_deferred()

    return success


def get_mcp_tools() -> List[Dict[str, Any]]:
    """Get all tools from MCP servers"""
    return get_mcp_manager().get_all_tools()


def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call an MCP tool"""
    return get_mcp_manager().call_tool(tool_name, arguments)


def shutdown_mcp_servers():
    """Shutdown all MCP servers"""
    get_mcp_manager().stop_all()
