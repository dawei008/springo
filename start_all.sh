#!/bin/bash

# Springo 完整启动脚本 (后端 + 前端)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================"
echo "  Springo 完整启动脚本"
echo "================================"

# 停止可能运行的旧进程
pkill -f "uvicorn api.main:app" 2>/dev/null
pkill -f "electron" 2>/dev/null

# 1. 启动后端
echo ""
echo "[1/2] 启动 FastAPI 后端..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "  -> 创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q fastapi uvicorn pydantic-settings aioboto3 httpx sse-starlette psutil 2>/dev/null

# 后台启动 FastAPI
nohup uvicorn api.main:app --host 0.0.0.0 --port 8081 > /tmp/springo-fastapi.log 2>&1 &
BACKEND_PID=$!

sleep 2

# 检查后端是否启动成功
if curl -s http://localhost:8081/health > /dev/null; then
    echo "  -> FastAPI 后端启动成功 (PID: $BACKEND_PID)"
    echo "  -> API: http://localhost:8081"
    echo "  -> Swagger: http://localhost:8081/docs"
else
    echo "  -> FastAPI 后端启动失败，查看日志: /tmp/springo-fastapi.log"
    exit 1
fi

# 2. 启动前端
echo ""
echo "[2/2] 启动 Electron 前端..."

cd springo-app

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "  -> 安装前端依赖..."
    npm install
fi

echo "  -> 启动 Electron 应用..."
npm start &
FRONTEND_PID=$!

echo ""
echo "================================"
echo "  Springo 启动完成!"
echo "================================"
echo ""
echo "后端 PID: $BACKEND_PID"
echo "前端 PID: $FRONTEND_PID"
echo ""
echo "停止所有服务:"
echo "  pkill -f 'uvicorn api.main:app'"
echo "  pkill -f 'electron'"
echo ""
echo "或运行: ./stop.sh"
echo "================================"

# 等待前端进程
wait $FRONTEND_PID
