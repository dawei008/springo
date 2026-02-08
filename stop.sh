#!/bin/bash

# Springo 停止脚本

echo "停止 Springo 服务..."

pkill -f "uvicorn api.main:app" 2>/dev/null && echo "  -> FastAPI 后端已停止" || echo "  -> FastAPI 后端未运行"
pkill -f "electron" 2>/dev/null && echo "  -> Electron 前端已停止" || echo "  -> Electron 前端未运行"

echo "完成"
