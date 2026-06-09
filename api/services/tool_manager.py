"""
Tool Manager for FastAPI
异步工具管理器，使用 ThreadPoolExecutor 隔离同步操作
"""
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
from functools import partial
import sys
import os

# Add parent springo directory to path for importing mcp_tools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'springo'))

logger = logging.getLogger(__name__)


class ToolManager:
    """
    异步工具管理器

    使用 ThreadPoolExecutor 将同步的工具调用隔离到线程池中，
    避免阻塞 asyncio 事件循环。
    """

    # Per-session concurrency limit: prevents one session from starving others
    PER_SESSION_MAX_CONCURRENT = 10

    def __init__(self, max_workers: int = 100):
        """
        初始化 MCP 管理器

        Args:
            max_workers: 线程池最大工作线程数 (100 = 10 sessions × 10 concurrent tools)
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._global_semaphore = asyncio.Semaphore(max_workers)
        self._session_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._tools_loaded = False
        self._tool_definitions: List[Dict[str, Any]] = []
        self._tool_handlers: Dict[str, callable] = {}
        self._tool_defs_last_refresh: float = 0
        self._tool_defs_ttl: float = 30  # seconds - refresh definitions periodically
        # Track active asyncio tasks per session for cancellation
        self._session_tasks: Dict[str, set] = {}  # session_id → {asyncio.Task, ...}
        self._session_tasks_lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """异步初始化，加载工具定义"""
        if self._tools_loaded:
            return
            
        try:
            # 在线程池中加载工具（可能涉及文件 I/O）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._load_tools_sync)
            self._tools_loaded = True
            logger.info(f"Tool Manager initialized with {len(self._tool_definitions)} tools")
        except Exception as e:
            logger.error(f"Failed to initialize Tool Manager: {e}")
            raise
    
    def _load_tools_sync(self) -> None:
        """同步加载工具（在线程池中执行）"""
        try:
            from mcp_tools import get_tool_definitions, TOOL_HANDLERS
            self._tool_definitions = get_tool_definitions()
            self._tool_handlers = TOOL_HANDLERS
        except ImportError as e:
            logger.warning(f"Could not import mcp_tools: {e}")
            # 使用内置工具定义
            self._tool_definitions = self._get_builtin_definitions()
            self._tool_handlers = self._get_builtin_handlers()
    
    def _get_builtin_definitions(self) -> List[Dict[str, Any]]:
        """获取内置工具定义（当无法导入 mcp_tools 时）"""
        return [
            {
                "name": "read_file",
                "description": "Read the contents of a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "Content to write"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "execute_command",
                "description": "Execute a shell command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"]
                }
            }
        ]
    
    def _get_builtin_handlers(self) -> Dict[str, callable]:
        """获取内置工具处理器"""
        import subprocess
        
        def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
            try:
                with open(os.path.expanduser(path), 'r', encoding=encoding) as f:
                    content = f.read()
                return {"content": content, "path": path, "size": len(content)}
            except Exception as e:
                return {"error": str(e)}
        
        def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
            try:
                full_path = os.path.expanduser(path)
                parent = os.path.dirname(full_path)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                with open(full_path, 'w', encoding=encoding) as f:
                    f.write(content)
                return {"success": True, "path": path, "size": len(content)}
            except Exception as e:
                return {"error": str(e)}
        
        def execute_command(command: str, timeout: int = 300) -> Dict[str, Any]:
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=timeout
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode
                }
            except subprocess.TimeoutExpired:
                return {"error": f"Command timed out after {timeout} seconds"}
            except Exception as e:
                return {"error": str(e)}
        
        return {
            "read_file": read_file,
            "write_file": write_file,
            "execute_command": execute_command,
        }
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具定义 (dynamic - refreshed periodically via TTL)"""
        now = time.time()
        if now - self._tool_defs_last_refresh > self._tool_defs_ttl:
            try:
                from mcp_tools import get_tool_definitions
                self._tool_definitions = get_tool_definitions()
                self._tool_defs_last_refresh = now
            except ImportError:
                pass  # Use cached definitions
            except Exception as e:
                logger.warning(f"Failed to refresh tool definitions: {e}")
        return self._tool_definitions
    
    def _get_session_semaphore(self, session_id: str) -> asyncio.Semaphore:
        """Get or create a per-session semaphore."""
        if session_id not in self._session_semaphores:
            self._session_semaphores[session_id] = asyncio.Semaphore(
                self.PER_SESSION_MAX_CONCURRENT
            )
        return self._session_semaphores[session_id]

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any],
                           session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        异步执行单个工具 (with per-session + global semaphore)

        Uses two-level semaphore to prevent one session from starving others:
        - Per-session semaphore: max PER_SESSION_MAX_CONCURRENT concurrent tools
        - Global semaphore: max max_workers total across all sessions

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            session_id: Optional session ID for per-session limiting

        Returns:
            工具执行结果
        """
        session_sem = self._get_session_semaphore(session_id) if session_id else None

        async def _run():
            async with self._global_semaphore:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    self.executor,
                    partial(self._execute_tool_sync, tool_name, tool_input)
                )

        try:
            if session_sem:
                async with session_sem:
                    return await _run()
            else:
                return await _run()
        except asyncio.CancelledError:
            logger.info(f"Tool execution cancelled: {tool_name}")
            return {"error": "Tool execution cancelled by user"}
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {"error": f"Tool execution failed: {e}"}
    
    def _execute_tool_sync(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行工具（在线程池中执行, with crash detection）"""
        try:
            # 首先尝试使用 mcp_tools 的 execute_tool
            try:
                from mcp_tools import execute_tool
                return execute_tool(tool_name, tool_input)
            except ImportError:
                pass

            # 回退到内置处理器
            if tool_name not in self._tool_handlers:
                return {"error": f"Unknown tool: {tool_name}"}

            handler = self._tool_handlers[tool_name]
            return handler(**tool_input)

        except (BrokenPipeError, ConnectionError, OSError) as e:
            # MCP server process crash detection
            logger.error(f"MCP server may have crashed during {tool_name}: {e}")
            self._tools_loaded = False  # Force re-initialization on next call
            return {"error": f"MCP server connection lost during {tool_name}: {e}"}
        except TypeError as e:
            return {"error": f"Invalid arguments for {tool_name}: {e}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {e}"}
    
    async def execute_tools_parallel(
        self, 
        tool_calls: List[Dict[str, Any]],
        max_parallel: int = 10
    ) -> List[Dict[str, Any]]:
        """
        并行执行多个工具
        
        Args:
            tool_calls: 工具调用列表，每个元素包含 {"name": str, "input": dict, "id": str}
            max_parallel: 最大并行数
            
        Returns:
            工具执行结果列表，顺序与输入对应
        """
        if not tool_calls:
            return []
        
        # 限制并行数
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def execute_with_semaphore(tool_call: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                tool_name = tool_call.get("name", "")
                tool_input = tool_call.get("input", {})
                tool_id = tool_call.get("id", "")
                
                result = await self.execute_tool(tool_name, tool_input)
                
                return {
                    "tool_use_id": tool_id,
                    "name": tool_name,
                    "result": result
                }
        
        # 并行执行所有工具
        tasks = [execute_with_semaphore(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "tool_use_id": tool_calls[i].get("id", ""),
                    "name": tool_calls[i].get("name", ""),
                    "result": {"error": str(result)}
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def cancel_session_tools(self, session_id: str) -> int:
        """Cancel all running tool tasks for a session and kill subprocesses.

        Returns the number of cancelled tasks + killed processes.
        """
        cancelled = 0

        # 1. Kill registered subprocesses (execute_command Popen processes)
        try:
            from mcp_tools.handlers.file_tools import kill_active_processes
            killed = kill_active_processes(session_id)
            if killed:
                logger.info(f"[Cancel] Killed {killed} active subprocess(es) for session {session_id}")
            cancelled += killed
        except ImportError:
            pass

        return cancelled

    async def close(self) -> None:
        """关闭管理器，清理资源"""
        self.executor.shutdown(wait=True)
        logger.info("Tool Manager closed")


# 全局单例
_tool_manager: Optional[ToolManager] = None


async def get_tool_manager() -> ToolManager:
    """获取工具管理器单例"""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ToolManager()
        await _tool_manager.initialize()
    return _tool_manager


async def close_tool_manager() -> None:
    """关闭工具管理器"""
    global _tool_manager
    if _tool_manager is not None:
        await _tool_manager.close()
        _tool_manager = None
