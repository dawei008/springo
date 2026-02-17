import { useEffect } from 'react'
import { useSessionStore } from '@/stores/sessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useChatStore } from '@/stores/chatStore'
import Sidebar from '@/components/Layout/Sidebar'
import MainContent from '@/components/Layout/MainContent'
import SettingsModal from '@/components/Settings/SettingsModal'
import { useUIStore } from '@/stores/uiStore'
import Toast from '@/components/common/Toast'

export default function App() {
  const loadSessions = useSessionStore((s) => s.loadSessions)
  const loadModels = useSettingsStore((s) => s.loadModels)
  const loadSettings = useSettingsStore((s) => s.loadSettings)
  const loadWorkingDir = useSettingsStore((s) => s.loadWorkingDir)
  const settingsOpen = useUIStore((s) => s.settingsOpen)
  const toast = useUIStore((s) => s.toast)

  useEffect(() => {
    loadSettings()
    loadModels()
    loadWorkingDir()
    loadSessions()
  }, [loadSettings, loadModels, loadWorkingDir, loadSessions])

  // Register Electron menu callbacks
  useEffect(() => {
    if (window.electronAPI) {
      window.electronAPI.onNewChat(() => {
        useSessionStore.getState().createSession()
      })
      window.electronAPI.onClearChat(() => {
        const id = useSessionStore.getState().currentSessionId
        if (id) {
          const { runtimes } = useChatStore.getState()
          if (runtimes[id]) {
            runtimes[id].messages = []
          }
        }
      })
      window.electronAPI.onOpenSettings(() => {
        useUIStore.getState().toggleSettings()
      })
    }
  }, [])

  return (
    <div className="app-container">
      <Sidebar />
      <MainContent />
      {settingsOpen && <SettingsModal />}
      {toast && <Toast />}
    </div>
  )
}
