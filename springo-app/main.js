const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

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

// Enable remote debugging for Playwright testing (always enabled for E2E testing)
const DEBUG_PORT = process.env.ELECTRON_DEBUG_PORT || '9222';
app.commandLine.appendSwitch('remote-debugging-port', DEBUG_PORT);

let mainWindow;
let serverProcess = null;

// 服务器配置
const SERVER_URL = 'http://127.0.0.1:8080';
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
                serverProcess = spawn('python3', [SERVER_SCRIPT, '--port', '8080'], {
                    cwd: path.dirname(SERVER_SCRIPT),
                    stdio: ['ignore', 'pipe', 'pipe']
                });

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
                            if (attempts > 30) {
                                clearInterval(checkServer);
                                reject(new Error('Server failed to start'));
                            }
                        });
                }, 500);
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
    return shell.openPath(filePath);
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
