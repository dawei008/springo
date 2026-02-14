"""
LSP Manager Service
Manages Language Server Protocol servers for code intelligence.

Provides go-to-definition, find-references, hover, document-symbols,
workspace-symbol, and diagnostics capabilities via language servers
(pylsp, typescript-language-server, gopls, etc.).

Communicates with language servers over JSON-RPC 2.0 via stdio.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# File extension → language ID mapping
LANG_MAP: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".lua": "lua",
    ".sh": "shellscript",
    ".bash": "shellscript",
}

# Language → server launch command
# Each entry: (command_args, check_binary)
SERVER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "python": {
        "cmd": ["pylsp"],
        "check": "pylsp",
        "init_options": {},
    },
    "typescript": {
        "cmd": ["typescript-language-server", "--stdio"],
        "check": "typescript-language-server",
        "init_options": {},
    },
    "javascript": {
        "cmd": ["typescript-language-server", "--stdio"],
        "check": "typescript-language-server",
        "init_options": {},
    },
    "typescriptreact": {
        "cmd": ["typescript-language-server", "--stdio"],
        "check": "typescript-language-server",
        "init_options": {},
    },
    "javascriptreact": {
        "cmd": ["typescript-language-server", "--stdio"],
        "check": "typescript-language-server",
        "init_options": {},
    },
    "go": {
        "cmd": ["gopls", "serve"],
        "check": "gopls",
        "init_options": {},
    },
    "rust": {
        "cmd": ["rust-analyzer"],
        "check": "rust-analyzer",
        "init_options": {},
    },
}

# Languages that share the same server process
LANG_TO_SERVER_KEY: Dict[str, str] = {
    "python": "python",
    "typescript": "typescript",
    "typescriptreact": "typescript",
    "javascript": "typescript",
    "javascriptreact": "typescript",
    "go": "go",
    "rust": "rust",
}


class LspServerConnection:
    """Manages a single language server process and JSON-RPC communication."""

    def __init__(self, language: str, cmd: List[str], workspace_root: str,
                 init_options: Optional[Dict] = None):
        self.language = language
        self.cmd = cmd
        self.workspace_root = workspace_root
        self.init_options = init_options or {}
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._open_files: set = set()  # URIs of open documents
        self._read_buf = b""

    async def start(self) -> bool:
        """Start the language server process and initialize the LSP session."""
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_root,
            )
            logger.info(f"LSP server started: {' '.join(self.cmd)} (pid={self.process.pid})")

            # Start background reader
            self._reader_task = asyncio.create_task(self._read_loop())

            # Send initialize request
            result = await self._request("initialize", {
                "processId": os.getpid(),
                "rootUri": Path(self.workspace_root).as_uri(),
                "rootPath": self.workspace_root,
                "capabilities": {
                    "textDocument": {
                        "definition": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "documentSymbol": {
                            "dynamicRegistration": False,
                            "hierarchicalDocumentSymbolSupport": True,
                        },
                        "publishDiagnostics": {"relatedInformation": True},
                    },
                    "workspace": {
                        "symbol": {"dynamicRegistration": False},
                        "workspaceFolders": True,
                    },
                },
                "workspaceFolders": [
                    {"uri": Path(self.workspace_root).as_uri(), "name": Path(self.workspace_root).name}
                ],
                "initializationOptions": self.init_options,
            }, timeout=30)

            if result is None:
                logger.error(f"LSP initialize returned None for {self.language}")
                return False

            # Send initialized notification
            await self._notify("initialized", {})
            self._initialized = True
            logger.info(f"LSP server initialized for {self.language}")
            return True

        except Exception as e:
            logger.error(f"Failed to start LSP server for {self.language}: {e}")
            await self.stop()
            return False

    async def stop(self):
        """Gracefully shut down the language server."""
        if self.process and self.process.returncode is None:
            try:
                await self._request("shutdown", None, timeout=5)
                await self._notify("exit", None)
                await asyncio.sleep(0.5)
            except Exception:
                pass
            finally:
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._initialized = False
        self._open_files.clear()
        logger.info(f"LSP server stopped for {self.language}")

    @property
    def is_alive(self) -> bool:
        return (self.process is not None
                and self.process.returncode is None
                and self._initialized)

    # ---- Document management ----

    async def open_document(self, file_path: str):
        """Send textDocument/didOpen if not already open."""
        uri = Path(file_path).as_uri()
        if uri in self._open_files:
            return
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Cannot read {file_path} for didOpen: {e}")
            return
        lang_id = self._detect_language(file_path)
        await self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": lang_id,
                "version": 1,
                "text": content,
            }
        })
        self._open_files.add(uri)

    async def close_document(self, file_path: str):
        """Send textDocument/didClose."""
        uri = Path(file_path).as_uri()
        if uri not in self._open_files:
            return
        await self._notify("textDocument/didClose", {
            "textDocument": {"uri": uri}
        })
        self._open_files.discard(uri)

    async def notify_change(self, file_path: str):
        """Re-open document to notify server of file changes."""
        uri = Path(file_path).as_uri()
        if uri in self._open_files:
            await self.close_document(file_path)
        await self.open_document(file_path)

    # ---- LSP operations ----

    async def go_to_definition(self, file_path: str, line: int, character: int) -> List[Dict]:
        """textDocument/definition → list of locations."""
        await self.open_document(file_path)
        result = await self._request("textDocument/definition", {
            "textDocument": {"uri": Path(file_path).as_uri()},
            "position": {"line": line, "character": character},
        })
        return self._normalize_locations(result)

    async def find_references(self, file_path: str, line: int, character: int,
                              include_declaration: bool = True) -> List[Dict]:
        """textDocument/references → list of locations."""
        await self.open_document(file_path)
        result = await self._request("textDocument/references", {
            "textDocument": {"uri": Path(file_path).as_uri()},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration},
        })
        return self._normalize_locations(result)

    async def hover(self, file_path: str, line: int, character: int) -> Optional[str]:
        """textDocument/hover → markdown/plaintext content."""
        await self.open_document(file_path)
        result = await self._request("textDocument/hover", {
            "textDocument": {"uri": Path(file_path).as_uri()},
            "position": {"line": line, "character": character},
        })
        if not result:
            return None
        contents = result.get("contents")
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            return contents.get("value", str(contents))
        if isinstance(contents, list):
            parts = []
            for c in contents:
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, dict):
                    parts.append(c.get("value", ""))
            return "\n\n".join(parts)
        return str(contents)

    async def document_symbols(self, file_path: str) -> List[Dict]:
        """textDocument/documentSymbol → list of symbols."""
        await self.open_document(file_path)
        result = await self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": Path(file_path).as_uri()},
        })
        if not result:
            return []
        return self._flatten_symbols(result)

    async def workspace_symbol(self, query: str) -> List[Dict]:
        """workspace/symbol → list of symbols across workspace."""
        result = await self._request("workspace/symbol", {"query": query})
        if not result:
            return []
        return [self._format_symbol(s) for s in result]

    async def diagnostics(self, file_path: str) -> List[Dict]:
        """Get diagnostics by opening the file and waiting for publishDiagnostics.

        Note: LSP diagnostics are push-based (server → client). We open the file
        and wait briefly for the server to publish diagnostics.
        """
        await self.open_document(file_path)
        # Give the server time to analyze
        await asyncio.sleep(1.5)
        # Return cached diagnostics (collected by _read_loop)
        uri = Path(file_path).as_uri()
        return self._cached_diagnostics.get(uri, [])

    # ---- Internal JSON-RPC communication ----

    _cached_diagnostics: Dict[str, List[Dict]] = {}

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _request(self, method: str, params: Any, timeout: float = 15) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        req_id = self._next_id()
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        await self._send(msg)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            logger.warning(f"LSP request timed out: {method} (id={req_id})")
            return None

    async def _notify(self, method: str, params: Any):
        """Send a JSON-RPC notification (no response expected)."""
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._send(msg)

    async def _send(self, msg: dict):
        """Send a JSON-RPC message with Content-Length header."""
        if not self.process or not self.process.stdin:
            return
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + body)
        await self.process.stdin.drain()

    async def _read_loop(self):
        """Background task to read JSON-RPC messages from stdout."""
        try:
            while self.process and self.process.returncode is None:
                # Read Content-Length header
                content_length = 0

                while True:
                    stdout = self.process.stdout
                    assert stdout is not None
                    byte = await stdout.read(1)
                    if not byte:
                        return  # EOF
                    self._read_buf += byte

                    # Look for \r\n\r\n (end of headers)
                    if self._read_buf.endswith(b"\r\n\r\n"):
                        headers = self._read_buf.decode("ascii", errors="replace")
                        self._read_buf = b""
                        for line in headers.split("\r\n"):
                            if line.lower().startswith("content-length:"):
                                content_length = int(line.split(":", 1)[1].strip())
                        break

                if content_length <= 0:
                    continue

                # Read body
                body = await stdout.readexactly(content_length)
                try:
                    msg = json.loads(body)
                except json.JSONDecodeError:
                    continue

                self._handle_message(msg)

        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            logger.error(f"LSP read loop error ({self.language}): {e}")

    def _handle_message(self, msg: dict):
        """Dispatch incoming JSON-RPC message."""
        if "id" in msg and "method" not in msg:
            # Response to our request
            req_id = msg["id"]
            future = self._pending.pop(req_id, None)
            if future and not future.done():
                if "error" in msg:
                    err = msg["error"]
                    logger.warning(f"LSP error (id={req_id}): {err.get('message', err)}")
                    future.set_result(None)
                else:
                    future.set_result(msg.get("result"))
        elif "method" in msg and "id" not in msg:
            # Notification from server
            method = msg["method"]
            if method == "textDocument/publishDiagnostics":
                params = msg.get("params", {})
                uri = params.get("uri", "")
                diags = params.get("diagnostics", [])
                self._cached_diagnostics[uri] = [
                    {
                        "range": d.get("range", {}),
                        "severity": self._severity_label(d.get("severity", 1)),
                        "message": d.get("message", ""),
                        "source": d.get("source", ""),
                        "code": d.get("code"),
                    }
                    for d in diags
                ]

    # ---- Helpers ----

    @staticmethod
    def _severity_label(severity: int) -> str:
        return {1: "error", 2: "warning", 3: "information", 4: "hint"}.get(severity, "unknown")

    @staticmethod
    def _detect_language(file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return LANG_MAP.get(ext, "plaintext")

    @staticmethod
    def _normalize_locations(result) -> List[Dict]:
        """Normalize LSP Location/LocationLink responses to a uniform list."""
        if result is None:
            return []
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list):
            return []

        locations = []
        for item in result:
            if "targetUri" in item:
                # LocationLink
                uri = item["targetUri"]
                rng = item.get("targetSelectionRange") or item.get("targetRange", {})
            elif "uri" in item:
                # Location
                uri = item["uri"]
                rng = item.get("range", {})
            else:
                continue

            start = rng.get("start", {})
            file_path = _uri_to_path(uri)
            locations.append({
                "file": file_path,
                "line": start.get("line", 0) + 1,  # Convert 0-based → 1-based
                "character": start.get("character", 0) + 1,
                "uri": uri,
            })
        return locations

    def _flatten_symbols(self, symbols: List[Dict], parent: str = "") -> List[Dict]:
        """Flatten potentially hierarchical DocumentSymbol responses."""
        result = []
        for s in symbols:
            sym = self._format_symbol(s, parent)
            result.append(sym)
            children = s.get("children", [])
            if children:
                container = s.get("name", "")
                result.extend(self._flatten_symbols(children, parent=container))
        return result

    @staticmethod
    def _format_symbol(s: Dict, parent: str = "") -> Dict:
        """Format a symbol for display."""
        kind_map = {
            1: "File", 2: "Module", 3: "Namespace", 4: "Package",
            5: "Class", 6: "Method", 7: "Property", 8: "Field",
            9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
            13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
            21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
            25: "Operator", 26: "TypeParameter",
        }

        # DocumentSymbol format
        loc = s.get("location", {})
        rng = s.get("selectionRange") or s.get("range") or loc.get("range", {})
        start = rng.get("start", {})

        file_path = ""
        if "location" in s:
            file_path = _uri_to_path(loc.get("uri", ""))

        sym = {
            "name": s.get("name", ""),
            "kind": kind_map.get(s.get("kind", 0), "Unknown"),
            "line": start.get("line", 0) + 1,
            "character": start.get("character", 0) + 1,
        }
        if file_path:
            sym["file"] = file_path
        if parent:
            sym["container"] = parent
        detail = s.get("detail")
        if detail:
            sym["detail"] = detail
        return sym


class LspManager:
    """Manages multiple language server instances keyed by (language, workspace)."""

    def __init__(self):
        self._servers: Dict[str, LspServerConnection] = {}  # key: "lang:workspace"
        self._lock = asyncio.Lock()

    async def ensure_server(self, file_path: str, workspace_root: Optional[str] = None
                            ) -> Optional[LspServerConnection]:
        """Get or start a language server for the given file.

        Returns the server connection, or None if the language is unsupported
        or the server binary is not installed.
        """
        ext = Path(file_path).suffix.lower()
        lang = LANG_MAP.get(ext)
        if not lang:
            return None

        server_key_lang = LANG_TO_SERVER_KEY.get(lang, lang)
        config = SERVER_CONFIGS.get(server_key_lang)
        if not config:
            return None

        # Determine workspace root
        if not workspace_root:
            workspace_root = _find_workspace_root(file_path)

        cache_key = f"{server_key_lang}:{workspace_root}"

        async with self._lock:
            server = self._servers.get(cache_key)
            if server and server.is_alive:
                return server

            # Check if binary exists (PATH + current venv)
            binary = config["check"]
            resolved_binary = _find_binary(binary)
            if not resolved_binary:
                logger.warning(f"LSP binary not found: {binary}. Install it to enable {lang} code intelligence.")
                return None

            # Resolve full command path (replace first element with resolved path)
            cmd = list(config["cmd"])
            cmd[0] = resolved_binary

            # Start new server
            server = LspServerConnection(
                language=server_key_lang,
                cmd=cmd,
                workspace_root=workspace_root,
                init_options=config.get("init_options"),
            )
            ok = await server.start()
            if ok:
                self._servers[cache_key] = server
                return server
            return None

    async def shutdown(self):
        """Stop all language servers."""
        async with self._lock:
            for key, server in self._servers.items():
                try:
                    await server.stop()
                except Exception as e:
                    logger.warning(f"Error stopping LSP server {key}: {e}")
            self._servers.clear()
        logger.info("All LSP servers shut down")

    def get_status(self) -> List[Dict]:
        """Get status of all running language servers."""
        return [
            {
                "key": key,
                "language": srv.language,
                "workspace": srv.workspace_root,
                "alive": srv.is_alive,
                "open_files": len(srv._open_files),
            }
            for key, srv in self._servers.items()
        ]


# ---- Module-level singleton ----

_lsp_manager: Optional[LspManager] = None


def get_lsp_manager() -> LspManager:
    """Get the singleton LspManager instance."""
    global _lsp_manager
    if _lsp_manager is None:
        _lsp_manager = LspManager()
    return _lsp_manager


async def shutdown_lsp_manager():
    """Shut down the singleton LspManager."""
    global _lsp_manager
    if _lsp_manager:
        await _lsp_manager.shutdown()
        _lsp_manager = None


# ---- Utility functions ----

def _uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a local path."""
    if uri.startswith("file://"):
        from urllib.parse import unquote, urlparse
        parsed = urlparse(uri)
        return unquote(parsed.path)
    return uri


def _find_binary(name: str) -> Optional[str]:
    """Find a binary in PATH or the current Python venv."""
    # 1. Check PATH
    found = shutil.which(name)
    if found:
        return found
    # 2. Check current Python's venv bin dir (e.g. venv/bin/pylsp)
    import sys
    venv_bin = os.path.join(sys.prefix, "bin", name)
    if os.path.isfile(venv_bin) and os.access(venv_bin, os.X_OK):
        return venv_bin
    # 3. Check Scripts dir on Windows
    venv_scripts = os.path.join(sys.prefix, "Scripts", name + ".exe")
    if os.path.isfile(venv_scripts):
        return venv_scripts
    return None


def _find_workspace_root(file_path: str) -> str:
    """Walk up from file_path to find a workspace root (git root, or directory with markers)."""
    markers = [".git", "pyproject.toml", "setup.py", "package.json",
               "Cargo.toml", "go.mod", "tsconfig.json", ".vscode"]
    current = Path(file_path).resolve()
    if current.is_file():
        current = current.parent

    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return str(current)
        current = current.parent

    # Fallback: directory of the file
    return str(Path(file_path).resolve().parent)
