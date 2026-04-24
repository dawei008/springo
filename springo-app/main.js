const { app, BrowserWindow, Menu, shell, ipcMain, dialog, session, systemPreferences } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

// Debug log helper
const DEBUG_LOG = path.join(os.homedir(), '.springo', 'lifecycle.log');
function debugLog(msg) {
    try {
        fs.appendFileSync(DEBUG_LOG, `[${new Date().toISOString()}] ${msg}\n`);
    } catch(e) { /* ignore */ }
}

// Cache file path: ~/.springo/cache.json
const CACHE_DIR = path.join(os.homedir(), '.springo');
const CACHE_FILE = path.join(CACHE_DIR, 'cache.json');
// Scheduled tasks file: ~/.springo/scheduled_tasks.json (separate from cache, survives cache clear)
const SCHEDULES_FILE = path.join(CACHE_DIR, 'scheduled_tasks.json');

// Cache helper functions
function ensureCacheDir() {
    if (!fs.existsSync(CACHE_DIR)) {
        fs.mkdirSync(CACHE_DIR, { recursive: true });
    }
}

function readCache() {
    try {
        ensureCacheDir();
        if (fs.existsSync(CACHE_FILE)) {
            const data = fs.readFileSync(CACHE_FILE, 'utf8');
            return JSON.parse(data);
        }
    } catch (err) {
        console.error('Failed to read cache:', err);
    }
    return {};
}

function writeCache(cache) {
    try {
        ensureCacheDir();
        fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf8');
        return true;
    } catch (err) {
        console.error('Failed to write cache:', err);
        return false;
    }
}

// Scheduled tasks helper functions (independent from cache)
function readScheduledTasks() {
    try {
        ensureCacheDir();
        if (fs.existsSync(SCHEDULES_FILE)) {
            const data = fs.readFileSync(SCHEDULES_FILE, 'utf8');
            return JSON.parse(data);
        }
    } catch (err) {
        console.error('Failed to read scheduled tasks:', err);
    }
    return {};
}

function writeScheduledTasks(tasks) {
    try {
        ensureCacheDir();
        fs.writeFileSync(SCHEDULES_FILE, JSON.stringify(tasks, null, 2), 'utf8');
        return true;
    } catch (err) {
        console.error('Failed to write scheduled tasks:', err);
        return false;
    }
}

// EPIPE error tracking
let epipeErrorCount = 0;
const EPIPE_LOG_INTERVAL = 100; // Log every N EPIPE errors

// Global error handlers to prevent EPIPE crashes
process.on('uncaughtException', (err) => {
    if (err.code === 'EPIPE' || err.message?.includes('EPIPE')) {
        epipeErrorCount++;
        // Log periodically instead of silently ignoring
        if (epipeErrorCount % EPIPE_LOG_INTERVAL === 1) {
            try {
                console.debug(`EPIPE error (count: ${epipeErrorCount})`);
            } catch (e) { /* ignore */ }
        }
        return;
    }
    // Only log non-EPIPE errors, and catch any logging errors
    try {
        console.error('Uncaught Exception:', err);
    } catch (e) {
        // Ignore logging errors
    }
});

process.on('unhandledRejection', (reason, promise) => {
    try {
        console.warn('Unhandled Rejection:', reason);
    } catch (e) {
        // Ignore logging errors
    }
});

// Ignore EPIPE on stdout/stderr
process.stdout?.on?.('error', (err) => {
    if (err.code !== 'EPIPE') throw err;
});
process.stderr?.on?.('error', (err) => {
    if (err.code !== 'EPIPE') throw err;
});

// Disable Electron's default error dialog for EPIPE
// This will be set after app is ready

// Enable remote debugging for development/testing only (disabled in packaged app)
const isDev = !app.isPackaged;
const DEBUG_PORT = process.env.ELECTRON_DEBUG_PORT || (isDev ? '9222' : null);
if (DEBUG_PORT) {
    app.commandLine.appendSwitch('remote-debugging-port', DEBUG_PORT);
}

let mainWindow;
let serverProcess = null;
let serverRestartCount = 0;

// Prevent multiple instances of the Electron app (both dev and packaged)
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    console.log('Another instance is already running — quitting.');
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.show();
            mainWindow.focus();
        } else {
            createWindow();
        }
    });
}

// 服务器配置
const SERVER_PORT = process.env.SPRINGO_PORT || '8081';
const SERVER_URL = `http://127.0.0.1:${SERVER_PORT}`;
// In development: use python3 with script
// In packaged app: use bundled executable
const SERVER_EXECUTABLE = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'springo-backend')
    : null;
const SERVER_SCRIPT = path.join(__dirname, '..', 'run.py');

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        titleBarStyle: 'hiddenInset',
        trafficLightPosition: { x: 15, y: 15 },
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        },
        backgroundColor: '#FAF9F5',
        show: false
    });

    // 加载本地 HTML
    if (process.env.SPRINGO_DEV_URL) {
        mainWindow.loadURL(process.env.SPRINGO_DEV_URL);
        mainWindow.webContents.openDevTools({ mode: 'detach' });
    } else {
        mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
    }

    // 准备好后显示窗口
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Log renderer crashes
    mainWindow.webContents.on('render-process-gone', (event, details) => {
        debugLog(`Renderer crashed: reason=${details.reason} exitCode=${details.exitCode}`);
    });
    mainWindow.webContents.on('crashed', () => {
        debugLog('Renderer process crashed');
    });
    mainWindow.webContents.on('console-message', (event, level, message) => {
        if (level >= 1 || message.includes('[voice]')) {
            const labels = ['debug','info','warn','error'];
            debugLog(`[renderer-${labels[level] || level}] ${message}`);
        }
    });

    // 外部链接在浏览器中打开
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
        debugLog('window closed/destroyed');
        mainWindow = null;
    });
}

function createMenu() {
    const template = [
        {
            label: 'Springo',
            submenu: [
                { role: 'about', label: 'About Springo' },
                { type: 'separator' },
                {
                    label: 'Preferences...',
                    accelerator: 'CmdOrCtrl+,',
                    click: () => {
                        mainWindow.webContents.send('open-settings');
                    }
                },
                { type: 'separator' },
                { role: 'services' },
                { type: 'separator' },
                { role: 'hide', label: 'Hide Springo' },
                { role: 'hideOthers' },
                { role: 'unhide' },
                { type: 'separator' },
                { role: 'quit', label: 'Quit Springo' }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' }
            ]
        },
        {
            label: 'Chat',
            submenu: [
                {
                    label: 'New Chat',
                    accelerator: 'CmdOrCtrl+N',
                    click: () => {
                        mainWindow.webContents.send('new-chat');
                    }
                },
                { type: 'separator' },
                {
                    label: 'Clear Chat',
                    accelerator: 'CmdOrCtrl+K',
                    click: () => {
                        mainWindow.webContents.send('clear-chat');
                    }
                },
                { type: 'separator' },
                {
                    label: 'Toggle Recording',
                    accelerator: 'CmdOrCtrl+Shift+R',
                    click: () => {
                        mainWindow.webContents.send('toggle-recording');
                    }
                }
            ]
        },
        {
            label: 'Window',
            submenu: [
                { role: 'minimize' },
                { role: 'zoom' },
                { type: 'separator' },
                { role: 'front' }
            ]
        },
        {
            label: 'Help',
            submenu: [
                {
                    label: 'AWS Config',
                    click: () => {
                        shell.openExternal(`${SERVER_URL}/config`);
                    }
                },
                { type: 'separator' },
                {
                    label: 'View Server Logs',
                    click: () => {
                        mainWindow.webContents.send('show-logs');
                    }
                }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
}

function getPortPids(port) {
    try {
        const result = require('child_process').execSync(
            `lsof -ti:${port}`, { encoding: 'utf8', timeout: 5000 }
        ).trim();
        if (result) {
            return result.split('\n').filter(Boolean).map(Number);
        }
    } catch(e) { /* no process on port */ }
    return [];
}

function killPortProcess(port) {
    const pids = getPortPids(port);
    if (pids.length === 0) return false;

    debugLog(`Found stale processes on port ${port}: ${pids.join(', ')}`);

    // First try SIGTERM for graceful shutdown
    for (const pid of pids) {
        try { process.kill(pid, 'SIGTERM'); } catch(e) { /* ignore */ }
    }

    // Wait briefly, then SIGKILL any survivors
    try {
        require('child_process').execSync('sleep 1');
    } catch(e) { /* ignore */ }

    const remaining = getPortPids(port);
    for (const pid of remaining) {
        try {
            process.kill(pid, 'SIGKILL');
            debugLog(`Force killed PID ${pid}`);
        } catch(e) { /* ignore */ }
    }

    // Wait for port to actually be freed
    try {
        require('child_process').execSync('sleep 1');
    } catch(e) { /* ignore */ }

    const stillAlive = getPortPids(port);
    if (stillAlive.length > 0) {
        debugLog(`WARNING: port ${port} still occupied by PIDs: ${stillAlive.join(', ')}`);
    } else {
        debugLog(`Port ${port} successfully freed`);
    }
    return stillAlive.length === 0;
}

function startServer() {
    return new Promise((resolve, reject) => {
        // 检查服务器是否已经运行
        fetch(`${SERVER_URL}/health`, { signal: AbortSignal.timeout(3000) })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'healthy') {
                    console.log('Server already running');
                    resolve(true);
                }
            })
            .catch(() => {
                // 服务器未运行，先清理可能残留的旧进程
                killPortProcess(8081);

                console.log('Starting server...');

                // Use bundled executable in packaged app, python3 in development
                // detached=true creates a new process group so we can kill the group later
                if (SERVER_EXECUTABLE) {
                    debugLog('Using bundled executable: ' + SERVER_EXECUTABLE);
                    serverProcess = spawn(SERVER_EXECUTABLE, ['--port', SERVER_PORT], {
                        cwd: path.dirname(SERVER_EXECUTABLE),
                        stdio: ['ignore', 'pipe', 'pipe'],
                        detached: true
                    });
                } else {
                    // Use venv python to avoid system python architecture mismatches
                    const venvPython = path.join(__dirname, '..', 'venv', 'bin', 'python3');
                    const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
                    debugLog(`Using ${pythonCmd} with script: ${SERVER_SCRIPT}`);
                    serverProcess = spawn(pythonCmd, [SERVER_SCRIPT, '--port', SERVER_PORT], {
                        cwd: path.dirname(SERVER_SCRIPT),
                        stdio: ['ignore', 'pipe', 'pipe'],
                        detached: true
                    });
                }
                debugLog(`Server spawned with PID=${serverProcess.pid}`);

                serverProcess.stdout.on('data', (data) => {
                    const msg = data.toString().trim();
                    console.log(`Server: ${msg}`);
                    debugLog(`[stdout] ${msg}`);
                });

                serverProcess.stderr.on('data', (data) => {
                    const msg = data.toString().trim();
                    console.error(`Server Error: ${msg}`);
                    debugLog(`[stderr] ${msg}`);
                });

                // Track unexpected crash — do NOT auto-restart here
                // (the health-check polling below will detect the failure)
                serverProcess.on('exit', (code, signal) => {
                    debugLog(`Server process exited: code=${code} signal=${signal}`);
                    serverProcess = null;
                    if (code !== null && code !== 0 && !app.isQuitting) {
                        debugLog(`Server crashed with code ${code}`);
                    }
                });

                // 等待服务器启动
                let attempts = 0;
                const checkServer = setInterval(() => {
                    fetch(`${SERVER_URL}/health`, { signal: AbortSignal.timeout(3000) })
                        .then(res => res.json())
                        .then(data => {
                            if (data.status === 'healthy') {
                                clearInterval(checkServer);
                                console.log('Server started successfully');
                                resolve(true);
                            }
                        })
                        .catch(() => {
                            attempts++;
                            // Wait up to 60 seconds (MCP servers can take 20+ seconds to start)
                            if (attempts > 60) {
                                clearInterval(checkServer);
                                reject(new Error('Server failed to start'));
                            }
                        });
                }, 1000);
            });
    });
}

function stopServer() {
    app.isQuitting = true;
    debugLog('stopServer called');

    // 1. Kill the tracked server process and its entire process group
    if (serverProcess) {
        const pid = serverProcess.pid;
        debugLog(`Killing server process PID=${pid}`);

        // Kill the process group (negative PID) to catch child processes
        try { process.kill(-pid, 'SIGTERM'); } catch(e) { /* ignore */ }
        // Also kill the process directly
        try { serverProcess.kill('SIGTERM'); } catch(e) { /* ignore */ }

        // Give it a moment then force kill
        try {
            require('child_process').execSync('sleep 1');
        } catch(e) { /* ignore */ }

        try { process.kill(-pid, 'SIGKILL'); } catch(e) { /* ignore */ }
        try { serverProcess.kill('SIGKILL'); } catch(e) { /* ignore */ }

        serverProcess = null;
    }

    // 2. Also kill anything still holding port 8081 (orphaned children)
    killPortProcess(8081);
    debugLog('stopServer complete');
}

// Graceful stop: kill backend but don't set isQuitting (app stays alive on macOS)
function stopServerGraceful() {
    debugLog('stopServerGraceful called');
    if (serverProcess) {
        const pid = serverProcess.pid;
        debugLog(`Gracefully stopping server PID=${pid}`);
        try { process.kill(-pid, 'SIGTERM'); } catch(e) { /* ignore */ }
        try { serverProcess.kill('SIGTERM'); } catch(e) { /* ignore */ }
        serverProcess = null;
    }
    // Clean up port in background
    setTimeout(() => killPortProcess(8081), 2000);
}

// IPC 处理
ipcMain.handle('get-server-url', () => SERVER_URL);

// Microphone permission check/request
ipcMain.handle('check-mic-access', async () => {
    if (process.platform === 'darwin') {
        const status = systemPreferences.getMediaAccessStatus('microphone');
        if (status !== 'granted') {
            return await systemPreferences.askForMediaAccess('microphone');
        }
        return true;
    }
    return true;
});

// Get desktop audio source for system audio capture
ipcMain.handle('get-desktop-audio-source', async () => {
    const { desktopCapturer } = require('electron');
    // Check screen recording permission on macOS
    if (process.platform === 'darwin') {
        const screenStatus = systemPreferences.getMediaAccessStatus('screen');
        debugLog(`[voice] Screen recording permission: ${screenStatus}`);
        if (screenStatus !== 'granted') {
            debugLog('[voice] Screen recording NOT granted — system audio will not be captured');
        }
    }
    const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } });
    debugLog(`[voice] desktopCapturer sources: ${sources.map(s => s.id + '/' + s.name).join(', ')}`);
    return sources[0] ? { id: sources[0].id, name: sources[0].name } : null;
});

// Folder selection dialog
ipcMain.handle('select-folder', async () => {
    // Focus the window to ensure dialog appears in front
    if (mainWindow) {
        mainWindow.focus();
    }
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory', 'multiSelections'],
        title: 'Select Working Folder'
    });
    if (result.canceled) {
        return null;
    }
    return result.filePaths;
});

// Open folder in Finder
ipcMain.handle('open-folder', async (event, folderPath) => {
    shell.showItemInFolder(folderPath);
});

// Open file/folder with system default application
ipcMain.handle('open-path', async (event, filePath) => {
    // Expand ~ to home directory
    let expandedPath = filePath;
    if (filePath.startsWith('~/')) {
        expandedPath = path.join(require('os').homedir(), filePath.slice(2));
    }
    return shell.openPath(expandedPath);
});

// Read a local file as base64 (for inline image rendering)
ipcMain.handle('read-file-base64', async (event, filePath) => {
    try {
        let expandedPath = filePath;
        if (filePath.startsWith('~/')) {
            expandedPath = path.join(require('os').homedir(), filePath.slice(2));
        }
        const data = fs.readFileSync(expandedPath);
        const ext = path.extname(expandedPath).toLowerCase();
        const mimeTypes = {
            '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.gif': 'image/gif', '.svg': 'image/svg+xml', '.webp': 'image/webp',
            '.bmp': 'image/bmp', '.ico': 'image/x-icon',
        };
        const mimeType = mimeTypes[ext] || 'application/octet-stream';
        return { success: true, data: data.toString('base64'), mimeType };
    } catch (err) {
        return { success: false, error: err.message };
    }
});

// Open URL in default browser (new tab in Chrome)
ipcMain.handle('open-external', async (event, url) => {
    try {
        await shell.openExternal(url);
        return { success: true };
    } catch (err) {
        console.error('Failed to open external URL:', err);
        return { success: false, error: err.message };
    }
});

// Open HTML artifact in a new window
ipcMain.handle('open-artifact-window', async (event, html, title) => {
    try {
        const win = new BrowserWindow({
            width: 1024,
            height: 768,
            title: title || 'Artifact',
            webPreferences: {
                nodeIntegration: false,
                contextIsolation: true
            }
        });
        // Write HTML to a temp file and load it
        const tmpDir = path.join(os.tmpdir(), 'springo-artifacts');
        if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
        const tmpFile = path.join(tmpDir, `artifact-${Date.now()}.html`);
        fs.writeFileSync(tmpFile, html, 'utf8');
        win.loadFile(tmpFile);
        // Clean up temp file when window closes
        win.on('closed', () => {
            try { fs.unlinkSync(tmpFile); } catch (e) { /* ignore */ }
        });
        return { success: true };
    } catch (err) {
        console.error('Failed to open artifact window:', err);
        return { success: false, error: err.message };
    }
});

// Disk cache IPC handlers (persists across macOS restarts)
ipcMain.handle('cache-get', async (event, key) => {
    const cache = readCache();
    return cache[key];
});

ipcMain.handle('cache-set', async (event, key, value) => {
    const cache = readCache();
    cache[key] = value;
    return writeCache(cache);
});

ipcMain.handle('cache-remove', async (event, key) => {
    const cache = readCache();
    delete cache[key];
    return writeCache(cache);
});

ipcMain.handle('cache-get-all', async () => {
    return readCache();
});

// Scheduled tasks IPC handlers (separate file, survives cache clear)
ipcMain.handle('schedules-get', async () => {
    return readScheduledTasks();
});

ipcMain.handle('schedules-set', async (event, tasks) => {
    return writeScheduledTasks(tasks);
});

// --- Screen Recording ---
ipcMain.handle('recording-get-source', async (event, target) => {
    const { desktopCapturer, screen } = require('electron');
    if (target === 'screen' || target === 'screen-ext') {
        const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } });
        if (sources.length <= 1) {
            // Only one screen — use it regardless
            return sources[0] ? { id: sources[0].id, name: sources[0].name } : null;
        }
        // Find which display the Springo window is on
        const winBounds = mainWindow.getBounds();
        const displays = screen.getAllDisplays();
        const currentDisplay = screen.getDisplayMatching(winBounds);
        if (target === 'screen') {
            // Current screen — match by display id
            const currentIdx = displays.findIndex(d => d.id === currentDisplay.id);
            const source = sources[currentIdx >= 0 ? currentIdx : 0];
            return source ? { id: source.id, name: source.name } : null;
        } else {
            // Extended screen — pick the OTHER display
            const otherIdx = displays.findIndex(d => d.id !== currentDisplay.id);
            const source = sources[otherIdx >= 0 ? otherIdx : 0];
            return source ? { id: source.id, name: source.name } : null;
        }
    } else {
        const sources = await desktopCapturer.getSources({ types: ['window'], thumbnailSize: { width: 0, height: 0 } });
        const springoSource = sources.find(s => s.name.includes('Springo'));
        return springoSource ? { id: springoSource.id, name: springoSource.name } : null;
    }
});

ipcMain.handle('recording-save', async (event, buffer, filename) => {
    const cache = readCache();
    const recordingSettings = cache.recording || {};
    const dir = recordingSettings.outputDir || path.join(os.homedir(), '.springo', 'recordings');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const filePath = path.join(dir, filename);
    fs.writeFileSync(filePath, Buffer.from(buffer));
    return filePath;
});

ipcMain.handle('recording-select-dir', async () => {
    if (mainWindow) mainWindow.focus();
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory', 'createDirectory'],
        title: 'Select Recording Output Directory'
    });
    return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(async () => {
    // Suppress EPIPE error dialogs
    const originalShowErrorBox = dialog.showErrorBox;
    dialog.showErrorBox = (title, content) => {
        if (content?.includes?.('EPIPE')) {
            return; // Suppress EPIPE error dialogs
        }
        originalShowErrorBox.call(dialog, title, content);
    };

    debugLog('app ready');

    // Auto-approve microphone and display-capture permissions
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
        callback(true);
    });

    // Handle getDisplayMedia() calls from renderer — auto-select screen with loopback audio
    // This is the modern Electron approach; avoids the desktopCapturer audio track dying bug
    const { desktopCapturer: dc } = require('electron');
    session.defaultSession.setDisplayMediaRequestHandler(async (request, callback) => {
        const sources = await dc.getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } });
        debugLog(`[voice] setDisplayMediaRequestHandler: ${sources.length} sources, picking ${sources[0]?.name}`);
        if (sources.length > 0) {
            callback({ video: sources[0], audio: 'loopback' });
        } else {
            callback(null);
        }
    });

    // Pre-request macOS microphone permission so the system dialog
    // appears at startup rather than crashing the renderer later
    if (process.platform === 'darwin') {
        systemPreferences.askForMediaAccess('microphone').then((granted) => {
            debugLog(`Microphone access: ${granted ? 'granted' : 'denied'}`);
        });
    }

    createMenu();
    createWindow();
    debugLog('window created');

    // Start server in background — don't block window creation
    startServer()
        .then(() => debugLog('server started OK'))
        .catch(err => {
            debugLog('server start failed: ' + err.message);
            console.error('Failed to start server:', err);
        });

    app.on('activate', () => {
        debugLog(`activate fired. mainWindow=${!!mainWindow} destroyed=${mainWindow?.isDestroyed()} allWindows=${BrowserWindow.getAllWindows().length}`);
        if (mainWindow && !mainWindow.isDestroyed()) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.show();
            mainWindow.focus();
        } else {
            debugLog('activate: creating new window');
            createWindow();
        }
        // Ensure backend is running (may have been stopped on window-all-closed)
        if (!serverProcess) {
            debugLog('activate: restarting server');
            startServer()
                .then(() => debugLog('activate: server restarted OK'))
                .catch(err => debugLog('activate: server restart failed: ' + err.message));
        }
    });
});

app.on('window-all-closed', () => {
    debugLog(`window-all-closed platform=${process.platform}`);
    // On macOS, stop the backend when all windows close (it will restart on activate)
    // This prevents orphaned backend processes
    if (process.platform === 'darwin') {
        debugLog('macOS: stopping server on window close (will restart on activate)');
        stopServerGraceful();
    } else {
        stopServer();
        app.quit();
    }
});

app.on('before-quit', () => {
    stopServer();
});
