"""
Springo FastAPI Main Application
FastAPI 应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from logging.handlers import RotatingFileHandler

from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

# Configure logging with rotation to prevent unbounded log growth
_log_level = logging.DEBUG if settings.debug else logging.INFO
_log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Console handler: INFO even in debug mode (keeps terminal readable)
logging.basicConfig(level=logging.INFO, format=_log_format)

# File handler: full debug logs with rotation
_log_dir = os.path.expanduser("~/.springo/logs")
os.makedirs(_log_dir, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "server.log"),
    maxBytes=50 * 1024 * 1024,  # 50 MB
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setLevel(_log_level)
_file_handler.setFormatter(logging.Formatter(_log_format))
logging.getLogger().addHandler(_file_handler)

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

    # Initialize VendorRouter (Bedrock + optional DeepSeek)
    try:
        from .services.bedrock import get_bedrock_service
        from .services.vendor_router import init_vendor_router
        bedrock_svc = get_bedrock_service()
        deepseek_svc = None

        # Load vendor keys from ~/.springo/config.json
        _vendor_keys = {}
        try:
            import json as _json_mod
            _cfg_file = os.path.expanduser("~/.springo/config.json")
            if os.path.exists(_cfg_file):
                with open(_cfg_file, 'r') as _f:
                    _cfg = _json_mod.load(_f)
                _vendor_keys = _cfg.get("vendor_keys", {})
        except Exception as e:
            logger.debug(f"Vendor keys config not available: {e}")

        # DeepSeek
        try:
            _ds_keys = _vendor_keys.get("deepseek", {})
            _ds_api_key = _ds_keys.get("api_key", "") or settings.deepseek_api_key
            if _ds_api_key:
                from .services.deepseek import init_deepseek_service
                _ds_base = _ds_keys.get("base_url", "") or settings.deepseek_base_url
                deepseek_svc = init_deepseek_service(_ds_api_key, _ds_base)
                logger.info(f"DeepSeek service initialized (base_url={_ds_base})")
        except Exception as e:
            logger.debug(f"DeepSeek init failed: {e}")

        # MiniMax
        minimax_svc = None
        try:
            _mm_keys = _vendor_keys.get("minimax", {})
            _mm_api_key = _mm_keys.get("api_key", "")
            if _mm_api_key:
                from .services.minimax import init_minimax_service
                _mm_base = _mm_keys.get("base_url", "") or "https://api.minimax.chat/v1"
                minimax_svc = init_minimax_service(_mm_api_key, _mm_base)
        except Exception as e:
            logger.debug(f"MiniMax init failed: {e}")

        init_vendor_router(bedrock_svc, deepseek_svc, minimax_svc)
        _vendors = ['bedrock']
        if deepseek_svc: _vendors.append('deepseek')
        logger.info(f"VendorRouter initialized with vendors: {_vendors}")
    except Exception as e:
        logger.warning(f"Failed to initialize VendorRouter: {e}")

    # Initialize Team Manager with periodic cleanup
    try:
        from .services.agent_team_manager import init_team_manager
        await init_team_manager()
    except Exception as e:
        logger.warning(f"Failed to initialize Team Manager: {e}")

    # Initialize LSP Manager (lazy — servers start on first tool call)
    try:
        from .services.lsp_manager import get_lsp_manager
        get_lsp_manager()
        # Capture main event loop for LSP tool handlers (they run in ThreadPoolExecutor)
        import asyncio
        from mcp_tools.handlers.lsp_tools import set_main_loop
        set_main_loop(asyncio.get_running_loop())
        logger.info("LSP Manager initialized (servers start lazily on first use)")
    except Exception as e:
        logger.warning(f"Failed to initialize LSP Manager: {e}")

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
    try:
        from .services.agent_team_manager import shutdown_team_manager
        await shutdown_team_manager()
    except Exception as e:
        logger.warning(f"Error closing Team Manager: {e}")
    try:
        from .services.lsp_manager import shutdown_lsp_manager
        await shutdown_lsp_manager()
    except Exception as e:
        logger.warning(f"Error closing LSP Manager: {e}")


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


# MCP lazy init middleware - fallback if lifespan init fails
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
from .routers import models, mcp, terminal, teams

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
app.include_router(terminal.router, prefix="/v1", tags=["terminal"])
app.include_router(teams.router, prefix="/v1", tags=["teams"])


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
