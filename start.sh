#!/bin/bash

# Springo FastAPI 启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================"
echo "  Springo FastAPI 启动脚本"
echo "================================"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
else
    echo "[1/4] 虚拟环境已存在"
fi

# 激活虚拟环境
echo "[2/4] 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "[3/4] 检查依赖..."
pip install -q fastapi uvicorn pydantic-settings aioboto3 httpx sse-starlette psutil 2>/dev/null

# 停止可能运行的旧进程
pkill -f "uvicorn api.main:app" 2>/dev/null

# 启动 FastAPI
echo "[4/4] 启动 FastAPI 服务器..."
echo ""
echo "  API:     http://localhost:8081"
echo "  Swagger: http://localhost:8081/docs"
echo "  Health:  http://localhost:8081/health"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "================================"

uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload
