"""
MCP Router for FastAPI
外部 MCP Server 管理端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class AddServerRequest(BaseModel):
    """添加 MCP Server 请求"""
    name: str = Field(..., description="Server name")
    command: str = Field(..., description="Command to start server")
    args: List[str] = Field(default=[], description="Command arguments")
    env: Dict[str, str] = Field(default={}, description="Environment variables")
    description: str = Field(default="", description="Server description")


class ServerResponse(BaseModel):
    """Server 响应"""
    success: bool
    name: Optional[str] = None
    error: Optional[str] = None


# ============ Endpoints ============

@router.get("/mcp/servers")
async def list_servers() -> Dict[str, Any]:
    """列出所有配置的 MCP servers"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        servers = manager.get_configured_servers()
        return {
            "servers": servers,
            "total": len(servers),
            "running": sum(1 for s in servers if s.get("running")),
        }
    except Exception as e:
        logger.error(f"List MCP servers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers", response_model=ServerResponse)
async def add_server(request: AddServerRequest) -> ServerResponse:
    """添加并启动 MCP server"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        success = manager.add_server(
            name=request.name, command=request.command,
            args=request.args, env=request.env,
            description=request.description,
        )
        if success:
            return ServerResponse(success=True, name=request.name)
        return ServerResponse(success=False, name=request.name,
                            error="Failed to start server")
    except Exception as e:
        logger.error(f"Add MCP server error: {e}")
        return ServerResponse(success=False, error=str(e))


@router.delete("/mcp/servers/{server_name}", response_model=ServerResponse)
async def remove_server(server_name: str) -> ServerResponse:
    """停止并移除 MCP server"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        manager.remove_server(server_name)
        return ServerResponse(success=True, name=server_name)
    except Exception as e:
        logger.error(f"Remove MCP server error: {e}")
        return ServerResponse(success=False, error=str(e))


@router.post("/mcp/servers/{server_name}/refresh", response_model=ServerResponse)
async def refresh_server(server_name: str) -> ServerResponse:
    """刷新（重启）MCP server"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        success = manager.refresh_server(server_name)
        if success:
            return ServerResponse(success=True, name=server_name)
        return ServerResponse(success=False, name=server_name,
                            error="Failed to refresh server")
    except Exception as e:
        logger.error(f"Refresh MCP server error: {e}")
        return ServerResponse(success=False, error=str(e))


@router.post("/mcp/refresh-tools")
async def refresh_tools() -> Dict[str, Any]:
    """Discover tools for newly added MCP servers that aren't in the cache yet."""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        results = manager.discover_uncached_tools()
        discovered = sum(1 for r in results.values() if "tools" in r)
        return {
            "success": True,
            "discovered": discovered,
            "total_servers": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Refresh MCP tools error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/tools")
async def list_mcp_tools() -> Dict[str, Any]:
    """列出所有外部 MCP 工具"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        tools = manager.get_all_tools()
        return {
            "tools": tools,
            "total": len(tools),
        }
    except Exception as e:
        logger.error(f"List MCP tools error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/initialize")
async def initialize_mcp() -> Dict[str, Any]:
    """初始化所有 MCP servers"""
    try:
        from ..services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        manager.load_config(lazy=False)
        status = manager.get_status()
        return {
            "success": True,
            "servers": status,
            "total_running": len(status),
        }
    except Exception as e:
        logger.error(f"Initialize MCP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
