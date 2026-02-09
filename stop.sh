#!/bin/bash

# Springo 停止脚本

echo "停止 Springo 服务..."

pkill -f "uvicorn api.main:app" 2>/dev/null && echo "  -> FastAPI 后端已停止" || echo "  -> FastAPI 后端未运行"
pkill -fi "electron" 2>/dev/null && echo "  -> Electron 前端已停止" || echo "  -> Electron 前端未运行"
pkill -f "node.*electron" 2>/dev/null

# 等进程退出
sleep 1

# 确保端口释放
if lsof -ti:8081 >/dev/null 2>&1; then
    lsof -ti:8081 | xargs kill -9 2>/dev/null
    echo "  -> 端口 8081 已强制释放"
fi

echo "完成"
