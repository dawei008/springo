#!/bin/bash
# Springo full restart: kill all → build frontend → start backend → start frontend
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/springo-app"

echo "=== Springo Restart ==="

# 1. Kill everything
echo "[1/4] Killing processes..."
lsof -ti:8081 | xargs kill -9 2>/dev/null || true
# Kill ALL Electron-related processes (main + Helper + GPU + node shim)
ps ax -o pid,command | grep -i "[Ee]lectron" | grep -i "springo" | awk '{print $1}' | xargs kill -9 2>/dev/null || true
pkill -9 -f "npm exec electron" 2>/dev/null || true
sleep 2

# 2. Build frontend
echo "[2/4] Building frontend..."
cd "$APP" && npx vite build 2>&1 | tail -3

# 3. Start backend
echo "[3/4] Starting backend..."
cd "$ROOT" && source venv/bin/activate
nohup uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload > /tmp/springo-server.log 2>&1 &
sleep 3

if curl -sf http://localhost:8081/health > /dev/null; then
    echo "  Backend: OK (port 8081)"
else
    echo "  Backend: FAILED" && exit 1
fi

# 4. Start frontend
echo "[4/4] Starting Electron..."
cd "$APP" && nohup npx electron . > /tmp/springo-electron.log 2>&1 &
sleep 2

echo ""
echo "=== Done ==="
echo "  Backend:  http://localhost:8081"
echo "  Logs:     /tmp/springo-server.log"
echo "            /tmp/springo-electron.log"
