"""
MCP Client for Springo FastAPI
支持连接外部 MCP Servers (stdio)
"""

import asyncio
import json
import os
import subprocess
import threading
import queue
import concurrent.futures
import time
import logging
from typing import Any, Dict, List, Optional

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
        self.instructions: str = ""
        self.server_info: Dict[str, Any] = {}

    def start(self) -> bool:
        """Start the MCP server process"""
        try:
            process_env = os.environ.copy()
            home = os.path.expanduser("~")
            extra_paths = [
                "/usr/local/bin", "/opt/homebrew/bin", "/opt/homebrew/sbin",
                f"{home}/.local/bin", f"{home}/.npm-global/bin",
                f"{home}/.volta/bin", f"{home}/.cargo/bin",
                f"{home}/.asdf/shims",
                "/usr/bin", "/bin", "/usr/sbin", "/sbin",
            ]
            # Add NVM paths (wildcard expansion)
            import glob
            nvm_paths = glob.glob(f"{home}/.nvm/versions/node/*/bin")
            if nvm_paths:
                extra_paths = nvm_paths + extra_paths
            current_path = process_env.get("PATH", "")
            new_paths = [p for p in extra_paths if os.path.isdir(p) and p not in current_path]
            if new_paths:
                process_env["PATH"] = ":".join(new_paths) + ":" + current_path
            process_env.update(self.env)

            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=process_env, text=True, bufsize=1
            )
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()

            init_result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "springo", "version": "2.0.0"}
            })

            if init_result and "error" not in init_result:
                # Store server instructions if provided (used in system prompt)
                result_data = init_result.get("result", {})
                self.instructions = result_data.get("instructions", "")
                self.server_info = result_data.get("serverInfo", {})
                self._send_notification("notifications/initialized", {})
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
            except Exception:
                self.process.kill()
            self.process = None

    def is_alive(self) -> bool:
        if not self.process:
            return False
        return self.process.poll() is None

    def health_check(self) -> bool:
        if not self.is_alive():
            self._running = False
            return False
        return True

    def _send_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 60) -> Optional[Dict]:
        if not self.process or not self._running:
            return {"error": "Server not running"}
        self._message_id += 1
        msg_id = self._message_id
        request = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params:
            request["params"] = params
        response_queue = queue.Queue()
        self._pending_requests[msg_id] = response_queue
        try:
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str)
            self.process.stdin.flush()
            try:
                return response_queue.get(timeout=timeout)
            except queue.Empty:
                return {"error": "Request timed out"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            self._pending_requests.pop(msg_id, None)

    def _send_notification(self, method: str, params: Dict[str, Any] = None):
        if not self.process or not self._running:
            return
        notification = {"jsonrpc": "2.0", "method": method}
        if params:
            notification["params"] = params
        try:
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    def _read_responses(self):
        while self._running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    response = json.loads(line.strip())
                    msg_id = response.get("id")
                    if msg_id and msg_id in self._pending_requests:
                        self._pending_requests[msg_id].put(response)
                    else:
                        logger.debug(f"MCP notification from {self.name}: {response}")
                except json.JSONDecodeError:
                    pass
            except Exception as e:
                if self._running:
                    logger.error(f"Error reading from MCP server {self.name}: {e}")
                break

    def _discover_tools(self):
        result = self._send_request("tools/list", {})
        if result and "result" in result:
            self.tools = result["result"].get("tools", [])
            logger.info(f"Discovered {len(self.tools)} tools from {self.name}")
        else:
            self.tools = []

    def call_tool(self, name: str, arguments: Dict[str, Any], timeout: float = 120) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"MCP tool call started: {self.name}/{name} (timeout={timeout}s)")

        def _do_call():
            return self._send_request("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_call)
                try:
                    result = future.result(timeout=timeout + 5)
                    elapsed = time.time() - start_time
                    logger.info(f"MCP tool call completed: {self.name}/{name} ({elapsed:.1f}s)")
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    logger.error(f"MCP tool {name} hard timeout after {elapsed:.1f}s")
                    return {"error": f"Tool '{name}' timed out after {timeout} seconds."}
        except Exception as e:
            return {"error": f"Tool execution failed: {e}"}

        if result and "result" in result:
            return result["result"]
        elif result and "error" in result:
            error_msg = result["error"]
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_msg))
            return {"error": error_msg}
        return {"error": "Unknown error from MCP server"}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        definitions = []
        for tool in self.tools:
            definitions.append({
                "name": f"{self.name}__{tool['name']}",
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            })
        return definitions


class ExternalMCPManager:
    """Manages multiple external MCP server connections"""

    def __init__(self, config_path: str = None):
        self.servers: Dict[str, MCPServerConnection] = {}
        self.server_configs: Dict[str, Dict] = {}
        self.config_path = config_path or os.path.expanduser("~/.springo/mcp_servers.json")
        self._config_loaded = False
        self._tools_cache_path = os.path.expanduser("~/.springo/mcp_tools_cache.json")
        self._tools_cache: Dict[str, List[Dict]] = {}
        self._load_tools_cache()

    def _load_tools_cache(self):
        try:
            if os.path.exists(self._tools_cache_path):
                with open(self._tools_cache_path, 'r') as f:
                    self._tools_cache = json.load(f)
                logger.info(f"Loaded tool cache for {len(self._tools_cache)} servers")
                self._register_cached_tools_as_deferred()
        except Exception as e:
            logger.warning(f"Failed to load tool cache: {e}")
            self._tools_cache = {}

    def _save_tools_cache(self):
        try:
            os.makedirs(os.path.dirname(self._tools_cache_path), exist_ok=True)
            with open(self._tools_cache_path, 'w') as f:
                json.dump(self._tools_cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save tool cache: {e}")

    def cache_server_tools(self, server_name: str, tools: List[Dict]):
        if tools:
            self._tools_cache[server_name] = tools
            self._save_tools_cache()

    def load_config(self, lazy: bool = True) -> bool:
        if not os.path.exists(self.config_path):
            self._create_default_config()
            return False
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            servers_to_start = []
            for server_config in config.get("servers", []):
                name = server_config.get("name")
                if not name:
                    continue
                if not server_config.get("enabled", True):
                    self.server_configs[name] = {**server_config, "status": "disabled"}
                    continue
                self.server_configs[name] = {**server_config, "status": "configured"}
                if not lazy and name not in self.servers:
                    servers_to_start.append(server_config)
            self._config_loaded = True
            if not lazy and servers_to_start:
                self._start_servers_parallel(servers_to_start)
            return True
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return False

    def _start_servers_parallel(self, servers_to_start: List[Dict]):
        def start_server(server_config):
            name = server_config.get("name")
            try:
                server = MCPServerConnection(
                    name=name, command=server_config.get("command"),
                    args=server_config.get("args", []), env=server_config.get("env", {})
                )
                if server.start():
                    return (name, server, None)
                return (name, None, "Failed to start")
            except Exception as e:
                return (name, None, str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(servers_to_start))) as executor:
            futures = {executor.submit(start_server, cfg): cfg for cfg in servers_to_start}
            for future in concurrent.futures.as_completed(futures):
                name, server, error = future.result()
                if server:
                    self.servers[name] = server
                    if name in self.server_configs:
                        self.server_configs[name]["status"] = "running"
                    if server.tools:
                        self.cache_server_tools(name, server.get_tool_definitions())
                    logger.info(f"Started MCP server: {name} with {len(server.tools)} tools")
                else:
                    if name in self.server_configs:
                        self.server_configs[name]["status"] = "error"
                        self.server_configs[name]["error"] = error
                    logger.error(f"Failed to start MCP server {name}: {error}")

    def ensure_server_started(self, server_name: str) -> bool:
        if server_name in self.servers:
            return True
        if not self._config_loaded:
            self.load_config(lazy=True)
        if server_name not in self.server_configs:
            # Reload config in case new servers were added to mcp_servers.json
            self._config_loaded = False
            self.load_config(lazy=True)
        if server_name not in self.server_configs:
            logger.warning(f"MCP server '{server_name}' not configured in mcp_servers.json")
            return False
        config = self.server_configs[server_name]
        if config.get("status") == "disabled":
            return False
        logger.info(f"Lazy loading MCP server: {server_name}")
        try:
            server = MCPServerConnection(
                name=server_name, command=config.get("command"),
                args=config.get("args", []), env=config.get("env", {})
            )
            if server.start():
                self.servers[server_name] = server
                self.server_configs[server_name]["status"] = "running"
                if server.tools:
                    self.cache_server_tools(server_name, server.get_tool_definitions())
                    self._register_server_tools_deferred(server_name, server)
                return True
            self.server_configs[server_name]["status"] = "error"
            return False
        except Exception as e:
            logger.error(f"Failed to lazy-load MCP server {server_name}: {e}")
            self.server_configs[server_name]["status"] = "error"
            self.server_configs[server_name]["error"] = str(e)
            return False

    def get_configured_servers(self) -> List[Dict]:
        if not self._config_loaded:
            self.load_config(lazy=True)
        result = []
        for name, config in self.server_configs.items():
            result.append({
                "name": name,
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "description": config.get("description", ""),
                "enabled": config.get("enabled", True),
                "status": config.get("status", "configured"),
                "running": name in self.servers,
                "tools": len(self.servers[name].tools) if name in self.servers else 0,
                "error": config.get("error"),
            })
        return result

    def _create_default_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        default_config = {
            "servers": [
                {
                    "name": "filesystem", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.expanduser("~")],
                    "env": {}, "enabled": False,
                    "description": "MCP Filesystem server for file operations"
                },
            ]
        }
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default MCP config at {self.config_path}")

    def save_config(self) -> bool:
        """Save current server configs to file"""
        try:
            servers_list = []
            for name, config in self.server_configs.items():
                servers_list.append({
                    "name": name,
                    "command": config.get("command", ""),
                    "args": config.get("args", []),
                    "env": config.get("env", {}),
                    "enabled": config.get("enabled", True),
                    "description": config.get("description", ""),
                })
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump({"servers": servers_list}, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")
            return False

    def get_cached_tools(self, server_name: str = None) -> List[Dict]:
        """Get cached tools for a server, or all cached tools"""
        if server_name:
            return self._tools_cache.get(server_name, [])
        all_tools = []
        for tools in self._tools_cache.values():
            all_tools.extend(tools)
        return all_tools

    def _register_cached_tools_as_deferred(self):
        """Register all cached tools as deferred in the tool registry"""
        try:
            from .tool_registry import get_tool_registry
            registry = get_tool_registry()
            count = 0
            for server_name, tools in self._tools_cache.items():
                for tool in tools:
                    full_name = tool.get("name", "")
                    description = tool.get("description", "")
                    keywords = full_name.replace('__', ' ').replace('-', ' ').replace('_', ' ').split()
                    registry.register_deferred(
                        name=full_name,
                        description=description,
                        server_name=server_name,
                        keywords=keywords
                    )
                    count += 1
            if count > 0:
                logger.info(f"Registered {count} cached tools as deferred")
        except Exception as e:
            logger.error(f"Failed to register cached tools as deferred: {e}")

    def _register_server_tools_deferred(self, server_name: str, server: MCPServerConnection):
        """Register tools from a single server as deferred in the tool registry"""
        try:
            from .tool_registry import get_tool_registry
            registry = get_tool_registry()
            for tool in server.tools:
                full_name = f"{server_name}__{tool['name']}"
                description = tool.get("description", "")
                keywords = tool['name'].replace('-', ' ').replace('_', ' ').split()
                registry.register_deferred(
                    name=full_name,
                    description=description,
                    server_name=server_name,
                    keywords=keywords
                )
            logger.info(f"Registered {len(server.tools)} tools from {server_name} as deferred")
        except Exception as e:
            logger.error(f"Failed to register deferred tools for {server_name}: {e}")

    def register_tools_as_deferred(self):
        """Register all MCP tools as deferred in the tool registry (lazy loading)"""
        try:
            from .tool_registry import get_tool_registry
            registry = get_tool_registry()
            for server_name, server in self.servers.items():
                for tool in server.tools:
                    full_name = f"{server_name}__{tool['name']}"
                    description = tool.get("description", "")
                    keywords = tool['name'].replace('-', ' ').replace('_', ' ').split()
                    registry.register_deferred(
                        name=full_name,
                        description=description,
                        server_name=server_name,
                        keywords=keywords
                    )
            total = sum(len(s.tools) for s in self.servers.values())
            logger.info(f"Registered {total} MCP tools as deferred")
        except Exception as e:
            logger.error(f"Failed to register deferred tools: {e}")

    def add_server(self, name: str, command: str, args: List[str] = None,
                   env: Dict[str, str] = None, description: str = "") -> bool:
        if name in self.servers:
            return False
        server = MCPServerConnection(name, command, args, env)
        if server.start():
            self.servers[name] = server
            self.server_configs[name] = {
                "name": name, "command": command, "args": args or [],
                "env": env or {}, "description": description,
                "enabled": True, "status": "running"
            }
            if server.tools:
                self.cache_server_tools(name, server.get_tool_definitions())
                self._register_server_tools_deferred(name, server)
            self.save_config()
            return True
        return False

    def remove_server(self, name: str):
        if name in self.servers:
            self.servers[name].stop()
            del self.servers[name]
        if name in self.server_configs:
            del self.server_configs[name]
        self.save_config()

    def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        for server in self.servers.values():
            all_tools.extend(server.get_tool_definitions())
        return all_tools

    def get_server_instructions(self) -> Dict[str, str]:
        """Get instructions from all running MCP servers (for system prompt injection)"""
        instructions = {}
        for name, server in self.servers.items():
            if server.instructions:
                instructions[name] = server.instructions
        return instructions

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 60) -> Dict[str, Any]:
        if "__" not in tool_name:
            return {"error": f"Invalid tool name format: {tool_name}"}
        server_name, actual_tool_name = tool_name.split("__", 1)
        if server_name not in self.servers:
            if not self.ensure_server_started(server_name):
                return {"error": f"Server not found or failed to start: {server_name}"}
        server = self.servers[server_name]
        if not server.health_check():
            del self.servers[server_name]
            if not self.ensure_server_started(server_name):
                return {"error": f"Server {server_name} died and failed to restart"}
            server = self.servers[server_name]
        return server.call_tool(actual_tool_name, arguments, timeout=timeout)

    def stop_all(self):
        """Stop all running servers without modifying config file."""
        for name in list(self.servers.keys()):
            try:
                self.servers[name].stop()
            except Exception as e:
                logger.warning(f"Failed to stop server {name}: {e}")
        self.servers.clear()

    def get_status(self) -> Dict[str, Any]:
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
        results = {}
        dead_servers = []
        for name, server in self.servers.items():
            healthy = server.health_check()
            results[name] = healthy
            if not healthy:
                dead_servers.append(name)
        for name in dead_servers:
            del self.servers[name]
            if name in self.server_configs:
                self.server_configs[name]["status"] = "stopped"
        return results

    def refresh_server(self, server_name: str) -> bool:
        """Refresh a server by restarting it"""
        if server_name in self.servers:
            self.servers[server_name].stop()
            del self.servers[server_name]
        return self.ensure_server_started(server_name)


# Singleton
_external_mcp_manager: Optional[ExternalMCPManager] = None


def get_external_mcp_manager() -> ExternalMCPManager:
    global _external_mcp_manager
    if _external_mcp_manager is None:
        _external_mcp_manager = ExternalMCPManager()
    return _external_mcp_manager


def initialize_external_mcp(lazy: bool = True) -> bool:
    manager = get_external_mcp_manager()
    result = manager.load_config(lazy=lazy)
    if not lazy and manager.servers:
        manager.register_tools_as_deferred()
    return result


def shutdown_external_mcp():
    global _external_mcp_manager
    if _external_mcp_manager:
        _external_mcp_manager.stop_all()
        _external_mcp_manager = None


def start_all_mcp_servers() -> bool:
    """Start all configured MCP servers (parallel startup)."""
    manager = get_external_mcp_manager()
    if not manager._config_loaded:
        manager.load_config(lazy=True)
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
    return get_external_mcp_manager().get_all_tools()


def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], timeout: float = 60) -> Dict[str, Any]:
    """Call an MCP tool with timeout protection."""
    return get_external_mcp_manager().call_tool(tool_name, arguments, timeout=timeout)


__all__ = [
    'MCPServerConnection', 'ExternalMCPManager',
    'get_external_mcp_manager', 'initialize_external_mcp', 'shutdown_external_mcp',
    'start_all_mcp_servers', 'get_mcp_tools', 'call_mcp_tool',
]
