"""
Springo ACP Server — Agent Client Protocol server entry point.

Exposes Springo as an ACP-compatible agent that IDEs (Zed, JetBrains, Neovim)
can use for AI coding assistance. Communicates via JSON-RPC 2.0 over stdio.

Usage:
    python -m api.acp_server

IDE configuration (Zed settings.json):
    {
        "agent_servers": {
            "Springo": {
                "type": "custom",
                "command": "/path/to/venv/bin/python",
                "args": ["-m", "api.acp_server"],
                "env": {"PYTHONPATH": "/path/to/springo"}
            }
        }
    }
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

# Ensure the project root is on the path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Configure logging to stderr (stdout is reserved for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger("springo.acp_server")

# ACP protocol version
ACP_PROTOCOL_VERSION = "2025-03-26"


class SpringoAcpServer:
    """Springo as an ACP agent server over stdio.

    Implements the ACP protocol (JSON-RPC 2.0) methods:
    - initialize
    - session/new
    - session/prompt
    - session/cancel
    """

    def __init__(self):
        self._client_info: Dict[str, Any] = {}
        self._client_capabilities: Dict[str, Any] = {}
        self._initialized = False
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._active_prompts: Dict[str, bool] = {}  # session_id -> cancelled

        # Lazy-loaded services
        self._session_bridge = None
        self._tool_bridge = None
        self._vendor_router = None

    # ──────────────────── Service Access ────────────────────

    def _get_session_bridge(self):
        if self._session_bridge is None:
            from api.services.acp_session import get_acp_session_bridge
            self._session_bridge = get_acp_session_bridge()
        return self._session_bridge

    def _get_tool_bridge(self):
        if self._tool_bridge is None:
            from api.acp_tool_bridge import AcpToolBridge
            self._tool_bridge = AcpToolBridge()
            self._tool_bridge.set_ide_capabilities(self._client_capabilities)
        return self._tool_bridge

    def _get_vendor_router(self):
        if self._vendor_router is None:
            try:
                from api.services.vendor_router import get_vendor_router
                self._vendor_router = get_vendor_router()
            except Exception as e:
                logger.error(f"Failed to load VendorRouter: {e}")
        return self._vendor_router

    # ──────────────────── Protocol Methods ────────────────────

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 'initialize' request."""
        self._client_info = params.get("clientInfo", {})
        self._client_capabilities = params.get("clientCapabilities", {})
        self._initialized = True

        logger.info(f"ACP initialize from: {self._client_info.get('name', 'unknown')}")

        return {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "agentInfo": {
                "name": "Springo",
                "version": "2.0.0",
                "description": "AI coding assistant powered by Amazon Bedrock",
            },
            "agentCapabilities": {
                "streaming": True,
                "toolExecution": True,
                "multiTurn": True,
            },
            "authMethods": [],
        }

    async def handle_session_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 'session/new' request."""
        cwd = params.get("cwd", os.getcwd())
        mcp_servers = params.get("mcpServers", [])

        bridge = self._get_session_bridge()
        session_id = bridge.create_session(cwd=cwd, client_caps=self._client_capabilities)

        self._sessions[session_id] = {
            "cwd": cwd,
            "mcp_servers": mcp_servers,
        }

        logger.info(f"New ACP session: {session_id[:8]} cwd={cwd}")
        return {"sessionId": session_id}

    async def handle_session_prompt(
        self,
        params: Dict[str, Any],
        send_notification,
    ) -> Dict[str, Any]:
        """Handle 'session/prompt' request.

        This is the core agent loop:
        1. Convert ACP prompt to Springo message format
        2. Call VendorRouter for LLM response
        3. Stream updates back via session/update notifications
        4. Handle tool calls in a loop
        5. Return final response
        """
        session_id = params.get("sessionId", "")
        prompt_blocks = params.get("prompt", [])

        if session_id not in self._sessions:
            return {"error": {"code": -32602, "message": f"Unknown session: {session_id}"}}

        self._active_prompts[session_id] = False  # Not cancelled

        # Extract text from prompt blocks
        prompt_text = ""
        for block in prompt_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                prompt_text += block.get("text", "")
            elif isinstance(block, str):
                prompt_text += block

        bridge = self._get_session_bridge()
        bridge.append_message(session_id, "user", [{"type": "text", "text": prompt_text}])

        # Build messages for LLM
        messages = bridge.get_messages(session_id)

        # Get tool definitions
        tool_bridge = self._get_tool_bridge()
        tools = tool_bridge.get_tool_definitions_for_acp()

        # Agent loop (with tool use)
        max_iterations = 10
        for iteration in range(max_iterations):
            if self._active_prompts.get(session_id):
                return {"stopReason": "cancelled", "content": []}

            # Call LLM
            response = await self._call_llm(messages, tools, session_id, send_notification)

            if "error" in response:
                return {"stopReason": "error", "content": [{"type": "text", "text": response["error"]}]}

            stop_reason = response.get("stop_reason", "end_turn")
            content_blocks = response.get("content", [])

            # Send text chunks as updates
            for block in content_blocks:
                if block.get("type") == "text":
                    await send_notification("session/update", {
                        "sessionId": session_id,
                        "kind": "agent_message_chunk",
                        "agentMessageChunk": {"type": "text", "text": block["text"]},
                    })

            # Handle tool use
            tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
            if stop_reason == "tool_use" and tool_use_blocks:
                # Store assistant message
                bridge.append_message(session_id, "assistant", content_blocks)

                tool_results = []
                for tool_block in tool_use_blocks:
                    tool_name = tool_block.get("name", "")
                    tool_input = tool_block.get("input", {})
                    tool_id = tool_block.get("id", str(uuid.uuid4()))

                    # Notify IDE about tool call
                    await send_notification("session/update", {
                        "sessionId": session_id,
                        "kind": "tool_call",
                        "toolCall": {
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_input,
                            "status": "running",
                        },
                    })

                    # Execute tool
                    session_state = self._sessions.get(session_id, {})
                    result = await tool_bridge.execute_tool(
                        tool_name, tool_input, session_state,
                    )

                    # Notify IDE about tool result
                    await send_notification("session/update", {
                        "sessionId": session_id,
                        "kind": "tool_call_update",
                        "toolCallUpdate": {
                            "id": tool_id,
                            "name": tool_name,
                            "status": "completed",
                            "result": result,
                        },
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(result) if isinstance(result, dict) else str(result),
                    })

                # Add tool results to messages and continue loop
                bridge.append_message(session_id, "user", tool_results)
                messages = bridge.get_messages(session_id)
                continue

            # No tool use — we're done
            bridge.append_message(session_id, "assistant", content_blocks)

            return {
                "stopReason": stop_reason if stop_reason != "tool_use" else "end_turn",
                "content": content_blocks,
            }

        # Max iterations reached
        return {
            "stopReason": "max_iterations",
            "content": [{"type": "text", "text": "Max tool iterations reached."}],
        }

    async def handle_session_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 'session/cancel' request."""
        session_id = params.get("sessionId", "")
        self._active_prompts[session_id] = True  # Mark as cancelled
        logger.info(f"Cancelled ACP session prompt: {session_id[:8]}")
        return {}

    # ──────────────────── LLM Integration ────────────────────

    async def _call_llm(
        self,
        messages: List[Dict],
        tools: List[Dict],
        session_id: str,
        send_notification,
    ) -> Dict[str, Any]:
        """Call the LLM via VendorRouter's Converse API and collect the response."""
        router = self._get_vendor_router()
        if not router:
            return {"error": "VendorRouter not available"}

        try:
            from api.config import settings
            model = settings.bedrock_model_id

            # Build system prompt
            cwd = self._sessions.get(session_id, {}).get("cwd", "/tmp")
            system_prompt = (
                f"You are Springo, an AI coding assistant. "
                f"Working directory: {cwd}\n"
                f"You have access to tools for file operations, git, search, and more."
            )

            # Build Converse-compatible body
            # _build_converse_kwargs expects: system, messages, tools, max_tokens
            converse_messages = self._convert_messages_for_bedrock(messages)

            # Build tools in Converse format (toolSpec)
            converse_tools = []
            for tool in tools[:50]:
                converse_tools.append({
                    "toolSpec": {
                        "name": tool["name"],
                        "description": tool.get("description", "")[:500],
                        "inputSchema": {"json": tool.get("inputSchema", {"type": "object", "properties": {}})},
                    }
                })

            body = {
                "system": system_prompt,
                "messages": converse_messages,
                "max_tokens": 4096,
                "_original_model": model,
            }
            if converse_tools:
                body["tools"] = converse_tools

            # Use invoke_model_stream_text with Converse API
            # Yields: {"type": "delta", "text": "..."} and {"type": "usage", ...}
            # For tool use we need the full converse stream — use invoke_model_stream instead
            full_response = {"content": [], "stop_reason": "end_turn"}
            collected_text = ""

            async for event in router.invoke_model_stream_text(
                model_id=model,
                body=body,
                api_format="converse",
            ):
                event_type = event.get("type", "")
                if event_type == "delta":
                    text = event.get("text", "")
                    collected_text += text
                elif event_type == "tool_use_start":
                    # Converse stream_text doesn't yield tool_use — fall back
                    pass
                elif event_type == "heartbeat":
                    pass

            if collected_text:
                full_response["content"].append({"type": "text", "text": collected_text})

            return full_response

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return {"error": str(e)}

    def _convert_messages_for_bedrock(self, messages: List[Dict]) -> List[Dict]:
        """Convert ACP-style messages to Bedrock Converse format."""
        bedrock_msgs = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                bedrock_msgs.append({"role": role, "content": [{"text": content}]})
            elif isinstance(content, list):
                bedrock_content = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            bedrock_content.append({"text": block.get("text", "")})
                        elif block.get("type") == "tool_use":
                            bedrock_content.append({
                                "toolUse": {
                                    "toolUseId": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}),
                                }
                            })
                        elif block.get("type") == "tool_result":
                            bedrock_content.append({
                                "toolResult": {
                                    "toolUseId": block.get("tool_use_id", ""),
                                    "content": [{"text": block.get("content", "")}],
                                }
                            })
                    elif isinstance(block, str):
                        bedrock_content.append({"text": block})
                if bedrock_content:
                    bedrock_msgs.append({"role": role, "content": bedrock_content})
            else:
                bedrock_msgs.append({"role": role, "content": [{"text": str(content)}]})

        return bedrock_msgs


# ──────────────────── stdio JSON-RPC Transport ────────────────────

class StdioTransport:
    """JSON-RPC 2.0 transport over stdin/stdout."""

    def __init__(self, server: SpringoAcpServer):
        self.server = server

    async def run(self):
        """Main loop: read JSON-RPC requests from stdin, dispatch, write responses to stdout."""
        logger.info("Springo ACP Server starting on stdio")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break  # EOF
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self._write_error(None, -32700, "Parse error")
                    continue

                msg_id = request.get("id")
                method = request.get("method", "")
                params = request.get("params", {})

                if not method:
                    if msg_id is not None:
                        self._write_error(msg_id, -32600, "Invalid request: missing method")
                    continue

                # Dispatch
                result = await self._dispatch(method, params)

                # If it's a request (has id), send response
                if msg_id is not None:
                    if isinstance(result, dict) and "error" in result and isinstance(result["error"], dict):
                        self._write_response(msg_id, error=result["error"])
                    else:
                        self._write_response(msg_id, result=result)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stdio loop: {e}", exc_info=True)

        logger.info("Springo ACP Server shutting down")

    async def _dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        """Dispatch a JSON-RPC method to the appropriate handler."""
        if method == "initialize":
            return await self.server.handle_initialize(params)
        elif method == "notifications/initialized":
            return None  # Notification, no response needed
        elif method == "session/new":
            return await self.server.handle_session_new(params)
        elif method == "session/prompt":
            return await self.server.handle_session_prompt(params, self._send_notification)
        elif method == "session/cancel":
            return await self.server.handle_session_cancel(params)
        else:
            logger.warning(f"Unknown ACP method: {method}")
            return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    async def _send_notification(self, method: str, params: Dict[str, Any]):
        """Send a JSON-RPC notification (no id) to stdout."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write_line(json.dumps(notification, ensure_ascii=False))

    def _write_response(self, msg_id: Any, result: Any = None, error: Dict = None):
        """Write a JSON-RPC response to stdout."""
        response = {"jsonrpc": "2.0", "id": msg_id}
        if error:
            response["error"] = error
        else:
            response["result"] = result if result is not None else {}
        self._write_line(json.dumps(response, ensure_ascii=False))

    def _write_error(self, msg_id: Any, code: int, message: str):
        """Write a JSON-RPC error response."""
        self._write_response(msg_id, error={"code": code, "message": message})

    def _write_line(self, line: str):
        """Write a line to stdout and flush."""
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


# ──────────────────── Entry Point ────────────────────

async def main():
    """Initialize services and run the ACP server."""
    # Initialize core services needed for the agent
    try:
        from api.services.tool_manager import get_tool_manager
        await get_tool_manager()
        logger.info("Tool Manager initialized for ACP server")
    except Exception as e:
        logger.warning(f"Tool Manager init failed: {e}")

    try:
        from api.services.mcp_client import initialize_external_mcp
        initialize_external_mcp(lazy=True)
        logger.info("External MCP loaded for ACP server")
    except Exception as e:
        logger.warning(f"MCP init failed: {e}")

    try:
        from api.services.bedrock import get_bedrock_service
        from api.services.vendor_router import init_vendor_router
        bedrock_svc = get_bedrock_service()
        init_vendor_router(bedrock_svc, None, None)
        logger.info("VendorRouter initialized for ACP server")
    except Exception as e:
        logger.warning(f"VendorRouter init failed: {e}")

    # Run the server
    server = SpringoAcpServer()
    transport = StdioTransport(server)
    await transport.run()


if __name__ == "__main__":
    asyncio.run(main())
