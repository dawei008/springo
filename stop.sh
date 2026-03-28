#!/bin/bash

# Springo 停止脚本

echo "停止 Springo 服务..."

# Graceful stop for Electron (releases single-instance lock)
pkill -f "npm exec electron" 2>/dev/null || true
pkill -f "npx electron" 2>/dev/null || true
pkill -f "Electron.*springo" 2>/dev/null || true
sleep 2

# Force-kill Electron survivors
ps ax -o pid,command | grep -i "[Ee]lectron" | grep -i "springo" | awk '{print $1}' | xargs kill -9 2>/dev/null || true
pkill -9 -f "npm exec electron" 2>/dev/null || true
pkill -9 -f "npx electron" 2>/dev/null || true
echo "  -> Electron 已停止"

# Stop backend
pkill -f "uvicorn api.main" 2>/dev/null && echo "  -> FastAPI 后端已停止" || echo "  -> FastAPI 后端未运行"
sleep 1

# Release port 8081
if lsof -ti:8081 >/dev/null 2>&1; then
    lsof -ti:8081 | xargs kill -9 2>/dev/null
    echo "  -> 端口 8081 已强制释放"
fi

# Clean up stale Electron lock files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$SCRIPT_DIR/springo-app"
find "$APP" -name "SingletonLock" -delete 2>/dev/null || true
find "$APP" -name "SingletonSocket" -delete 2>/dev/null || true
ELECTRON_USERDATA="$HOME/Library/Application Support/springo"
if [ -d "$ELECTRON_USERDATA" ]; then
    find "$ELECTRON_USERDATA" -name "SingletonLock" -delete 2>/dev/null || true
    find "$ELECTRON_USERDATA" -name "SingletonSocket" -delete 2>/dev/null || true
fi

echo "完成"
