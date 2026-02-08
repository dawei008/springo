"""
Tools Router for FastAPI
工具执行端点
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

from ..services.mcp_manager import get_mcp_manager, MCPManager

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_SIZE = 100 * 1024  # 100KB truncation limit

router = APIRouter()


# ============ Request/Response Models ============

class ToolExecuteRequest(BaseModel):
    """工具执行请求"""
    name: str = Field(..., description="Tool name")
    input: Dict[str, Any] = Field(default_factory=dict, description="Tool input parameters")


class ToolExecuteResponse(BaseModel):
    """工具执行响应"""
    success: bool
    name: str
    result: Dict[str, Any]


class ToolsBatchRequest(BaseModel):
    """批量工具执行请求"""
    tools: List[ToolExecuteRequest] = Field(..., description="List of tools to execute")
    parallel: bool = Field(default=True, description="Execute tools in parallel")


class ToolsBatchResponse(BaseModel):
    """批量工具执行响应"""
    success: bool
    results: List[Dict[str, Any]]
    total: int
    succeeded: int
    failed: int


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]


class ToolsListResponse(BaseModel):
    """工具列表响应"""
    tools: List[ToolDefinition]
    count: int


# ============ Endpoints ============

@router.post("/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    request: ToolExecuteRequest,
    mcp_manager: MCPManager = Depends(get_mcp_manager)
):
    """
    执行单个工具
    
    Execute a single tool with the given input parameters.
    """
    try:
        # Validate required params for known tools to detect truncated model responses
        _validate_tool_params(request.name, request.input)

        result = await mcp_manager.execute_tool(request.name, request.input)

        # Truncate large results
        result = _truncate_result(result)

        # 检查是否有错误
        has_error = "error" in result

        return ToolExecuteResponse(
            success=not has_error,
            name=request.name,
            result=result
        )
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return ToolExecuteResponse(
            success=False,
            name=request.name,
            result={"error": str(e)}
        )


@router.post("/tools/batch", response_model=ToolsBatchResponse)
async def execute_tools_batch(
    request: ToolsBatchRequest,
    mcp_manager: MCPManager = Depends(get_mcp_manager)
):
    """
    批量执行工具
    
    Execute multiple tools, optionally in parallel.
    """
    try:
        tool_calls = [
            {"name": t.name, "input": t.input, "id": f"tool_{i}"}
            for i, t in enumerate(request.tools)
        ]
        
        if request.parallel:
            results = await mcp_manager.execute_tools_parallel(tool_calls)
        else:
            # 串行执行
            results = []
            for tc in tool_calls:
                result = await mcp_manager.execute_tool(tc["name"], tc["input"])
                results.append({
                    "tool_use_id": tc["id"],
                    "name": tc["name"],
                    "result": result
                })
        
        # 统计结果
        succeeded = sum(1 for r in results if "error" not in r.get("result", {}))
        failed = len(results) - succeeded
        
        return ToolsBatchResponse(
            success=failed == 0,
            results=results,
            total=len(results),
            succeeded=succeeded,
            failed=failed
        )
    except Exception as e:
        logger.error(f"Batch tool execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools", response_model=ToolsListResponse)
@router.get("/tools/list", response_model=ToolsListResponse, include_in_schema=False)
async def list_tools(
    mcp_manager: MCPManager = Depends(get_mcp_manager)
):
    """
    获取所有可用工具列表
    
    Get list of all available tools with their definitions.
    """
    try:
        definitions = mcp_manager.get_tool_definitions()
        
        tools = [
            ToolDefinition(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {})
            )
            for t in definitions
        ]
        
        return ToolsListResponse(
            tools=tools,
            count=len(tools)
        )
    except Exception as e:
        logger.error(f"List tools error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_name}")
async def get_tool_info(
    tool_name: str,
    mcp_manager: MCPManager = Depends(get_mcp_manager)
):
    """
    获取单个工具的详细信息
    
    Get detailed information about a specific tool.
    """
    try:
        definitions = mcp_manager.get_tool_definitions()
        
        for tool in definitions:
            if tool.get("name") == tool_name:
                return {
                    "found": True,
                    "tool": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "input_schema": tool.get("input_schema")
                    }
                }
        
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get tool info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Helpers ============

# Required params for known tools (detect truncated model responses)
_TOOL_REQUIRED_PARAMS = {
    "write_file": ["path", "content"],
    "edit": ["path", "old_string", "new_string"],
    "execute_command": ["command"],
    "create_file": ["path", "content"],
    "replace_file": ["path", "content"],
    "web_search": ["query"],
    "web_fetch": ["url"],
    "read_file": ["path"],
    "create_directory": ["path"],
    "git_commit": ["message"],
}


def _validate_tool_params(tool_name: str, tool_input: Dict[str, Any]):
    """Validate required parameters for known tools to detect truncated model responses."""
    required = _TOOL_REQUIRED_PARAMS.get(tool_name)
    if not required:
        return
    missing = [p for p in required if p not in tool_input or not tool_input[p]]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Tool '{tool_name}' missing required parameters: {', '.join(missing)}. "
                   f"This may indicate a truncated model response."
        )


def _truncate_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate tool result content if it exceeds MAX_TOOL_RESULT_SIZE."""
    import json
    try:
        result_str = json.dumps(result, ensure_ascii=False)
        if len(result_str) > MAX_TOOL_RESULT_SIZE:
            # Try to truncate the 'output' or 'content' field
            for key in ("output", "content", "result"):
                if key in result and isinstance(result[key], str) and len(result[key]) > MAX_TOOL_RESULT_SIZE:
                    half = MAX_TOOL_RESULT_SIZE // 2
                    result[key] = (
                        result[key][:half]
                        + f"\n\n... [truncated {len(result[key]) - MAX_TOOL_RESULT_SIZE} chars] ...\n\n"
                        + result[key][-half // 2:]
                    )
                    return result
            # Generic truncation: convert to string and chop
            if len(result_str) > MAX_TOOL_RESULT_SIZE:
                result["_truncated"] = True
                result["_original_size"] = len(result_str)
    except Exception:
        pass
    return result
