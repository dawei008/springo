"""
ACP Client for Springo FastAPI
Manages connections to external ACP-compatible agents (stdio + HTTP/WebSocket).
Follows the same patterns as mcp_client.py (subprocess management, JSON-RPC 2.0).
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
import uuid
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ACP Protocol version
ACP_PROTOCOL_VERSION = "2025-03-26"


class AcpAgentConnection:
    """Connection to a single ACP agent (stdio or HTTP/WebSocket)."""

    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        command: str = None,
        args: List[str] = None,
        env: Dict[str, str] = None,
        url: str = None,
        auth: Dict[str, str] = None,
        description: str = "",
    ):
        self.name = name
        self.transport = transport  # "stdio" | "http" | "websocket"
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.url = url
        self.auth = auth or {}
        self.description = description

        # stdio state
        self.process: Optional[subprocess.Popen] = None
        self._message_id = 0
        self._pending_requests: Dict[int, queue.Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

        # HTTP state
        self._http_client: Optional[httpx.AsyncClient] = None

        # Agent capabilities (populated after initialize)
        self.agent_info: Dict[str, Any] = {}
        self.agent_capabilities: Dict[str, Any] = {}
        self.auth_methods: List[Dict[str, Any]] = []
        self._initialized = False

        # Active sessions
        self._sessions: Dict[str, Dict[str, Any]] = {}

    # ──────────────────── Lifecycle ────────────────────

    async def start(self) -> bool:
        """Start connection: spawn subprocess or connect to remote."""
        try:
            if self.transport == "stdio":
                return self._start_stdio()
            elif self.transport in ("http", "websocket"):
                return await self._start_http()
            else:
                logger.error(f"Unknown transport: {self.transport}")
                return False
        except Exception as e:
            logger.error(f"Failed to start ACP agent {self.name}: {e}")
            return False

    async def stop(self):
        """Terminate connection."""
        self._running = False
        self._initialized = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def is_alive(self) -> bool:
        if self.transport == "stdio":
            return self.process is not None and self.process.poll() is None
        elif self.transport in ("http", "websocket"):
            return self._http_client is not None
        return False

    # ──────────────────── stdio transport ────────────────────

    def _start_stdio(self) -> bool:
        """Start subprocess-based ACP agent."""
        process_env = os.environ.copy()
        home = os.path.expanduser("~")
        extra_paths = [
            "/usr/local/bin", "/opt/homebrew/bin", "/opt/homebrew/sbin",
            f"{home}/.local/bin", f"{home}/.npm-global/bin",
            f"{home}/.volta/bin", f"{home}/.cargo/bin",
            f"{home}/.asdf/shims",
            "/usr/bin", "/bin", "/usr/sbin", "/sbin",
        ]
        import glob as glob_mod
        nvm_paths = glob_mod.glob(f"{home}/.nvm/versions/node/*/bin")
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
            env=process_env, text=True, bufsize=1,
        )
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()
        return True

    def _send_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 60) -> Optional[Dict]:
        """Send a JSON-RPC 2.0 request (stdio)."""
        if not self.process or not self._running:
            return {"error": "Agent not running"}
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
        """Send a JSON-RPC 2.0 notification (no id, no response expected)."""
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
        """Background thread: read JSON-RPC responses from stdout."""
        while self._running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    response = json.loads(line)
                    msg_id = response.get("id")
                    if msg_id is not None and msg_id in self._pending_requests:
                        self._pending_requests[msg_id].put(response)
                    elif response.get("method"):
                        # This is a notification/request from the agent
                        self._handle_agent_notification(response)
                    else:
                        logger.debug(f"ACP unmatched response from {self.name}: {response}")
                except json.JSONDecodeError:
                    pass
            except Exception as e:
                if self._running:
                    logger.error(f"Error reading from ACP agent {self.name}: {e}")
                break

    def _handle_agent_notification(self, message: Dict[str, Any]):
        """Handle notifications/requests from the agent (e.g., session/update)."""
        method = message.get("method", "")
        params = message.get("params", {})
        msg_id = message.get("id")

        if method == "session/update":
            session_id = params.get("sessionId", "")
            if session_id in self._sessions:
                updates = self._sessions[session_id].setdefault("updates", [])
                updates.append(params)
        elif method == "session/request_permission":
            # Auto-approve permissions for now
            if msg_id is not None:
                self._send_response(msg_id, {"approved": True})
        elif method.startswith("fs/"):
            # File system requests from agent — auto-deny for now
            if msg_id is not None:
                self._send_response(msg_id, None, error={"code": -32601, "message": "fs not supported by client"})
        else:
            logger.debug(f"ACP notification from {self.name}: {method}")

    def _send_response(self, msg_id: int, result: Any = None, error: Dict = None):
        """Send a JSON-RPC 2.0 response back to the agent."""
        if not self.process or not self._running:
            return
        response = {"jsonrpc": "2.0", "id": msg_id}
        if error:
            response["error"] = error
        else:
            response["result"] = result or {}
        try:
            self.process.stdin.write(json.dumps(response) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    # ──────────────────── HTTP transport ────────────────────

    async def _start_http(self) -> bool:
        """Start HTTP-based ACP connection."""
        headers = {}
        if self.auth:
            auth_type = self.auth.get("type", "")
            if auth_type == "bearer":
                token_env = self.auth.get("token_env", "")
                token = os.environ.get(token_env, self.auth.get("token", ""))
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "api_key":
                key_env = self.auth.get("key_env", "")
                key = os.environ.get(key_env, self.auth.get("key", ""))
                header_name = self.auth.get("header", "X-API-Key")
                if key:
                    headers[header_name] = key

        self._http_client = httpx.AsyncClient(
            base_url=self.url,
            headers=headers,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self._running = True
        return True

    async def _http_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 120) -> Optional[Dict]:
        """Send a JSON-RPC 2.0 request over HTTP POST."""
        if not self._http_client:
            return {"error": "HTTP client not initialized"}
        self._message_id += 1
        msg_id = self._message_id
        request = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params:
            request["params"] = params
        try:
            resp = await self._http_client.post("/", json=request, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {"error": "HTTP request timed out"}
        except Exception as e:
            return {"error": str(e)}

    # ──────────────────── ACP Protocol Methods ────────────────────

    async def initialize(self) -> Dict[str, Any]:
        """ACP initialize handshake. Returns agent capabilities."""
        params = {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "clientCapabilities": {
                "roots": True,
                "sampling": False,
            },
            "clientInfo": {"name": "springo", "version": "2.0.0"},
        }

        if self.transport == "stdio":
            result = self._send_request("initialize", params, timeout=30)
        else:
            result = await self._http_request("initialize", params, timeout=30)

        if result and "error" not in result:
            result_data = result.get("result", {})
            self.agent_info = result_data.get("agentInfo", {})
            self.agent_capabilities = result_data.get("agentCapabilities", {})
            self.auth_methods = result_data.get("authMethods", [])
            self._initialized = True

            # Send initialized notification
            if self.transport == "stdio":
                self._send_notification("notifications/initialized", {})

            logger.info(
                f"ACP agent {self.name} initialized: "
                f"info={self.agent_info}, caps={list(self.agent_capabilities.keys())}"
            )
            return result_data
        else:
            error = result.get("error", "Unknown error") if result else "No response"
            logger.error(f"ACP initialize failed for {self.name}: {error}")
            return {"error": error}

    async def authenticate(self, method_id: str, credentials: Dict[str, Any] = None) -> Dict[str, Any]:
        """ACP authenticate if needed."""
        params = {"methodId": method_id}
        if credentials:
            params["credentials"] = credentials

        if self.transport == "stdio":
            result = self._send_request("authenticate", params, timeout=30)
        else:
            result = await self._http_request("authenticate", params, timeout=30)

        if result and "error" not in result:
            return result.get("result", {})
        return {"error": result.get("error", "Authentication failed") if result else "No response"}

    async def session_new(self, cwd: str = None, mcp_servers: List[Dict] = None) -> Optional[str]:
        """Create a new ACP session. Returns sessionId."""
        params = {}
        if cwd:
            params["cwd"] = cwd
        if mcp_servers:
            params["mcpServers"] = mcp_servers

        if self.transport == "stdio":
            result = self._send_request("session/new", params, timeout=30)
        else:
            result = await self._http_request("session/new", params, timeout=30)

        if result and "error" not in result:
            session_id = result.get("result", {}).get("sessionId")
            if session_id:
                self._sessions[session_id] = {"cwd": cwd, "updates": [], "created": time.time()}
            return session_id

        error = result.get("error", "Unknown") if result else "No response"
        logger.error(f"ACP session/new failed for {self.name}: {error}")
        return None

    async def session_prompt(
        self,
        session_id: str,
        prompt: str,
        on_update: Callable = None,
        timeout: float = 300,
    ) -> Dict[str, Any]:
        """Send a prompt to the agent, collect streaming updates.

        Returns {text, stop_reason, updates}.
        """
        params = {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt}],
        }

        # Clear prior updates for this session
        if session_id in self._sessions:
            self._sessions[session_id]["updates"] = []

        if self.transport == "stdio":
            result = self._send_request("session/prompt", params, timeout=timeout)
        else:
            result = await self._http_request("session/prompt", params, timeout=timeout)

        # Collect any streaming updates that arrived via notifications
        updates = []
        if session_id in self._sessions:
            updates = self._sessions[session_id].get("updates", [])

        if result and "error" not in result:
            result_data = result.get("result", {})
            return {
                "text": self._extract_text(result_data),
                "stop_reason": result_data.get("stopReason", "end_turn"),
                "updates": updates,
                "raw": result_data,
            }

        error = result.get("error", "Unknown") if result else "No response"
        return {"text": "", "stop_reason": "error", "error": str(error), "updates": updates}

    async def session_cancel(self, session_id: str) -> bool:
        """Cancel an ongoing prompt."""
        params = {"sessionId": session_id}
        if self.transport == "stdio":
            result = self._send_request("session/cancel", params, timeout=10)
        else:
            result = await self._http_request("session/cancel", params, timeout=10)
        return result is not None and "error" not in result

    # ──────────────────── Helpers ────────────────────

    def _extract_text(self, result_data: Dict) -> str:
        """Extract text content from ACP response."""
        content = result_data.get("content", [])
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif isinstance(block, str):
                    texts.append(block)
            return "\n".join(texts)
        elif isinstance(content, str):
            return content
        return str(result_data)

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "alive": self.is_alive(),
            "initialized": self._initialized,
            "agent_info": self.agent_info,
            "capabilities": list(self.agent_capabilities.keys()),
            "sessions": len(self._sessions),
            "description": self.description,
        }


class AcpClientManager:
    """Manages multiple ACP agent connections. Singleton."""

    def __init__(self, config_path: str = None):
        self.agents: Dict[str, AcpAgentConnection] = {}
        self.agent_configs: Dict[str, Dict] = {}
        self.config_path = config_path or os.path.expanduser("~/.springo/acp_agents.json")
        self._config_loaded = False

    def load_config(self) -> bool:
        """Load agent configurations from acp_agents.json."""
        if not os.path.exists(self.config_path):
            self._create_default_config()
            return False
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            for agent_config in config.get("agents", []):
                name = agent_config.get("name")
                if not name:
                    continue
                if not agent_config.get("enabled", True):
                    self.agent_configs[name] = {**agent_config, "status": "disabled"}
                    continue
                self.agent_configs[name] = {**agent_config, "status": "configured"}
            self._config_loaded = True
            logger.info(f"Loaded {len(self.agent_configs)} ACP agent configs")
            return True
        except Exception as e:
            logger.error(f"Failed to load ACP config: {e}")
            return False

    def _create_default_config(self):
        """Create default acp_agents.json with example agents."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        default_config = {
            "agents": [
                {
                    "name": "kiro",
                    "transport": "stdio",
                    "command": os.path.expanduser("~/.local/bin/kiro-cli"),
                    "args": ["acp"],
                    "env": {},
                    "enabled": False,
                    "description": "AWS Kiro agent — uses Kiro subscription credit"
                },
                {
                    "name": "gemini",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@google/gemini-cli", "--experimental-acp"],
                    "env": {},
                    "enabled": False,
                    "description": "Google Gemini CLI agent"
                },
            ]
        }
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default ACP config at {self.config_path}")

    def save_config(self) -> bool:
        """Save current agent configs to file."""
        try:
            agents_list = []
            for name, config in self.agent_configs.items():
                agents_list.append({
                    "name": name,
                    "transport": config.get("transport", "stdio"),
                    "command": config.get("command", ""),
                    "args": config.get("args", []),
                    "env": config.get("env", {}),
                    "url": config.get("url", ""),
                    "auth": config.get("auth", {}),
                    "enabled": config.get("enabled", True),
                    "description": config.get("description", ""),
                })
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump({"agents": agents_list}, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save ACP config: {e}")
            return False

    async def ensure_agent_started(self, agent_name: str) -> bool:
        """Start an agent if not already running. Returns True on success."""
        if agent_name in self.agents and self.agents[agent_name].is_alive():
            if self.agents[agent_name]._initialized:
                return True
            # Connected but not initialized — initialize now
            result = await self.agents[agent_name].initialize()
            return "error" not in result

        if not self._config_loaded:
            self.load_config()

        if agent_name not in self.agent_configs:
            logger.warning(f"ACP agent '{agent_name}' not configured")
            return False

        config = self.agent_configs[agent_name]
        if config.get("status") == "disabled":
            return False

        logger.info(f"Starting ACP agent: {agent_name}")
        agent = AcpAgentConnection(
            name=agent_name,
            transport=config.get("transport", "stdio"),
            command=config.get("command"),
            args=config.get("args", []),
            env=config.get("env", {}),
            url=config.get("url"),
            auth=config.get("auth", {}),
            description=config.get("description", ""),
        )

        started = await agent.start()
        if not started:
            self.agent_configs[agent_name]["status"] = "error"
            self.agent_configs[agent_name]["error"] = "Failed to start"
            return False

        # Initialize ACP handshake
        init_result = await agent.initialize()
        if "error" in init_result:
            self.agent_configs[agent_name]["status"] = "error"
            self.agent_configs[agent_name]["error"] = str(init_result["error"])
            await agent.stop()
            return False

        self.agents[agent_name] = agent
        self.agent_configs[agent_name]["status"] = "running"
        logger.info(f"ACP agent {agent_name} started and initialized")
        return True

    async def prompt_agent(
        self,
        agent_name: str,
        prompt: str,
        cwd: str = None,
        timeout: float = 300,
    ) -> Dict[str, Any]:
        """High-level: ensure agent is started, create session if needed, send prompt."""
        if not await self.ensure_agent_started(agent_name):
            return {"error": f"Failed to start ACP agent: {agent_name}"}

        agent = self.agents[agent_name]

        # Create a new session for this prompt
        session_id = await agent.session_new(cwd=cwd)
        if not session_id:
            return {"error": f"Failed to create session on agent: {agent_name}"}

        # Send prompt
        result = await agent.session_prompt(session_id, prompt, timeout=timeout)
        return result

    def get_all_agents(self) -> List[Dict[str, Any]]:
        """List all configured agents with their status."""
        if not self._config_loaded:
            self.load_config()
        result = []
        for name, config in self.agent_configs.items():
            agent = self.agents.get(name)
            entry = {
                "name": name,
                "transport": config.get("transport", "stdio"),
                "description": config.get("description", ""),
                "enabled": config.get("enabled", True),
                "status": config.get("status", "configured"),
                "running": agent is not None and agent.is_alive() if agent else False,
                "initialized": agent._initialized if agent else False,
                "agent_info": agent.agent_info if agent else {},
                "error": config.get("error"),
            }
            result.append(entry)
        return result

    async def add_agent(
        self,
        name: str,
        transport: str = "stdio",
        command: str = None,
        args: List[str] = None,
        env: Dict[str, str] = None,
        url: str = None,
        auth: Dict[str, str] = None,
        description: str = "",
    ) -> bool:
        """Add and start a new agent."""
        if name in self.agents:
            return False
        self.agent_configs[name] = {
            "name": name,
            "transport": transport,
            "command": command,
            "args": args or [],
            "env": env or {},
            "url": url or "",
            "auth": auth or {},
            "enabled": True,
            "description": description,
            "status": "configured",
        }
        self.save_config()
        return await self.ensure_agent_started(name)

    async def remove_agent(self, name: str):
        """Stop and remove an agent."""
        if name in self.agents:
            await self.agents[name].stop()
            del self.agents[name]
        if name in self.agent_configs:
            del self.agent_configs[name]
        self.save_config()

    async def refresh_agent(self, agent_name: str) -> bool:
        """Restart an agent connection."""
        if agent_name in self.agents:
            await self.agents[agent_name].stop()
            del self.agents[agent_name]
        if agent_name in self.agent_configs:
            self.agent_configs[agent_name]["status"] = "configured"
            self.agent_configs[agent_name].pop("error", None)
        return await self.ensure_agent_started(agent_name)

    async def stop_all(self):
        """Stop all running agents."""
        for name in list(self.agents.keys()):
            try:
                await self.agents[name].stop()
            except Exception as e:
                logger.warning(f"Failed to stop ACP agent {name}: {e}")
        self.agents.clear()

    async def fetch_registry(self) -> List[Dict[str, Any]]:
        """Fetch available agents from ACP registry CDN."""
        registry_url = "https://registry.acpx.dev/agents.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(registry_url)
                resp.raise_for_status()
                data = resp.json()
                return data.get("agents", [])
        except Exception as e:
            logger.warning(f"Failed to fetch ACP registry: {e}")
            return []

    async def install_agent(self, agent_id: str, registry_entry: Dict[str, Any] = None) -> bool:
        """Install an agent from registry entry."""
        if not registry_entry:
            registry = await self.fetch_registry()
            for entry in registry:
                if entry.get("id") == agent_id or entry.get("name") == agent_id:
                    registry_entry = entry
                    break
        if not registry_entry:
            return False

        name = registry_entry.get("name", agent_id)
        transport = registry_entry.get("transport", "stdio")
        self.agent_configs[name] = {
            "name": name,
            "transport": transport,
            "command": registry_entry.get("command", ""),
            "args": registry_entry.get("args", []),
            "env": registry_entry.get("env", {}),
            "url": registry_entry.get("url", ""),
            "auth": registry_entry.get("auth", {}),
            "enabled": True,
            "description": registry_entry.get("description", ""),
            "status": "configured",
        }
        self.save_config()
        return True


# ──────────────────── Singleton ────────────────────

_acp_client_manager: Optional[AcpClientManager] = None


def get_acp_client_manager() -> AcpClientManager:
    global _acp_client_manager
    if _acp_client_manager is None:
        _acp_client_manager = AcpClientManager()
    return _acp_client_manager


def initialize_acp_client() -> bool:
    """Load ACP agent config (lazy mode — agents start on first use)."""
    manager = get_acp_client_manager()
    return manager.load_config()


async def shutdown_acp_client():
    """Stop all ACP agents."""
    global _acp_client_manager
    if _acp_client_manager:
        await _acp_client_manager.stop_all()
        _acp_client_manager = None


__all__ = [
    'AcpAgentConnection', 'AcpClientManager',
    'get_acp_client_manager', 'initialize_acp_client', 'shutdown_acp_client',
]
