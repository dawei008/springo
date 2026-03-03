"""
Health Router for FastAPI
健康检查端点
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import platform
import psutil
import os

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Response Models ============

class HealthResponse(BaseModel):
    """基本健康检查响应"""
    status: str
    version: str
    framework: str
    model: str


class DetailedHealthResponse(BaseModel):
    """详细健康检查响应"""
    status: str
    version: str
    framework: str
    model: str
    services: Dict[str, Any]
    system: Dict[str, Any]


# ============ Endpoints ============

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    基本健康检查
    
    Simple health check endpoint for load balancers and monitoring.
    """
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        framework="FastAPI",
        model=settings.bedrock_model_id
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check():
    """
    详细健康检查
    
    Comprehensive health check including service status and system info.
    """
    # 检查各服务状态
    services = {}
    
    # 检查 Bedrock 连接
    try:
        import boto3
        client = boto3.client('bedrock-runtime', region_name=settings.aws_region)
        services["bedrock"] = {"status": "available", "region": settings.aws_region}
    except Exception as e:
        services["bedrock"] = {"status": "error", "error": str(e)}
    
    # 检查 Tool Manager
    try:
        from ..services.tool_manager import get_tool_manager
        mcp = await get_tool_manager()
        tools_count = len(mcp.get_tool_definitions())
        services["mcp"] = {"status": "available", "tools": tools_count}
    except Exception as e:
        services["mcp"] = {"status": "error", "error": str(e)}
    
    # 检查 Session Store
    try:
        from ..services.session_store import get_session_store
        store = get_session_store()
        sessions = store.list_sessions()
        services["sessions"] = {"status": "available", "count": len(sessions)}
    except Exception as e:
        services["sessions"] = {"status": "error", "error": str(e)}
    
    # 系统信息
    system = {
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent
    }
    
    # 判断整体状态
    all_ok = all(s.get("status") != "error" for s in services.values())
    
    return DetailedHealthResponse(
        status="healthy" if all_ok else "degraded",
        version="2.0.0",
        framework="FastAPI",
        model=settings.bedrock_model_id,
        services=services,
        system=system
    )


@router.get("/health/ready")
async def readiness_check():
    """
    就绪检查
    
    Check if the application is ready to receive traffic.
    Used by Kubernetes readiness probes.
    """
    try:
        # 检查核心服务是否就绪
        from ..services.tool_manager import get_tool_manager
        await get_tool_manager()
        
        return {"ready": True}
    except Exception as e:
        return {"ready": False, "error": str(e)}


@router.get("/health/live")
async def liveness_check():
    """
    存活检查
    
    Check if the application is alive.
    Used by Kubernetes liveness probes.
    """
    return {"alive": True}
