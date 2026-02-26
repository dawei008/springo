#!/usr/bin/env python3
"""
Springo FastAPI Runner
便捷启动脚本
"""
import argparse
import os
import sys


def main():
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

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not enable_reload else 1,
        reload=enable_reload,
        log_level="debug" if args.debug else "info"
    )


if __name__ == "__main__":
    main()
