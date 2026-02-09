#!/bin/bash

# Springo 启动脚本 (后端 + 前端)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================"
echo "  Springo 启动脚本"
echo "================================"

# 停止可能运行的旧进程
echo "  清理旧进程..."
pkill -f "uvicorn api.main:app" 2>/dev/null
pkill -fi "electron" 2>/dev/null
pkill -f "node.*electron" 2>/dev/null
# 等进程真正退出，端口释放
sleep 2

# 再确认 8081 端口没被占用
if lsof -ti:8081 >/dev/null 2>&1; then
    echo "  -> 端口 8081 仍被占用，强制释放..."
    lsof -ti:8081 | xargs kill -9 2>/dev/null
    sleep 1
fi

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
pip install -q fastapi uvicorn pydantic-settings aioboto3 httpx sse-starlette psutil asyncssh 2>/dev/null

# 后台启动 FastAPI
echo "[4/4] 启动 FastAPI 后端..."
nohup uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload > /tmp/springo-fastapi.log 2>&1 &
BACKEND_PID=$!

# 等待后端就绪
echo "  -> 等待后端启动..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8081/health > /dev/null 2>&1; then
        echo "  -> FastAPI 后端启动成功 (PID: $BACKEND_PID)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "  -> FastAPI 后端启动失败，查看日志: /tmp/springo-fastapi.log"
        exit 1
    fi
    sleep 1
done

echo ""
echo "  API:     http://localhost:8081"
echo "  Swagger: http://localhost:8081/docs"
echo ""

# 启动 Electron 前端（只启动一个实例）
echo "  启动 Electron 前端..."
cd springo-app
if [ ! -d "node_modules" ]; then
    echo "  -> 安装前端依赖..."
    npm install
fi
npm start &
FRONTEND_PID=$!

echo ""
echo "================================"
echo "  Springo 启动完成!"
echo "================================"
echo "  后端 PID: $BACKEND_PID"
echo "  前端 PID: $FRONTEND_PID"
echo ""
echo "  停止: ./stop.sh"
echo "================================"

# 等待前端进程（关闭窗口后自动退出）
wait $FRONTEND_PID

# 前端退出后清理后端
kill $BACKEND_PID 2>/dev/null
echo "Springo 已停止"
