#!/bin/bash
# Springo full restart: kill all → build frontend → start backend → start frontend
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/springo-app"

echo "=== Springo Restart ==="

# 1. Kill everything gracefully first, then force
echo "[1/4] Stopping processes..."

# Graceful SIGTERM first for Electron (releases single-instance lock)
pkill -f "npm exec electron" 2>/dev/null || true
pkill -f "npx electron" 2>/dev/null || true
pkill -f "Electron.*springo" 2>/dev/null || true

# Give Electron time to release the lock file
sleep 2

# Force-kill any survivors
ps ax -o pid,command | grep -i "[Ee]lectron" | grep -i "springo" | awk '{print $1}' | xargs kill -9 2>/dev/null || true
pkill -9 -f "npm exec electron" 2>/dev/null || true
pkill -9 -f "npx electron" 2>/dev/null || true

# Kill backend
pkill -f "uvicorn api.main" 2>/dev/null || true
sleep 1

# Force-release port 8081
if lsof -ti:8081 >/dev/null 2>&1; then
    echo "  -> Force-releasing port 8081..."
    lsof -ti:8081 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Clean up stale Electron lock files
LOCK_DIR="$APP"
find "$LOCK_DIR" -name "SingletonLock" -delete 2>/dev/null || true
find "$LOCK_DIR" -name "SingletonSocket" -delete 2>/dev/null || true
# Also check common Electron userData lock locations
ELECTRON_USERDATA="$HOME/Library/Application Support/springo"
if [ -d "$ELECTRON_USERDATA" ]; then
    find "$ELECTRON_USERDATA" -name "SingletonLock" -delete 2>/dev/null || true
    find "$ELECTRON_USERDATA" -name "SingletonSocket" -delete 2>/dev/null || true
fi

echo "  -> All processes stopped"

# 2. Build frontend
echo "[2/4] Building frontend..."
cd "$APP" && npx vite build 2>&1 | tail -3

# 3. Start backend
echo "[3/4] Starting backend..."
cd "$ROOT" && source venv/bin/activate
nohup uvicorn api.main:app --host 127.0.0.1 --port 8081 --reload --reload-dir api > /tmp/springo-server.log 2>&1 &
BACKEND_PID=$!

# Wait for backend health
for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:8081/health > /dev/null 2>&1; then
        echo "  Backend: OK (PID $BACKEND_PID, port 8081)"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "  Backend: FAILED (check /tmp/springo-server.log)"
        exit 1
    fi
    sleep 1
done

# 4. Start frontend
echo "[4/4] Starting Electron..."
cd "$APP" && nohup npx electron . --remote-debugging-port=9222 > /tmp/springo-electron.log 2>&1 &
FRONTEND_PID=$!
sleep 3

# Verify Electron is actually running
if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo "  Electron: OK (PID $FRONTEND_PID)"
else
    echo "  Electron: FAILED (check /tmp/springo-electron.log)"
    echo "  Last log lines:"
    tail -5 /tmp/springo-electron.log 2>/dev/null
    exit 1
fi

echo ""
echo "=== Done ==="
echo "  Backend:  http://127.0.0.1:8081"
echo "  Logs:     /tmp/springo-server.log"
echo "            /tmp/springo-electron.log"
