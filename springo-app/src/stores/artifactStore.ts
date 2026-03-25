import { create } from 'zustand'

export type ArtifactType = 'html' | 'markdown' | 'image' | 'svg' | 'excalidraw' | 'drawio'

export interface ArtifactItem {
  id: string
  type: ArtifactType
  title: string
  /** HTML source for html type, markdown text for markdown, data URL for image, SVG string for svg */
  content: string
  /** Optional: excalidraw elements JSON for excalidraw type */
  elements?: unknown[]
  /** Optional: file path on disk (for "Reveal in Folder") */
  filePath?: string
  /** Optional: URL (for "Open in Browser") */
  url?: string
  /** Timestamp for ordering */
  timestamp: number
}

interface SessionArtifactSnapshot {
  activeArtifact: ArtifactItem | null
  artifacts: ArtifactItem[]
  panelOpen: boolean
}

interface ArtifactState {
  /** Currently displayed artifact in the panel */
  activeArtifact: ArtifactItem | null
  /** History of artifacts in this session */
  artifacts: ArtifactItem[]
  /** Whether the artifact panel is visible */
  panelOpen: boolean
  /** Per-session snapshots for save/restore */
  sessionMap: Record<string, SessionArtifactSnapshot>
  /** Current session id being tracked */
  currentSessionId: string | null

  openArtifact: (artifact: ArtifactItem) => void
  closePanel: () => void
  togglePanel: () => void
  /** Switch session: save current, restore target */
  switchSession: (sessionId: string | null) => void
}

let artifactIdCounter = 0

export function createArtifactId(): string {
  return `art-${++artifactIdCounter}-${Date.now()}`
}

export const useArtifactStore = create<ArtifactState>((set, get) => ({
  activeArtifact: null,
  artifacts: [],
  panelOpen: false,
  sessionMap: {},
  currentSessionId: null,

  openArtifact: (artifact) =>
    set((state) => {
      const exists = state.artifacts.some((a) => a.id === artifact.id)
      return {
        activeArtifact: artifact,
        artifacts: exists ? state.artifacts : [...state.artifacts, artifact],
        panelOpen: true,
      }
    }),

  closePanel: () => set({ panelOpen: false }),

  togglePanel: () => set((state) => ({ panelOpen: !state.panelOpen })),

  switchSession: (sessionId) => {
    const { currentSessionId, activeArtifact, artifacts, panelOpen, sessionMap } = get()

    // Save current session state
    const updatedMap = { ...sessionMap }
    if (currentSessionId) {
      updatedMap[currentSessionId] = { activeArtifact, artifacts, panelOpen }
    }

    // Restore target session state (or empty)
    const restored = sessionId ? updatedMap[sessionId] : null

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      activeArtifact: restored?.activeArtifact ?? null,
      artifacts: restored?.artifacts ?? [],
      panelOpen: restored?.panelOpen ?? false,
    })
  },
}))

