const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

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

// 服务器配置 - FastAPI on port 8081
const SERVER_URL = 'http://127.0.0.1:8081';
// In development: use python3 with script
// In packaged app: use bundled executable
const SERVER_EXECUTABLE = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'springo-backend')
    : null;
const SERVER_SCRIPT = path.join(__dirname, '..', 'full_proxy_server.py');

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
    mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

    // 准备好后显示窗口
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // 外部链接在浏览器中打开
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
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

function startServer() {
    return new Promise((resolve, reject) => {
        // 检查服务器是否已经运行
        fetch(`${SERVER_URL}/health`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'healthy') {
                    console.log('Server already running');
                    resolve(true);
                }
            })
            .catch(() => {
                // 服务器未运行，启动它
                console.log('Starting server...');

                // Use bundled executable in packaged app, python3 in development
                if (SERVER_EXECUTABLE) {
                    console.log('Using bundled executable:', SERVER_EXECUTABLE);
                    serverProcess = spawn(SERVER_EXECUTABLE, ['--port', '8081'], {
                        cwd: path.dirname(SERVER_EXECUTABLE),
                        stdio: ['ignore', 'pipe', 'pipe']
                    });
                } else {
                    console.log('Using python3 with script:', SERVER_SCRIPT);
                    serverProcess = spawn('python3', [SERVER_SCRIPT, '--port', '8080'], {
                        cwd: path.dirname(SERVER_SCRIPT),
                        stdio: ['ignore', 'pipe', 'pipe']
                    });
                }

                serverProcess.stdout.on('data', (data) => {
                    console.log(`Server: ${data}`);
                });

                serverProcess.stderr.on('data', (data) => {
                    console.error(`Server Error: ${data}`);
                });

                // 等待服务器启动
                let attempts = 0;
                const checkServer = setInterval(() => {
                    fetch(`${SERVER_URL}/health`)
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
    if (serverProcess) {
        serverProcess.kill();
        serverProcess = null;
    }
}

// IPC 处理
ipcMain.handle('get-server-url', () => SERVER_URL);

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

app.whenReady().then(async () => {
    // Suppress EPIPE error dialogs
    const originalShowErrorBox = dialog.showErrorBox;
    dialog.showErrorBox = (title, content) => {
        if (content?.includes?.('EPIPE')) {
            return; // Suppress EPIPE error dialogs
        }
        originalShowErrorBox.call(dialog, title, content);
    };

    try {
        await startServer();
    } catch (err) {
        console.error('Failed to start server:', err);
    }

    createMenu();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        stopServer();
        app.quit();
    }
});

app.on('before-quit', () => {
    stopServer();
});
