"""
Springo FastAPI Main Application
FastAPI 应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting Springo FastAPI on {settings.host}:{settings.port}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"AWS Region: {settings.aws_region}")
    logger.info(f"Bedrock Model: {settings.bedrock_model_id}")

    # Initialize MCP Manager (built-in tools)
    global _mcp_initialized
    try:
        from .services.mcp_manager import get_mcp_manager, close_mcp_manager
        mcp_manager = await get_mcp_manager()
        _mcp_initialized = True
        logger.info(f"MCP Manager initialized with {len(mcp_manager.get_tool_definitions())} tools")
    except Exception as e:
        logger.warning(f"Failed to initialize MCP Manager: {e}")

    # Initialize External MCP Servers (lazy)
    try:
        from .services.mcp_client import initialize_external_mcp
        initialize_external_mcp(lazy=True)
        logger.info("External MCP servers config loaded (lazy mode)")
    except Exception as e:
        logger.warning(f"Failed to load external MCP config: {e}")

    # Initialize Session Store
    try:
        from .services.session_store import get_session_store
        store = get_session_store()
        sessions = store.list_sessions()
        logger.info(f"Session Store initialized with {len(sessions)} sessions")
    except Exception as e:
        logger.warning(f"Failed to initialize Session Store: {e}")

    # Initialize Memory Sync (if configured)
    try:
        from .services.memory_sync import init_memory_sync
        init_memory_sync()
    except Exception as e:
        logger.debug(f"Memory sync not started: {e}")

    # Initialize S3 Sync (if configured)
    try:
        from .services.s3_sync import init_s3_sync
        init_s3_sync()
    except Exception as e:
        logger.debug(f"S3 sync not started: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Springo FastAPI...")
    try:
        from .services.mcp_manager import close_mcp_manager
        await close_mcp_manager()
    except Exception as e:
        logger.warning(f"Error closing MCP Manager: {e}")
    try:
        from .services.mcp_client import shutdown_external_mcp
        shutdown_external_mcp()
    except Exception as e:
        logger.warning(f"Error closing external MCP: {e}")
    try:
        from .services.memory_sync import shutdown_memory_sync
        shutdown_memory_sync()
    except Exception as e:
        logger.warning(f"Error closing memory sync: {e}")
    try:
        from .services.s3_sync import shutdown_s3_sync
        shutdown_s3_sync()
    except Exception as e:
        logger.warning(f"Error closing S3 sync: {e}")


# Create FastAPI application
app = FastAPI(
    title="Springo API",
    description="Springo - AI Assistant Backend powered by Amazon Bedrock",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "file://",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if not settings.debug else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# MCP lazy init middleware - fallback if lifespan init fails (Flask-aligned)
_mcp_initialized = False


class MCPLazyInitMiddleware(BaseHTTPMiddleware):
    """Auto-initialize MCP servers on first request if not already initialized"""

    async def dispatch(self, request, call_next):
        global _mcp_initialized
        if not _mcp_initialized:
            try:
                from .services.mcp_manager import get_mcp_manager
                await get_mcp_manager()
                _mcp_initialized = True
            except Exception as e:
                logger.warning(f"MCP lazy init on request failed: {e}")
        return await call_next(request)


app.add_middleware(MCPLazyInitMiddleware)


# Health check endpoint (root level)
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "framework": "FastAPI",
        "model": settings.bedrock_model_id
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Springo API",
        "version": "2.0.0",
        "docs": "/docs"
    }


# Import and include routers
from .routers import messages, tools, sessions, context, news, images, health
from .routers import config, memory, skills, tool_results
from .routers import models, mcp

app.include_router(messages.router, prefix="/v1", tags=["messages"])
app.include_router(tools.router, prefix="/v1", tags=["tools"])
app.include_router(sessions.router, prefix="/v1", tags=["sessions"])
app.include_router(context.router, prefix="/v1", tags=["context"])
app.include_router(news.router, prefix="/v1", tags=["news"])
app.include_router(images.router, prefix="/v1", tags=["images"])
app.include_router(health.router, tags=["health"])
# 配置与管理路由
app.include_router(config.router, prefix="/v1", tags=["config"])
app.include_router(memory.router, prefix="/v1", tags=["memory"])
app.include_router(skills.router, prefix="/v1", tags=["skills"])
app.include_router(tool_results.router, prefix="/v1", tags=["tool-results"])
# 新增路由
app.include_router(models.router, prefix="/v1", tags=["models"])
app.include_router(mcp.router, prefix="/v1", tags=["mcp"])


from fastapi.responses import JSONResponse
from fastapi import Request


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], include_in_schema=False)
async def catch_all(request: Request, path: str):
    """Catch-all for unknown routes"""
    return JSONResponse(
        status_code=404,
        content={"error": f"Unknown endpoint: /{path}"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
