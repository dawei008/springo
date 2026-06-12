#!/usr/bin/env python3
"""
Springo FastAPI Runner
便捷启动脚本
"""
import argparse
import os
import sys


def main():
    # When running as a PyInstaller bundle, add the temp extraction dir to sys.path
    # so that "api" and "mcp_tools" packages (added via --add-data) can be imported.
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)

    parser = argparse.ArgumentParser(description="Run Springo FastAPI server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8081, help="Port to bind to")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Set environment variables
    if args.debug:
        os.environ["SPRINGO_DEBUG"] = "true"
    
    # Run with uvicorn
    # In development (non-packaged), always enable reload for hot code updates
    import uvicorn

    enable_reload = args.reload or not getattr(sys, 'frozen', False)

    # Only watch backend source dirs. Without this, WatchFiles watches the whole
    # repo — AI tools writing .py files into the working tree (e.g. creating a
    # venv or test project) trigger a reload that kills in-flight SSE streams.
    repo_root = os.path.dirname(os.path.abspath(__file__))
    reload_dirs = [
        os.path.join(repo_root, d)
        for d in ("api", "mcp_tools")
        if os.path.isdir(os.path.join(repo_root, d))
    ]

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not enable_reload else 1,
        reload=enable_reload,
        reload_dirs=reload_dirs if enable_reload else None,
        log_level="debug" if args.debug else "info"
    )


if __name__ == "__main__":
    main()
