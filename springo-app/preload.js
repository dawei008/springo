const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getServerUrl: () => ipcRenderer.invoke('get-server-url'),
    onNewChat: (callback) => ipcRenderer.on('new-chat', callback),
    onClearChat: (callback) => ipcRenderer.on('clear-chat', callback),
    onOpenSettings: (callback) => ipcRenderer.on('open-settings', callback),
    onShowLogs: (callback) => ipcRenderer.on('show-logs', callback),
    onToggleRecording: (callback) => ipcRenderer.on('toggle-recording', callback),
    // Folder selection
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    openFolder: (path) => ipcRenderer.invoke('open-folder', path),
    // Open file/folder with system default application
    openPath: (path) => ipcRenderer.invoke('open-path', path),
    // Read local file as base64 (for inline image rendering)
    readFileBase64: (path) => ipcRenderer.invoke('read-file-base64', path),
    // Open URL in default browser (Chrome new tab)
    openExternal: (url) => ipcRenderer.invoke('open-external', url),
    // Open HTML artifact in a new Electron window
    openArtifactWindow: (html, title) => ipcRenderer.invoke('open-artifact-window', html, title),
    // Disk cache API (persists across macOS restarts)
    cache: {
        get: (key) => ipcRenderer.invoke('cache-get', key),
        set: (key, value) => ipcRenderer.invoke('cache-set', key, value),
        remove: (key) => ipcRenderer.invoke('cache-remove', key),
        getAll: () => ipcRenderer.invoke('cache-get-all')
    },
    // Scheduled tasks API (separate file, survives cache clear)
    schedules: {
        get: () => ipcRenderer.invoke('schedules-get'),
        set: (tasks) => ipcRenderer.invoke('schedules-set', tasks)
    },
    // Screen recording API
    recording: {
        getSource: (target) => ipcRenderer.invoke('recording-get-source', target),
        save: (buffer, filename) => ipcRenderer.invoke('recording-save', buffer, filename),
        selectDir: () => ipcRenderer.invoke('recording-select-dir'),
    },
    // Microphone permission
    checkMicAccess: () => ipcRenderer.invoke('check-mic-access'),
    // Desktop audio source for system audio capture
    getDesktopAudioSource: () => ipcRenderer.invoke('get-desktop-audio-source'),
});
