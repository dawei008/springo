const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getServerUrl: () => ipcRenderer.invoke('get-server-url'),
    onNewChat: (callback) => ipcRenderer.on('new-chat', callback),
    onClearChat: (callback) => ipcRenderer.on('clear-chat', callback),
    onOpenSettings: (callback) => ipcRenderer.on('open-settings', callback),
    onShowLogs: (callback) => ipcRenderer.on('show-logs', callback),
    // Folder selection
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    openFolder: (path) => ipcRenderer.invoke('open-folder', path),
    // Open file/folder with system default application
    openPath: (path) => ipcRenderer.invoke('open-path', path)
});
