import { useArtifactStore, type ArtifactItem } from '@/stores/artifactStore'

interface ArtifactCardProps {
  artifact: ArtifactItem
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
      return <svg {...props}><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" /></svg>
  }
}

const TYPE_LABELS: Record<ArtifactItem['type'], string> = {
  html: 'HTML',
  markdown: 'Document',
  image: 'Image',
  svg: 'SVG',
  excalidraw: 'Diagram',
}

export default function ArtifactCard({ artifact }: ArtifactCardProps) {
  const openArtifact = useArtifactStore((s) => s.openArtifact)
  const activeId = useArtifactStore((s) => s.activeArtifact?.id)
  const panelOpen = useArtifactStore((s) => s.panelOpen)

  const isActive = panelOpen && activeId === artifact.id

  return (
    <div
      className={`artifact-card${isActive ? ' active' : ''}`}
      onClick={() => openArtifact(artifact)}
    >
      <div className="artifact-card-icon">
        <TypeIcon type={artifact.type} />
      </div>
      <div className="artifact-card-info">
        <span className="artifact-card-title">{artifact.title}</span>
        <span className="artifact-card-type">{TYPE_LABELS[artifact.type]}</span>
      </div>
      <svg className="artifact-card-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </div>
  )
}
