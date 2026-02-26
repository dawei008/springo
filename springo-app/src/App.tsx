import { useEffect } from 'react'
import { useSessionStore } from '@/stores/sessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useChatStore } from '@/stores/chatStore'
import Sidebar from '@/components/Layout/Sidebar'
import FileBrowser from '@/components/Layout/FileBrowser'
import MainContent from '@/components/Layout/MainContent'
import SettingsModal from '@/components/Settings/SettingsModal'
import ImagePreview from '@/components/common/ImagePreview'
import AskUserModal from '@/components/common/AskUserModal'
import PlanApprovalModal, { PlanModeIndicator } from '@/components/common/PlanModeModal'
import { useUIStore } from '@/stores/uiStore'
import { useToolsStore } from '@/stores/toolsStore'
import { useScheduleStore } from '@/stores/scheduleStore'
import Toast from '@/components/common/Toast'

export default function App() {
  const loadSessions = useSessionStore((s) => s.loadSessions)
  const loadModels = useSettingsStore((s) => s.loadModels)
  const loadSettings = useSettingsStore((s) => s.loadSettings)
  const loadWorkingDir = useSettingsStore((s) => s.loadWorkingDir)
  const settingsOpen = useUIStore((s) => s.settingsOpen)
  const toast = useUIStore((s) => s.toast)
  const imagePreview = useUIStore((s) => s.imagePreview)
  const askUserData = useUIStore((s) => s.askUserData)
  const planApprovalData = useUIStore((s) => s.planApprovalData)

  useEffect(() => {
    loadSettings()
    loadModels()
    loadWorkingDir()
    loadSessions()
    useToolsStore.getState().fetchAll()
    useScheduleStore.getState().loadTasks()
  }, [loadSettings, loadModels, loadWorkingDir, loadSessions])

  // Set theme on body
  const themeMode = useUIStore((s) => s.themeMode)
  useEffect(() => {
    if (themeMode === 'system') {
      document.body.removeAttribute('data-theme')
    } else {
      document.body.setAttribute('data-theme', themeMode)
    }
  }, [themeMode])

  // Register Electron menu callbacks
  useEffect(() => {
    if (window.electronAPI) {
      window.electronAPI.onNewChat?.(() => {
        useSessionStore.getState().createSession()
      })
      window.electronAPI.onClearChat?.(() => {
        const id = useSessionStore.getState().currentSessionId
        if (id) {
          const { runtimes } = useChatStore.getState()
          if (runtimes[id]) {
            runtimes[id].messages = []
          }
        }
      })
      window.electronAPI.onOpenSettings?.(() => {
        useUIStore.getState().toggleSettings()
      })
    }
  }, [])

  // Global keyboard shortcuts (matching legacy behavior)
  useEffect(() => {
    let lastEscapeTime = 0

    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey

      // Cmd/Ctrl+N: New chat
      if (meta && e.key === 'n' && !e.shiftKey) {
        e.preventDefault()
        useSessionStore.getState().createSession()
        return
      }

      // Cmd/Ctrl+K: Focus search in sidebar
      if (meta && e.key === 'k') {
        e.preventDefault()
        const searchInput = document.querySelector<HTMLInputElement>('.search-box input, #sidebar-search')
        if (searchInput) {
          searchInput.focus()
          searchInput.select()
        }
        return
      }

      // Cmd/Ctrl+Shift+S: Toggle sidebar
      if (meta && e.shiftKey && e.key === 's') {
        e.preventDefault()
        useUIStore.getState().toggleSidebar()
        return
      }

      // Escape: close modals or stop streaming (double-Escape force resets)
      if (e.key === 'Escape') {
        const ui = useUIStore.getState()

        // Close settings modal first
        if (ui.settingsOpen) {
          ui.setSettingsOpen(false)
          return
        }

        // Close image preview
        if (ui.imagePreview) {
          ui.setImagePreview(null)
          return
        }

        // Double-escape within 500ms: force reset all streaming
        const now = Date.now()
        const timeSince = now - lastEscapeTime
        lastEscapeTime = now

        if (timeSince < 500) {
          const chatState = useChatStore.getState()
          let resetCount = 0
          for (const convId of Object.keys(chatState.runtimes)) {
            if (chatState.runtimes[convId]?.isStreaming) {
              chatState.stopTask(convId)
              resetCount++
            }
          }
          if (resetCount > 0) {
            ui.showToast(`Force reset ${resetCount} stuck session(s)`, 'warning', 3000)
          }
          return
        }

        // Single escape: stop current streaming task
        const sessionId = useSessionStore.getState().currentSessionId
        if (sessionId && useChatStore.getState().runtimes[sessionId]?.isStreaming) {
          e.preventDefault()
          useChatStore.getState().stopTask(sessionId)
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Legacy app renders sidebar and main-content as direct siblings (children of body)
  // In React, #root is the body's child, so we render them as fragments
  return (
    <>
      <Sidebar />
      <FileBrowser />
      <MainContent />
      <PlanModeIndicator />
      {settingsOpen && <SettingsModal />}
      {imagePreview && <ImagePreview />}
      {askUserData && <AskUserModal />}
      {planApprovalData && <PlanApprovalModal />}
      {toast && <Toast />}
    </>
  )
}
