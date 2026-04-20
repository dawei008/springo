import { useRef, useEffect, useState, useCallback } from 'react'
import { useArtifactStore, type ArtifactItem } from '@/stores/artifactStore'
import Markdown from '@/components/common/Markdown'
import ExcalidrawPreview from '@/components/Visual/ExcalidrawPreview'
import { useUIStore } from '@/stores/uiStore'
import TeamPanel from '@/components/RightPanel/TeamPanel'
import SchedulesPanel from '@/components/RightPanel/SchedulesPanel'
import MeetingPanel from '@/components/RightPanel/MeetingPanel'
import PlanCanvasPanel from '@/components/RightPanel/PlanCanvasPanel'
import RecordingCanvasPanel from '@/components/RightPanel/RecordingCanvasPanel'

// ==================== HTML Renderer ====================

function HtmlRenderer({ artifact }: { artifact: ArtifactItem }) {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return
    iframe.srcdoc = artifact.content
  }, [artifact.content])

  return (
    <iframe
      ref={iframeRef}
      className="artifact-panel-iframe"
      sandbox="allow-scripts allow-same-origin"
    />
  )
}

// ==================== Image Renderer ====================

function ImageRenderer({ artifact }: { artifact: ArtifactItem }) {
  const setImagePreview = useUIStore((s) => s.setImagePreview)

  return (
    <div className="artifact-panel-image">
      <img
        src={artifact.content}
        alt={artifact.title}
        onClick={() => setImagePreview(artifact.content)}
        style={{ maxWidth: '100%', cursor: 'pointer' }}
      />
    </div>
  )
}

// ==================== SVG Renderer ====================

function SvgRenderer({ artifact }: { artifact: ArtifactItem }) {
  return (
    <div
      className="artifact-panel-svg"
      dangerouslySetInnerHTML={{ __html: artifact.content }}
    />
  )
}

// ==================== Markdown Renderer ====================

function MarkdownRenderer({ artifact }: { artifact: ArtifactItem }) {
  return (
    <div className="artifact-panel-markdown">
      <Markdown content={artifact.content} />
    </div>
  )
}

// ==================== Draw.io Renderer ====================

// Cache the viewer JS to avoid re-reading from disk
let viewerJsCache: string | null = null
let viewerJsPromise: Promise<string> | null = null

function fetchViewerJs(): Promise<string> {
  if (viewerJsCache) return Promise.resolve(viewerJsCache)
  if (viewerJsPromise) return viewerJsPromise
  // Read from local file via Electron IPC (fetch blocked on file:// origin)
  const base = document.baseURI.replace('file://', '').replace(/\/[^/]*$/, '/')
  const filePath = base + 'drawio-viewer.min.js'
  viewerJsPromise = window.electronAPI.readFileBase64(filePath)
    .then((r: { success: boolean; data: string }) => {
      if (!r.success) throw new Error('read failed')
      const js = atob(r.data)
      viewerJsCache = js
      return js
    })
    .catch((e: Error) => { console.error('Failed to load drawio viewer:', e); viewerJsPromise = null; return '' })
  return viewerJsPromise
}

function DrawioRenderer({ artifact }: { artifact: ArtifactItem }) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [viewerJs, setViewerJs] = useState(viewerJsCache)

  useEffect(() => {
    if (!viewerJs) fetchViewerJs().then((js) => { if (js) setViewerJs(js) })
  }, [viewerJs])

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe || !viewerJs) return

    // Build srcdoc via DOM with inlined viewer JS
    const doc = document.implementation.createHTMLDocument('drawio')
    const style = doc.createElement('style')
    style.textContent = 'html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#fff}'
    doc.head.appendChild(style)

    const div = doc.createElement('div')
    div.className = 'mxgraph'
    div.style.maxWidth = '100%'
    div.style.border = 'none'
    div.setAttribute('data-mxgraph', JSON.stringify({
      highlight: '#0000ff',
      nav: true,
      resize: true,
      toolbar: 'zoom layers',
      xml: artifact.content,
    }))
    doc.body.appendChild(div)

    const script = doc.createElement('script')
    script.textContent = viewerJs
    doc.body.appendChild(script)

    iframe.srcdoc = '<!DOCTYPE html>' + doc.documentElement.outerHTML
  }, [artifact.content, viewerJs])

  if (!viewerJs) {
    return <div className="artifact-panel-empty">Loading draw.io viewer...</div>
  }

  return (
    <iframe
      ref={iframeRef}
      className="artifact-panel-iframe"
      sandbox="allow-scripts allow-same-origin"
    />
  )
}

// ==================== Component Renderer ====================

function TasksCanvasPanel() {
  const todos = useUIStore((s) => s.todos)
  const completedCount = todos.filter((t) => t.status === 'completed').length

  if (todos.length === 0) {
    return (
      <div className="artifact-panel-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        <span>No background tasks</span>
      </div>
    )
  }

  return (
    <div style={{ padding: '16px' }}>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {completedCount}/{todos.length} completed
      </div>
      {todos.map((todo) => {
        let statusIcon = '\u25CB'
        let color = 'var(--text-tertiary)'
        if (todo.status === 'in_progress') { statusIcon = '\u25D4'; color = 'var(--accent)' }
        else if (todo.status === 'completed') { statusIcon = '\u2713'; color = 'var(--success, #22c55e)' }
        return (
          <div key={todo.id} style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '6px 0', fontSize: '13px' }}>
            <span style={{ color, flexShrink: 0 }}>{statusIcon}</span>
            <span style={{ color: todo.status === 'completed' ? 'var(--text-tertiary)' : 'var(--text-primary)', textDecoration: todo.status === 'completed' ? 'line-through' : 'none' }}>
              {todo.subject}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function ComponentRenderer({ artifact }: { artifact: ArtifactItem }) {
  switch (artifact.componentId) {
    case 'tasks':
      return <TasksCanvasPanel />
    case 'team':
      return <TeamPanel />
    case 'schedules':
      return <SchedulesPanel />
    case 'meeting':
      return <MeetingPanel />
    case 'plan':
      return <PlanCanvasPanel />
    case 'recording':
      return <RecordingCanvasPanel />
    default:
      return <div className="artifact-panel-empty">Unknown component</div>
  }
}

// ==================== Content Router ====================

function ArtifactContent({ artifact }: { artifact: ArtifactItem }) {
  switch (artifact.type) {
    case 'html':
      return <HtmlRenderer artifact={artifact} />
    case 'markdown':
      return <MarkdownRenderer artifact={artifact} />
    case 'image':
      return <ImageRenderer artifact={artifact} />
    case 'svg':
      return <SvgRenderer artifact={artifact} />
    case 'excalidraw':
      return (
        <ExcalidrawPreview
          elements={artifact.elements || []}
        />
      )
    case 'drawio':
      return <DrawioRenderer artifact={artifact} />
    case 'component':
      return <ComponentRenderer artifact={artifact} />
    default:
      return <div className="artifact-panel-empty">Unsupported artifact type</div>
  }
}

// ==================== Type Icon ====================

function TypeIcon({ type }: { type: ArtifactItem['type'] }) {
  switch (type) {
    case 'html':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      )
    case 'markdown':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      )
    case 'image':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
      )
    case 'svg':
    case 'excalidraw':
    case 'drawio':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" />
        </svg>
      )
    case 'component':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
        </svg>
      )
  }
}

// ==================== Main Panel ====================

export default function ArtifactPanel() {
  const panelOpen = useArtifactStore((s) => s.panelOpen)
  const activeArtifact = useArtifactStore((s) => s.activeArtifact)
  const artifacts = useArtifactStore((s) => s.artifacts)
  const openArtifact = useArtifactStore((s) => s.openArtifact)
  const closePanel = useArtifactStore((s) => s.closePanel)

  const panelRef = useRef<HTMLDivElement>(null)
  const resizeRef = useRef<HTMLDivElement>(null)
  const [showHistory, setShowHistory] = useState(false)

  // Resize logic
  useEffect(() => {
    const resizeHandle = resizeRef.current
    const panel = panelRef.current
    if (!resizeHandle || !panel) return

    let isResizing = false
    let startX = 0
    let startWidth = 0

    const onMouseDown = (e: MouseEvent) => {
      isResizing = true
      startX = e.clientX
      startWidth = panel.offsetWidth
      resizeHandle.classList.add('dragging')
      panel.classList.add('resizing')
      document.body.style.cursor = 'ew-resize'
      document.body.style.userSelect = 'none'
      e.preventDefault()
    }

    const onMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const diff = startX - e.clientX
      const maxW = Math.floor(window.innerWidth * 0.6)
      const newWidth = Math.min(maxW, Math.max(300, startWidth + diff))
      panel.style.width = newWidth + 'px'
    }

    const onMouseUp = () => {
      if (isResizing) {
        isResizing = false
        resizeHandle.classList.remove('dragging')
        panel.classList.remove('resizing')
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }

    resizeHandle.addEventListener('mousedown', onMouseDown)
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)

    return () => {
      resizeHandle.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [panelOpen])

  const handleOpenExternal = useCallback(() => {
    if (!activeArtifact) return
    if (activeArtifact.type === 'html') {
      if (window.electronAPI?.openArtifactWindow) {
        window.electronAPI.openArtifactWindow(activeArtifact.content, activeArtifact.title)
      } else {
        const win = window.open('', '_blank', 'width=1024,height=768')
        if (win) {
          win.document.open()
          win.document.write(activeArtifact.content)
          win.document.close()
        }
      }
    } else if (activeArtifact.type === 'image') {
      useUIStore.getState().setImagePreview(activeArtifact.content)
    } else if (activeArtifact.type === 'drawio') {
      // Open in diagrams.net editor with the XML
      const encoded = encodeURIComponent(activeArtifact.content)
      window.open(`https://app.diagrams.net/?#R${encoded}`, '_blank')
    }
  }, [activeArtifact])

  if (!panelOpen) return null

  return (
    <div className="artifact-panel" ref={panelRef}>
      <div className="artifact-panel-resize" ref={resizeRef} />

      {/* Header */}
      <div className="artifact-panel-header">
        <div className="artifact-panel-header-left">
          {activeArtifact && <TypeIcon type={activeArtifact.type} />}
          <span className="artifact-panel-title">
            {activeArtifact?.title || 'Artifact'}
          </span>
        </div>
        <div className="artifact-panel-header-actions">
          {artifacts.length > 1 && (
            <button
              className="artifact-panel-btn"
              onClick={() => setShowHistory((v) => !v)}
              title="History"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="22 12 16 12 13 15 10 9 7 12 2 12" />
              </svg>
              {artifacts.length}
            </button>
          )}
          {(activeArtifact?.type === 'html' || activeArtifact?.type === 'image' || activeArtifact?.type === 'drawio') && (
            <button
              className="artifact-panel-btn"
              onClick={handleOpenExternal}
              title="Open in new window"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </button>
          )}
          <button
            className="artifact-panel-btn"
            onClick={closePanel}
            title="Close"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* History dropdown */}
      {showHistory && (
        <div className="artifact-panel-history">
          {artifacts.map((a) => (
            <div
              key={a.id}
              className={`artifact-panel-history-item${a.id === activeArtifact?.id ? ' active' : ''}`}
              onClick={() => {
                openArtifact(a)
                setShowHistory(false)
              }}
            >
              <TypeIcon type={a.type} />
              <span>{a.title}</span>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="artifact-panel-body">
        {activeArtifact ? (
          <ArtifactContent artifact={activeArtifact} />
        ) : (
          <div className="artifact-panel-empty">No artifact selected</div>
        )}
      </div>
    </div>
  )
}
