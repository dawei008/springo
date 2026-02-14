"""
LSP Tool Handlers
Code intelligence tools powered by Language Server Protocol.

These handlers are called synchronously from ThreadPoolExecutor by mcp_tools/core.py.
LSP servers run on the main asyncio event loop (where subprocess IO is registered),
so we use asyncio.run_coroutine_threadsafe to schedule work on the main loop.
"""

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Reference to the main event loop, set during startup
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Called during app startup to capture the main event loop reference."""
    global _main_loop
    _main_loop = loop


def _run_async(coro):
    """Run an async coroutine on the main event loop from a sync thread.

    Uses run_coroutine_threadsafe to schedule on the main loop where
    LSP subprocess IO is registered.
    """
    global _main_loop
    if _main_loop is not None and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result(timeout=60)

    # Fallback: try creating a new loop (won't work with existing servers)
    new_loop = asyncio.new_event_loop()
    try:
        return new_loop.run_until_complete(coro)
    finally:
        new_loop.close()


def _get_manager():
    from api.services.lsp_manager import get_lsp_manager
    return get_lsp_manager()


def lsp_go_to_definition(file_path: str, line: int, character: int,
                          workspace_root: str = "") -> Dict[str, Any]:
    """Find where a symbol is defined."""
    async def _run():
        mgr = _get_manager()
        server = await mgr.ensure_server(file_path, workspace_root or None)
        if not server:
            return _no_server_error(file_path)
        locations = await server.go_to_definition(file_path, line - 1, character - 1)
        if not locations:
            return {"result": "No definition found", "locations": []}
        return {
            "result": f"Found {len(locations)} definition(s)",
            "locations": locations,
        }
    return _run_async(_run())


def lsp_find_references(file_path: str, line: int, character: int,
                         include_declaration: bool = True,
                         workspace_root: str = "") -> Dict[str, Any]:
    """Find all references to a symbol."""
    async def _run():
        mgr = _get_manager()
        server = await mgr.ensure_server(file_path, workspace_root or None)
        if not server:
            return _no_server_error(file_path)
        locations = await server.find_references(file_path, line - 1, character - 1, include_declaration)
        if not locations:
            return {"result": "No references found", "locations": []}
        return {
            "result": f"Found {len(locations)} reference(s)",
            "locations": locations,
        }
    return _run_async(_run())


def lsp_hover(file_path: str, line: int, character: int,
              workspace_root: str = "") -> Dict[str, Any]:
    """Get type information and documentation for a symbol."""
    async def _run():
        mgr = _get_manager()
        server = await mgr.ensure_server(file_path, workspace_root or None)
        if not server:
            return _no_server_error(file_path)
        content = await server.hover(file_path, line - 1, character - 1)
        if not content:
            return {"result": "No hover information available"}
        return {"result": content}
    return _run_async(_run())


def lsp_document_symbols(file_path: str,
                          workspace_root: str = "") -> Dict[str, Any]:
    """Get all symbols (functions, classes, variables) in a file."""
    async def _run():
        mgr = _get_manager()
        server = await mgr.ensure_server(file_path, workspace_root or None)
        if not server:
            return _no_server_error(file_path)
        symbols = await server.document_symbols(file_path)
        if not symbols:
            return {"result": "No symbols found", "symbols": []}
        return {
            "result": f"Found {len(symbols)} symbol(s)",
            "symbols": symbols,
        }
    return _run_async(_run())


def lsp_workspace_symbol(query: str, file_path: str = "",
                          workspace_root: str = "") -> Dict[str, Any]:
    """Search for symbols across the entire workspace."""
    async def _run():
        mgr = _get_manager()
        # Need a file_path to determine language and workspace
        target = file_path or workspace_root
        if not target:
            return {"error": "Provide file_path or workspace_root to identify the workspace"}
        server = await mgr.ensure_server(target, workspace_root or None)
        if not server:
            return _no_server_error(target)
        symbols = await server.workspace_symbol(query)
        if not symbols:
            return {"result": "No symbols found", "symbols": []}
        return {
            "result": f"Found {len(symbols)} symbol(s)",
            "symbols": symbols,
        }
    return _run_async(_run())


def lsp_diagnostics(file_path: str,
                     workspace_root: str = "") -> Dict[str, Any]:
    """Get errors and warnings for a file."""
    async def _run():
        mgr = _get_manager()
        server = await mgr.ensure_server(file_path, workspace_root or None)
        if not server:
            return _no_server_error(file_path)
        diags = await server.diagnostics(file_path)
        if not diags:
            return {"result": "No diagnostics (file is clean)", "diagnostics": []}

        # Format for readability
        formatted = []
        for d in diags:
            rng = d.get("range", {})
            start = rng.get("start", {})
            formatted.append({
                "line": start.get("line", 0) + 1,
                "character": start.get("character", 0) + 1,
                "severity": d.get("severity", "unknown"),
                "message": d.get("message", ""),
                "source": d.get("source", ""),
            })

        errors = sum(1 for d in formatted if d["severity"] == "error")
        warnings = sum(1 for d in formatted if d["severity"] == "warning")
        return {
            "result": f"{errors} error(s), {warnings} warning(s)",
            "diagnostics": formatted,
        }
    return _run_async(_run())


def _no_server_error(file_path: str) -> Dict[str, Any]:
    """Return a helpful error when no LSP server is available."""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    install_hints = {
        ".py": "pip install python-lsp-server",
        ".ts": "npm install -g typescript-language-server typescript",
        ".tsx": "npm install -g typescript-language-server typescript",
        ".js": "npm install -g typescript-language-server typescript",
        ".jsx": "npm install -g typescript-language-server typescript",
        ".go": "go install golang.org/x/tools/gopls@latest",
        ".rs": "rustup component add rust-analyzer",
    }
    hint = install_hints.get(ext, "")
    msg = f"No LSP server available for {ext} files."
    if hint:
        msg += f" Install with: {hint}"
    return {"error": msg}
