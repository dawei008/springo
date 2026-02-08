"""
MCP Tools Manager for FastAPI
异步 MCP 工具管理器，使用 ThreadPoolExecutor 隔离同步操作
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


class MCPManager:
    """
    异步 MCP 工具管理器
    
    使用 ThreadPoolExecutor 将同步的 MCP 工具调用隔离到线程池中，
    避免阻塞 asyncio 事件循环。
    """
    
    def __init__(self, max_workers: int = 10):
        """
        初始化 MCP 管理器

        Args:
            max_workers: 线程池最大工作线程数
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._semaphore = asyncio.Semaphore(max_workers)  # Prevent executor exhaustion
        self._tools_loaded = False
        self._tool_definitions: List[Dict[str, Any]] = []
        self._tool_handlers: Dict[str, callable] = {}
        self._tool_defs_last_refresh: float = 0
        self._tool_defs_ttl: float = 30  # seconds - refresh definitions periodically
        
    async def initialize(self) -> None:
        """异步初始化，加载工具定义"""
        if self._tools_loaded:
            return
            
        try:
            # 在线程池中加载工具（可能涉及文件 I/O）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._load_tools_sync)
            self._tools_loaded = True
            logger.info(f"MCP Manager initialized with {len(self._tool_definitions)} tools")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Manager: {e}")
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
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
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
    
    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步执行单个工具 (with semaphore to prevent executor exhaustion)

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            工具执行结果
        """
        async with self._semaphore:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    partial(self._execute_tool_sync, tool_name, tool_input)
                )
                return result
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
    
    async def close(self) -> None:
        """关闭管理器，清理资源"""
        self.executor.shutdown(wait=True)
        logger.info("MCP Manager closed")


# 全局单例
_mcp_manager: Optional[MCPManager] = None


async def get_mcp_manager() -> MCPManager:
    """获取 MCP 管理器单例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
        await _mcp_manager.initialize()
    return _mcp_manager


async def close_mcp_manager() -> None:
    """关闭 MCP 管理器"""
    global _mcp_manager
    if _mcp_manager is not None:
        await _mcp_manager.close()
        _mcp_manager = None
