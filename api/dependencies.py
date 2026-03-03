"""
Springo FastAPI Dependencies
依赖注入模块
"""
from typing import Annotated, Optional
from fastapi import Depends, Header, HTTPException, status
import logging

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


# Settings dependency
def get_app_settings() -> Settings:
    """Get application settings"""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


# Session ID dependency
async def get_session_id(
    x_session_id: Annotated[Optional[str], Header()] = None
) -> Optional[str]:
    """Extract session ID from header"""
    return x_session_id


SessionIdDep = Annotated[Optional[str], Depends(get_session_id)]


# API Key validation (optional, for future use)
async def verify_api_key(
    x_api_key: Annotated[Optional[str], Header()] = None,
    settings: Settings = Depends(get_app_settings)
) -> bool:
    """Verify API key if configured"""
    # TODO: Implement API key validation if needed
    # For now, always return True (no auth required)
    return True


ApiKeyDep = Annotated[bool, Depends(verify_api_key)]


# Bedrock client dependency (will be implemented in Phase 2)
# async def get_bedrock_client():
#     """Get Bedrock client instance"""
#     from .services.bedrock import BedrockService
#     return BedrockService()
# 
# BedrockDep = Annotated[BedrockService, Depends(get_bedrock_client)]


# Tool Manager dependency (will be implemented in Phase 3)
# async def get_tool_manager():
#     """Get MCP manager instance"""
#     from .services.tool_manager import ToolManager
#     return ToolManager()
# 
# ToolManagerDep = Annotated[ToolManager, Depends(get_tool_manager)]


# Session store dependency (will be implemented in Phase 5)
# async def get_session_store():
#     """Get session store instance"""
#     from .services.session_store import SessionStore
#     return SessionStore()
# 
# SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
