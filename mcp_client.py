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
            # Prepare environment with extended PATH for bundled apps
            process_env = os.environ.copy()

            # Add common tool paths that might be missing in bundled app
            home = os.path.expanduser("~")
            extra_paths = [
                "/usr/local/bin",
                "/opt/homebrew/bin",
                "/opt/homebrew/sbin",
                f"{home}/.local/bin",
                f"{home}/.npm-global/bin",
                f"{home}/.volta/bin",
                f"{home}/.nvm/versions/node/*/bin",  # NVM
                f"{home}/.asdf/shims",
                f"{home}/.cargo/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ]
            current_path = process_env.get("PATH", "")
            # Prepend extra paths to ensure tools are found
            new_paths = [p for p in extra_paths if os.path.isdir(p) and p not in current_path]
            if new_paths:
                process_env["PATH"] = ":".join(new_paths) + ":" + current_path

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
                    "name": "springo",
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

    def is_alive(self) -> bool:
        """Check if the server process is still alive"""
        if not self.process:
            return False
        return self.process.poll() is None  # None means still running

    def health_check(self) -> bool:
        """Check if the server is healthy and responsive.

        Returns True if server is alive and responsive, False otherwise.
        This detects zombie servers that have died but weren't cleaned up.
        """
        if not self.is_alive():
            self._running = False
            return False
        # Server process is alive
        return True

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

    def call_tool(self, name: str, arguments: Dict[str, Any], timeout: float = 60) -> Dict[str, Any]:
        """Call a tool on this server with robust timeout handling.

        Args:
            name: Tool name
            arguments: Tool arguments
            timeout: Timeout in seconds (default 60)
        """
        import concurrent.futures
        import time

        start_time = time.time()
        logger.info(f"MCP tool call started: {self.name}/{name} (timeout={timeout}s)")

        def _do_call():
            return self._send_request("tools/call", {
                "name": name,
                "arguments": arguments
            }, timeout=timeout)

        # Use ThreadPoolExecutor for hard timeout guarantee
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_call)
                try:
                    result = future.result(timeout=timeout + 5)  # Extra 5s buffer
                    elapsed = time.time() - start_time
                    logger.info(f"MCP tool call completed: {self.name}/{name} ({elapsed:.1f}s)")
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    logger.error(f"MCP tool {name} hard timeout after {elapsed:.1f}s (limit={timeout}s)")
                    return {"error": f"Tool '{name}' timed out after {timeout} seconds. The external service may be slow or unavailable."}
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"MCP tool {name} execution error after {elapsed:.1f}s: {e}")
            return {"error": f"Tool execution failed: {e}"}

        if result and "result" in result:
            return result["result"]
        elif result and "error" in result:
            error_msg = result["error"]
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_msg))
            return {"error": error_msg}
        else:
            return {"error": "Unknown error from MCP server"}

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
    """Manages multiple MCP server connections with lazy loading"""

    def __init__(self, config_path: str = None):
        self.servers: Dict[str, MCPServerConnection] = {}  # Running servers
        self.server_configs: Dict[str, Dict] = {}  # Configured servers (not yet started)
        self.config_path = config_path or os.path.expanduser("~/.springo/mcp_servers.json")
        self._config_loaded = False
        # Tool cache for lazy loading placeholders
        self._tools_cache_path = os.path.expanduser("~/.springo/mcp_tools_cache.json")
        self._tools_cache: Dict[str, List[Dict]] = {}  # server_name -> list of tool definitions
        self._load_tools_cache()

    def _load_tools_cache(self) -> None:
        """Load cached tool definitions from file and register as deferred tools"""
        try:
            if os.path.exists(self._tools_cache_path):
                with open(self._tools_cache_path, 'r') as f:
                    self._tools_cache = json.load(f)
                logger.info(f"Loaded tool cache for {len(self._tools_cache)} servers")
                # Register cached tools as deferred in tool registry
                self._register_cached_tools_as_deferred()
        except Exception as e:
            logger.warning(f"Failed to load tool cache: {e}")
            self._tools_cache = {}

    def _register_cached_tools_as_deferred(self) -> None:
        """Register cached tools as deferred in tool registry for lazy loading"""
        try:
            from tool_registry import get_tool_registry
            registry = get_tool_registry()

            total_tools = 0
            for server_name, tools in self._tools_cache.items():
                for tool in tools:
                    tool_name = tool.get('name', '')
                    description = tool.get('description', '')
                    if tool_name:
                        registry.register_deferred(
                            name=tool_name,
                            description=description,
                            server_name=server_name
                        )
                        total_tools += 1

            if total_tools > 0:
                logger.info(f"Registered {total_tools} cached tools as deferred")
        except Exception as e:
            logger.warning(f"Failed to register cached tools as deferred: {e}")

    def _save_tools_cache(self) -> None:
        """Save tool definitions to cache file"""
        try:
            os.makedirs(os.path.dirname(self._tools_cache_path), exist_ok=True)
            with open(self._tools_cache_path, 'w') as f:
                json.dump(self._tools_cache, f, indent=2)
            logger.debug(f"Saved tool cache for {len(self._tools_cache)} servers")
        except Exception as e:
            logger.warning(f"Failed to save tool cache: {e}")

    def cache_server_tools(self, server_name: str, tools: List[Dict]) -> None:
        """Cache tool definitions for a server"""
        if tools:
            self._tools_cache[server_name] = tools
            self._save_tools_cache()

    def get_cached_tools(self, server_name: str = None) -> Dict[str, List[Dict]]:
        """Get cached tools for a server or all servers"""
        if server_name:
            return {server_name: self._tools_cache.get(server_name, [])}
        return self._tools_cache.copy()

    def load_config(self, lazy: bool = True) -> bool:
        """Load MCP server configuration from file.

        Args:
            lazy: If True, only load config without starting servers (default).
                  If False, start all servers immediately (parallel startup).
        """
        if not os.path.exists(self.config_path):
            # Create default config
            self._create_default_config()
            return False

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            # Store all server configurations
            servers_to_start = []
            for server_config in config.get("servers", []):
                name = server_config.get("name")
                if not name:
                    continue

                # Skip disabled servers
                if not server_config.get("enabled", True):
                    logger.info(f"Skipping disabled MCP server: {name}")
                    # Still store config for UI display
                    self.server_configs[name] = {**server_config, "status": "disabled"}
                    continue

                # Store config for lazy loading
                self.server_configs[name] = {**server_config, "status": "configured"}

                if not lazy and name not in self.servers:
                    servers_to_start.append(server_config)

            self._config_loaded = True

            # Start servers in parallel if not lazy
            if not lazy and servers_to_start:
                self._start_servers_parallel(servers_to_start)

            return True

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return False

    def _start_servers_parallel(self, servers_to_start: List[Dict]) -> None:
        """Start multiple servers in parallel"""
        import concurrent.futures

        def start_server(server_config):
            name = server_config.get("name")
            try:
                server = MCPServerConnection(
                    name=name,
                    command=server_config.get("command"),
                    args=server_config.get("args", []),
                    env=server_config.get("env", {})
                )
                if server.start():
                    return (name, server, None)
                else:
                    return (name, None, "Failed to start")
            except Exception as e:
                return (name, None, str(e))

        # Use ThreadPoolExecutor for parallel startup
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(servers_to_start))) as executor:
            futures = {executor.submit(start_server, cfg): cfg for cfg in servers_to_start}

            for future in concurrent.futures.as_completed(futures):
                name, server, error = future.result()
                if server:
                    self.servers[name] = server
                    if name in self.server_configs:
                        self.server_configs[name]["status"] = "running"
                    # Cache discovered tools for future lazy loading
                    if server.tools:
                        self.cache_server_tools(name, server.get_tool_definitions())
                    logger.info(f"Started MCP server: {name} with {len(server.tools)} tools")
                else:
                    if name in self.server_configs:
                        self.server_configs[name]["status"] = "error"
                        self.server_configs[name]["error"] = error
                    logger.error(f"Failed to start MCP server {name}: {error}")

    def ensure_server_started(self, server_name: str) -> bool:
        """Ensure a specific server is started (lazy loading).

        Returns True if server is running, False otherwise.
        """
        # Already running
        if server_name in self.servers:
            return True

        # Load config if not loaded
        if not self._config_loaded:
            self.load_config(lazy=True)

        # Check if server is configured
        if server_name not in self.server_configs:
            logger.warning(f"Server {server_name} not configured")
            return False

        config = self.server_configs[server_name]

        # Skip disabled servers
        if config.get("status") == "disabled":
            logger.warning(f"Server {server_name} is disabled")
            return False

        # Start the server
        logger.info(f"Lazy loading MCP server: {server_name}")
        try:
            server = MCPServerConnection(
                name=server_name,
                command=config.get("command"),
                args=config.get("args", []),
                env=config.get("env", {})
            )
            if server.start():
                self.servers[server_name] = server
                self.server_configs[server_name]["status"] = "running"
                # Cache discovered tools for future lazy loading
                if server.tools:
                    self.cache_server_tools(server_name, server.get_tool_definitions())
                    # Register tools in deferred registry for tool lookup
                    self._register_server_tools_deferred(server_name, server)
                logger.info(f"Lazy-loaded MCP server: {server_name} with {len(server.tools)} tools")
                return True
            else:
                self.server_configs[server_name]["status"] = "error"
                return False
        except Exception as e:
            logger.error(f"Failed to lazy-load MCP server {server_name}: {e}")
            self.server_configs[server_name]["status"] = "error"
            self.server_configs[server_name]["error"] = str(e)
            return False

    def get_configured_servers(self) -> List[Dict]:
        """Get all configured servers with their status"""
        if not self._config_loaded:
            self.load_config(lazy=True)

        result = []
        for name, config in self.server_configs.items():
            server_info = {
                "name": name,
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "description": config.get("description", ""),
                "enabled": config.get("enabled", True),
                "status": config.get("status", "configured"),
                "running": name in self.servers,
                "tools": len(self.servers[name].tools) if name in self.servers else 0
            }
            if "error" in config:
                server_info["error"] = config["error"]
            result.append(server_info)
        return result

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

    def add_server(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None, description: str = "") -> bool:
        """Add and start an MCP server"""
        if name in self.servers:
            logger.warning(f"Server {name} already exists")
            return False

        server = MCPServerConnection(name, command, args, env)
        if server.start():
            self.servers[name] = server
            # Also update server_configs for UI display
            self.server_configs[name] = {
                "name": name,
                "command": command,
                "args": args or [],
                "env": env or {},
                "description": description,
                "enabled": True,
                "status": "running"
            }
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
        # Also remove from server_configs
        if name in self.server_configs:
            del self.server_configs[name]

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tool definitions from all servers"""
        all_tools = []
        for server in self.servers.values():
            all_tools.extend(server.get_tool_definitions())
        return all_tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 60) -> Dict[str, Any]:
        """Call a tool by its full name (server__toolname).

        Args:
            tool_name: Full tool name in format "server__toolname"
            arguments: Tool arguments
            timeout: Timeout in seconds (default 60)
        """
        if "__" not in tool_name:
            return {"error": f"Invalid tool name format: {tool_name}"}

        server_name, actual_tool_name = tool_name.split("__", 1)

        # Check if server needs to be started (lazy loading)
        if server_name not in self.servers:
            # Try lazy loading
            if not self.ensure_server_started(server_name):
                return {"error": f"Server not found or failed to start: {server_name}"}

        # Check server health and restart if dead
        server = self.servers[server_name]
        if not server.health_check():
            logger.warning(f"Server {server_name} is dead, attempting restart")
            del self.servers[server_name]
            if not self.ensure_server_started(server_name):
                return {"error": f"Server {server_name} died and failed to restart"}
            server = self.servers[server_name]

        return server.call_tool(actual_tool_name, arguments, timeout=timeout)

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
                "alive": server.is_alive(),
                "tools_count": len(server.tools),
                "tools": [t.get("name") for t in server.tools]
            }
        return status

    def health_check_all(self) -> Dict[str, bool]:
        """Check health of all servers and clean up dead ones.

        Returns dict of server_name -> is_healthy.
        Dead servers are removed from self.servers.
        """
        results = {}
        dead_servers = []

        for name, server in self.servers.items():
            healthy = server.health_check()
            results[name] = healthy
            if not healthy:
                dead_servers.append(name)
                logger.warning(f"MCP server {name} is dead, marking for cleanup")

        # Remove dead servers
        for name in dead_servers:
            del self.servers[name]
            if name in self.server_configs:
                self.server_configs[name]["status"] = "stopped"
            logger.info(f"Removed dead MCP server: {name}")

        return results

    def _register_server_tools_deferred(self, server_name: str, server: 'MCPServerConnection'):
        """Register tools from a single server as deferred in the tool registry.

        Called after lazy loading a server to make its tools available for lookup.
        """
        try:
            from tool_registry import get_tool_registry
            registry = get_tool_registry()

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

            logger.info(f"Registered {len(server.tools)} tools from {server_name} as deferred")

        except Exception as e:
            logger.error(f"Failed to register deferred tools for {server_name}: {e}")

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


def initialize_mcp_servers(lazy: bool = True) -> bool:
    """Initialize MCP servers from configuration.

    Args:
        lazy: If True (default), only load config without starting servers.
              Servers will be started on first tool use or explicit start.
              If False, start all servers immediately with parallel startup.
    """
    manager = get_mcp_manager()
    success = manager.load_config(lazy=lazy)

    # Register tools as deferred only if servers were started
    if success and not lazy:
        manager.register_tools_as_deferred()

    return success


def start_all_mcp_servers() -> bool:
    """Start all configured MCP servers (parallel startup).

    Call this when MCP tools are first needed.
    """
    manager = get_mcp_manager()

    # Ensure config is loaded
    if not manager._config_loaded:
        manager.load_config(lazy=True)

    # Get servers that need to be started
    servers_to_start = []
    for name, config in manager.server_configs.items():
        if name not in manager.servers and config.get("status") != "disabled":
            servers_to_start.append(config)

    if servers_to_start:
        manager._start_servers_parallel(servers_to_start)
        manager.register_tools_as_deferred()

    return len(manager.servers) > 0


def get_mcp_tools() -> List[Dict[str, Any]]:
    """Get all tools from MCP servers"""
    return get_mcp_manager().get_all_tools()


def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], timeout: float = 60) -> Dict[str, Any]:
    """Call an MCP tool with timeout protection.

    Args:
        tool_name: Full tool name in format "server__toolname"
        arguments: Tool arguments
        timeout: Timeout in seconds (default 60)

    Returns:
        Tool result or error dict
    """
    return get_mcp_manager().call_tool(tool_name, arguments, timeout=timeout)


def shutdown_mcp_servers():
    """Shutdown all MCP servers"""
    get_mcp_manager().stop_all()
