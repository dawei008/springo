import { useState, useEffect, useRef } from 'react'
import { useArtifactStore, type ArtifactItem } from '@/stores/artifactStore'
import { useUnifiedArtifactStore, type ArtifactIconName } from '@/stores/unifiedArtifactStore'
import { useUIStore } from '@/stores/uiStore'
import { buildFilePreviewHtml } from '@/utils/filePreviewHtml'

interface ArtifactCardProps {
  artifact: ArtifactItem
  onClickOverride?: () => void
  defaultCollapsed?: boolean
}

function TypeIcon({ type }: { type: ArtifactItem['type'] }) {
  const props = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }
  switch (type) {
    case 'html':
      return <svg {...props}><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg>
    case 'markdown':
      return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
    case 'image':
      return <svg {...props}><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
    case 'svg':
    case 'excalidraw':
    case 'drawio':
      return <svg {...props}><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" /></svg>
  }
}

const TYPE_LABELS: Record<ArtifactItem['type'], string> = {
  html: 'HTML',
  markdown: 'Document',
  image: 'Image',
  svg: 'SVG',
  excalidraw: 'Diagram',
  drawio: 'Draw.io',
}

const EXT_MAP: Record<ArtifactItem['type'], string> = {
  html: '.html',
  markdown: '.md',
  image: '.png',
  svg: '.svg',
  excalidraw: '.excalidraw',
  drawio: '.drawio',
}

// Promote an inline chat artifact into a persistent Canvas artifact so the
// user can keep it around across sessions and iterate on it. Every output is
// a single index.html file so ArtifactIframe's raw-HTML path can render it.
function pinInlineToCanvas(artifact: ArtifactItem): string {
  const iconByType: Partial<Record<ArtifactItem['type'], ArtifactIconName>> = {
    html: 'web', markdown: 'document', image: 'image',
    svg: 'image', excalidraw: 'chart', drawio: 'chart',
  };

  let htmlContent = artifact.content;
  switch (artifact.type) {
    case 'html':
      break;
    case 'markdown':
      htmlContent = buildFilePreviewHtml(artifact.title + '.md', artifact.content, 'markdown');
      break;
    case 'svg':
      htmlContent = buildFilePreviewHtml(artifact.title + '.svg', artifact.content, 'svg');
      break;
    case 'image':
      if (artifact.content.startsWith('data:')) {
        htmlContent = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${artifact.title}</title>
<style>body{margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;}
img{max-width:100%;max-height:100vh;object-fit:contain;}</style></head>
<body><img src="${artifact.content}" alt="${artifact.title.replace(/"/g, '&quot;')}"/></body></html>`;
      }
      break;
    case 'excalidraw': {
      const scene = {
        type: 'excalidraw',
        version: 2,
        source: 'springo',
        elements: Array.isArray(artifact.elements) ? artifact.elements : [],
        appState: { viewBackgroundColor: '#ffffff' },
      };
      htmlContent = buildFilePreviewHtml('scene.json', JSON.stringify(scene, null, 2), 'markdown');
      break;
    }
    case 'drawio':
      htmlContent = buildFilePreviewHtml('diagram.xml', artifact.content, 'markdown');
      break;
  }

  return useUnifiedArtifactStore.getState().createArtifact({
    name: artifact.title || 'Pinned artifact',
    type: 'app',
    icon: iconByType[artifact.type] ?? 'document',
    files: [{ path: 'index.html', type: 'html', content: htmlContent }],
  });
}

function saveArtifact(artifact: ArtifactItem) {
  let blob: Blob
  const filename = (artifact.title.replace(/[/\\?%*:|"<>]/g, '_').slice(0, 60) || 'artifact') + EXT_MAP[artifact.type]

  if (artifact.type === 'image' && artifact.content.startsWith('data:')) {
    // data URL → binary blob
    const [header, b64] = artifact.content.split(',')
    const mime = header.match(/:(.*?);/)?.[1] || 'image/png'
    const bytes = atob(b64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    blob = new Blob([arr], { type: mime })
  } else if (artifact.type === 'excalidraw') {
    const scene = {
      type: 'excalidraw',
      version: 2,
      source: 'springo',
      elements: Array.isArray(artifact.elements) ? artifact.elements : [],
      appState: { viewBackgroundColor: '#ffffff' },
    }
    blob = new Blob([JSON.stringify(scene, null, 2)], { type: 'application/json' })
  } else {
    blob = new Blob([artifact.content], { type: 'text/plain;charset=utf-8' })
  }

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// SVG icons as components
const FolderIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

const GlobeIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
)

const DownloadIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
)

const PinIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="17" x2="12" y2="22" />
    <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
  </svg>
)

/** Save artifact content to a temp file and open with system app */
async function openWithSystemApp(artifact: ArtifactItem) {
  // If artifact has a filePath, open that directly
  if (artifact.filePath) {
    window.electronAPI?.openPath(artifact.filePath)
    return
  }
  // Otherwise save to temp and open
  saveArtifact(artifact)
}

function ContextMenu({ x, y, artifact, onClose }: { x: number; y: number; artifact: ArtifactItem; onClose: () => void }) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  // Position: keep menu within viewport
  const style: React.CSSProperties = {
    position: 'fixed', left: x, top: y, zIndex: 9999,
  }

  return (
    <div className="artifact-context-menu" ref={menuRef} style={style}>
      {artifact.filePath && (
        <div className="artifact-context-menu-item" onClick={() => { onClose(); window.electronAPI?.openPath(artifact.filePath!) }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
          Open with System App
        </div>
      )}
      {artifact.filePath && (
        <div className="artifact-context-menu-item" onClick={() => { onClose(); window.electronAPI?.openFolder(artifact.filePath!) }}>
          <FolderIcon />
          Reveal in Folder
        </div>
      )}
      {artifact.url && (
        <div className="artifact-context-menu-item" onClick={() => { onClose(); window.electronAPI?.openExternal(artifact.url!) }}>
          <GlobeIcon />
          Open URL in Browser
        </div>
      )}
      <div className="artifact-context-menu-item" onClick={() => {
        onClose();
        pinInlineToCanvas(artifact);
        useUIStore.getState().showToast(`Pinned "${artifact.title}" to Canvas`, 'success');
      }}>
        <PinIcon />
        Pin to Canvas
      </div>
      <div className="artifact-context-menu-item" onClick={() => { onClose(); saveArtifact(artifact) }}>
        <DownloadIcon />
        Save / Export
      </div>
      <div className="artifact-context-menu-item" onClick={() => {
        onClose()
        const text = artifact.content || ''
        navigator.clipboard.writeText(text).catch(() => {})
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        Copy Content
      </div>
    </div>
  )
}

export default function ArtifactCard({ artifact, onClickOverride, defaultCollapsed = false }: ArtifactCardProps) {
  const openArtifact = useArtifactStore((s) => s.openArtifact)
  const activeId = useArtifactStore((s) => s.activeArtifact?.id)
  const panelOpen = useArtifactStore((s) => s.panelOpen)
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null)
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  const isActive = panelOpen && activeId === artifact.id

  // Collapsed view: compact single-line header
  if (collapsed) {
    return (
      <div
        className="artifact-card collapsed"
        onClick={() => setCollapsed(false)}
      >
        <div className="artifact-card-icon">
          <TypeIcon type={artifact.type} />
        </div>
        <div className="artifact-card-info">
          <span className="artifact-card-title">{artifact.title}</span>
          <span className="artifact-card-type">{TYPE_LABELS[artifact.type]}</span>
        </div>
        <svg className="artifact-card-chevron" width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
      </div>
    )
  }

  return (
    <>
      <div
        className={`artifact-card${isActive ? ' active' : ''}`}
        onClick={onClickOverride ?? (() => openArtifact(artifact))}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setCtxMenu({ x: e.clientX, y: e.clientY }) }}
      >
        <div className="artifact-card-icon">
          <TypeIcon type={artifact.type} />
        </div>
        <div className="artifact-card-info">
          <span className="artifact-card-title">{artifact.title}</span>
          <span className="artifact-card-type">{TYPE_LABELS[artifact.type]}</span>
        </div>
        <div className="artifact-card-actions">
          {artifact.filePath && (
            <button
              className="artifact-card-action"
              title="Reveal in Folder"
              onClick={(e) => { e.stopPropagation(); window.electronAPI?.openFolder(artifact.filePath!) }}
            >
              <FolderIcon />
            </button>
          )}
          {artifact.url && (
            <button
              className="artifact-card-action"
              title="Open in Browser"
              onClick={(e) => { e.stopPropagation(); window.open(artifact.url!, '_blank') }}
            >
              <GlobeIcon />
            </button>
          )}
          <button
            className="artifact-card-action"
            title="Pin to Canvas"
            onClick={(e) => {
              e.stopPropagation();
              pinInlineToCanvas(artifact);
              useUIStore.getState().showToast(`Pinned "${artifact.title}" to Canvas`, 'success');
            }}
          >
            <PinIcon />
          </button>
          <button
            className="artifact-card-action"
            title="Save"
            onClick={(e) => { e.stopPropagation(); saveArtifact(artifact) }}
          >
            <DownloadIcon />
          </button>
          <button
            className="artifact-card-action"
            title="Collapse"
            onClick={(e) => { e.stopPropagation(); setCollapsed(true) }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>
      {ctxMenu && <ContextMenu x={ctxMenu.x} y={ctxMenu.y} artifact={artifact} onClose={() => setCtxMenu(null)} />}
    </>
  )
}
