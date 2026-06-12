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

    # Initialize Tool Manager (built-in tools)
    global _mcp_initialized
    try:
        from .services.tool_manager import get_tool_manager, close_tool_manager
        tool_manager = await get_tool_manager()
        _mcp_initialized = True
        logger.info(f"Tool Manager initialized with {len(tool_manager.get_tool_definitions())} tools")
    except Exception as e:
        logger.warning(f"Failed to initialize Tool Manager: {e}")

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

    # Initialize Memory Backend (agentcore / local / custom)
    try:
        from .services.memory_backend import init_memory_backend, get_memory_backend_type
        init_memory_backend()
        logger.info(f"Memory backend: {get_memory_backend_type()}")
    except Exception as e:
        logger.debug(f"Memory backend not started: {e}")

    # Initialize Local Memory Files (memory/*.md)
    try:
        from .services.memory_files import init_memory_file_manager
        mem_mgr = init_memory_file_manager()
        file_count = len(mem_mgr.list_files())
        logger.info(f"Memory files initialized: {file_count} files in {mem_mgr.workspace_dir}")
    except Exception as e:
        logger.debug(f"Memory files not started: {e}")

    # Initialize Plugin System (hooks, skills, MCP, agent templates)
    try:
        from .services.plugin_system import get_plugin_manager, get_agent_template_manager
        plugin_mgr = get_plugin_manager()
        plugin_count = plugin_mgr.load_plugins()
        tmpl_count = get_agent_template_manager().load_templates()
        logger.info(f"Plugin system: {plugin_count} plugin(s), {tmpl_count} agent template(s)")
    except Exception as e:
        logger.warning(f"Failed to initialize plugin system: {e}")

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

    # Initialize Feishu Bot (if configured)
    try:
        from .services.feishu_bot import init_feishu_bot
        await init_feishu_bot()
    except Exception as e:
        logger.debug(f"Feishu bot not started: {e}")

    # Initialize ACP Client (lazy — agents start on first use)
    try:
        from .services.acp_client import initialize_acp_client
        initialize_acp_client()
        logger.info("ACP Client config loaded (lazy mode)")
    except Exception as e:
        logger.debug(f"ACP Client not started: {e}")

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

    # Canvas tool also needs main-loop access (same thread-executor + cross-loop
    # asyncio.Event issue as LSP)
    try:
        import asyncio
        from mcp_tools.handlers.canvas_tools import set_main_loop as set_canvas_main_loop
        set_canvas_main_loop(asyncio.get_running_loop())
        logger.info("Canvas bridge main-loop captured")
    except Exception as e:
        logger.warning(f"Failed to register canvas main loop: {e}")

    # Start the daily skill-distill background loop. It wakes every 6h and
    # only runs a full pass once 24h have elapsed since the previous one, so
    # the import cost is negligible and bedrock is only hit once per day.
    try:
        from .services.skill_distiller import start_background_loop as start_distiller
        start_distiller()
        logger.info("Skill distiller daily loop started")
    except Exception as e:
        logger.warning(f"Failed to start skill distiller loop: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Springo FastAPI...")
    try:
        from .services.skill_distiller import stop_background_loop as stop_distiller
        stop_distiller()
    except Exception as e:
        logger.debug(f"Skill distiller stop noop: {e}")
    try:
        from .services.tool_manager import close_tool_manager
        await close_tool_manager()
    except Exception as e:
        logger.warning(f"Error closing Tool Manager: {e}")
    try:
        from .services.mcp_client import shutdown_external_mcp
        shutdown_external_mcp()
    except Exception as e:
        logger.warning(f"Error closing external MCP: {e}")
    try:
        from .services.memory_backend import shutdown_memory_backend
        shutdown_memory_backend()
    except Exception as e:
        logger.warning(f"Error closing memory backend: {e}")
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
        from .services.feishu_bot import shutdown_feishu_bot
        shutdown_feishu_bot()
    except Exception as e:
        logger.warning(f"Error closing Feishu bot: {e}")
    try:
        from .services.lsp_manager import shutdown_lsp_manager
        await shutdown_lsp_manager()
    except Exception as e:
        logger.warning(f"Error closing LSP Manager: {e}")
    try:
        from .services.acp_client import shutdown_acp_client
        await shutdown_acp_client()
    except Exception as e:
        logger.warning(f"Error closing ACP Client: {e}")


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
                from .services.tool_manager import get_tool_manager
                await get_tool_manager()
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
from .routers import messages, tools, sessions, context, images, health
from .routers import config, memory, skills, skill_proposals, tool_results, canvas as canvas_router
from .routers import models, mcp, terminal, teams, schedules, plugins, acp, transcribe, plans, artifacts, folders, kb, meetings

app.include_router(messages.router, prefix="/v1", tags=["messages"])
app.include_router(tools.router, prefix="/v1", tags=["tools"])
app.include_router(sessions.router, prefix="/v1", tags=["sessions"])
app.include_router(context.router, prefix="/v1", tags=["context"])
app.include_router(images.router, prefix="/v1", tags=["images"])
app.include_router(health.router, tags=["health"])
# 配置与管理路由
app.include_router(config.router, prefix="/v1", tags=["config"])
app.include_router(memory.router, prefix="/v1", tags=["memory"])
app.include_router(skills.router, prefix="/v1", tags=["skills"])
app.include_router(skill_proposals.router, prefix="/v1", tags=["skill-proposals"])
app.include_router(canvas_router.router, prefix="/v1", tags=["canvas"])
app.include_router(tool_results.router, prefix="/v1", tags=["tool-results"])
# 新增路由
app.include_router(models.router, prefix="/v1", tags=["models"])
app.include_router(mcp.router, prefix="/v1", tags=["mcp"])
app.include_router(terminal.router, prefix="/v1", tags=["terminal"])
app.include_router(teams.router, prefix="/v1", tags=["teams"])
app.include_router(schedules.router, prefix="/v1", tags=["schedules"])
app.include_router(plugins.router, prefix="/v1", tags=["plugins"])
app.include_router(acp.router, prefix="/v1", tags=["acp"])
app.include_router(transcribe.router, prefix="/v1", tags=["transcribe"])
app.include_router(plans.router, prefix="/v1", tags=["plans"])
app.include_router(artifacts.router, prefix="/v1", tags=["artifacts"])
app.include_router(folders.router, prefix="/v1", tags=["folders"])
app.include_router(kb.router, prefix="/v1", tags=["kb"])
app.include_router(meetings.router, prefix="/v1", tags=["meetings"])


from fastapi.responses import JSONResponse, FileResponse
from fastapi import Request
from fastapi.staticfiles import StaticFiles

# Serve frontend static files (so Electron can load via http:// instead of file://)
_renderer_dir = os.path.join(os.path.dirname(__file__), '..', 'springo-app', 'renderer')
if os.path.isdir(_renderer_dir):
    # Serve assets sub-directory
    _assets_dir = os.path.join(_renderer_dir, 'assets')
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend-assets")

    @app.get("/app", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(_renderer_dir, 'index.html'))


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], include_in_schema=False)
async def catch_all(request: Request, path: str):
    """Catch-all for unknown routes"""
    return JSONResponse(
        status_code=404,
        content={"error": f"Unknown endpoint: /{path}"}
    )


if __name__ == "__main__":
    import uvicorn
    # reload_dirs: only watch backend source — see run.py for rationale
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=[os.path.join(_root, d) for d in ("api", "mcp_tools")] if settings.debug else None,
    )
