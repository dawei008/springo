/// <reference types="vite/client" />

interface ElectronAPI {
  getServerUrl: () => Promise<string>
  onNewChat: (callback: () => void) => void
  onClearChat: (callback: () => void) => void
  onOpenSettings: (callback: () => void) => void
  onShowLogs: (callback: () => void) => void
  selectFolder: () => Promise<string | null>
  openFolder: (path: string) => Promise<{ success: boolean }>
  openPath: (path: string) => Promise<{ success: boolean }>
  readFileBase64: (path: string) => Promise<{ success: boolean; data?: string; mimeType?: string }>
  openExternal: (url: string) => Promise<{ success: boolean }>
  openArtifactWindow: (html: string, title: string) => Promise<{ success: boolean }>
  cache: {
    get: (key: string) => Promise<unknown>
    set: (key: string, value: unknown) => Promise<void>
    remove: (key: string) => Promise<void>
    getAll: () => Promise<Record<string, unknown>>
  }
  schedules: {
    get: () => Promise<unknown>
    set: (tasks: unknown) => Promise<void>
  }
}

interface Window {
  electronAPI?: ElectronAPI
}
