import { useCallback, useRef } from 'react';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import type { Artifact } from '@/stores/unifiedArtifactStore';
import { ARTIFACT_TEMPLATES } from '@/data/artifactTemplates';
import type { ArtifactTemplate } from '@/data/artifactTemplates';
import ArtifactIframe from './ArtifactIframe';
import { ArtifactIcon } from './ArtifactIcon';

function VersionTimeline({ artifact }: { artifact: Artifact }) {
  const selectVersion = useUnifiedArtifactStore((s) => s.selectVersion);

  if (artifact.versions.length <= 1) return null;

  return (
    <div className="canvas-version-timeline">
      {artifact.versions.map((v, i) => (
        <button
          key={v.id}
          className={`canvas-version-dot${i === artifact.activeVersionIndex ? ' active' : ''}`}
          onClick={() => selectVersion(artifact.id, i)}
          title={`v${i + 1} — ${new Date(v.timestamp).toLocaleTimeString()}`}
        >
          <span className="canvas-version-dot-inner" />
          {i < artifact.versions.length - 1 && <span className="canvas-version-line" />}
        </button>
      ))}
    </div>
  );
}

function ActionBar({ artifact, containerRef }: { artifact: Artifact; containerRef: React.RefObject<HTMLDivElement | null> }) {
  const pinArtifact = useUnifiedArtifactStore((s) => s.pinArtifact);
  const unpinArtifact = useUnifiedArtifactStore((s) => s.unpinArtifact);
  const closeArtifact = useUnifiedArtifactStore((s) => s.closeArtifact);

  const handlePin = useCallback(() => {
    if (artifact.pinned) {
      unpinArtifact(artifact.id);
    } else {
      pinArtifact(artifact.id);
    }
  }, [artifact.id, artifact.pinned, pinArtifact, unpinArtifact]);

  const handleOpenExternal = useCallback(() => {
    if (!window.electronAPI?.openArtifactWindow || !containerRef.current) return;
    const iframe = containerRef.current.querySelector('.artifact-iframe') as HTMLIFrameElement | null;
    if (iframe?.srcdoc) {
      window.electronAPI.openArtifactWindow(iframe.srcdoc, artifact.name);
    }
  }, [artifact.name, containerRef]);

  return (
    <div className="canvas-action-bar">
      <button
        className={`canvas-action-btn${artifact.pinned ? ' pinned' : ''}`}
        onClick={handlePin}
        title={artifact.pinned ? 'Unpin from APPS (keeps the artifact, removes it from the sidebar)' : 'Pin to APPS (keep this artifact in the sidebar across sessions)'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill={artifact.pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 17v5" />
          <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
        </svg>
        {artifact.pinned ? 'Pinned' : 'Pin'}
      </button>
      <button className="canvas-action-btn" onClick={handleOpenExternal} title="Open in new window">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      </button>
      <button className="canvas-action-btn" onClick={closeArtifact} title="Close">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

function TemplateCard({ template }: { template: ArtifactTemplate }) {
  const createArtifact = useUnifiedArtifactStore((s) => s.createArtifact);

  const handleClick = useCallback(() => {
    createArtifact({
      name: template.name,
      icon: template.icon,
      type: template.type,
      files: template.files.map(f => ({ ...f })),
    });
  }, [template, createArtifact]);

  return (
    <button className="canvas-template-card" onClick={handleClick}>
      <ArtifactIcon name={template.icon} size={22} className="canvas-template-icon" />
      <span className="canvas-template-name">{template.name}</span>
      <span className="canvas-template-desc">{template.description}</span>
    </button>
  );
}

function EmptyCanvas() {
  return (
    <div className="canvas-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.25">
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
      <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--font-size-sm)', marginTop: '8px' }}>
        Artifacts appear here
      </p>
      <div className="canvas-templates">
        <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-xs)', margin: '16px 0 8px' }}>
          Start from a template
        </p>
        <div className="canvas-template-grid">
          {ARTIFACT_TEMPLATES.map(t => (
            <TemplateCard key={t.id} template={t} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Canvas() {
  const activeArtifactId = useUnifiedArtifactStore((s) => s.activeArtifactId);
  const activeArtifact = useUnifiedArtifactStore((s) =>
    s.activeArtifactId ? s.artifacts[s.activeArtifactId] ?? null : null,
  );
  const canvasRef = useRef<HTMLDivElement>(null);

  if (!activeArtifact || !activeArtifactId) {
    return (
      <div className="canvas-panel">
        <EmptyCanvas />
      </div>
    );
  }

  return (
    <div className="canvas-panel" ref={canvasRef}>
      <div className="canvas-header">
        <ArtifactIcon name={activeArtifact.icon} size={16} className="canvas-header-icon" />
        <span className="canvas-header-title">{activeArtifact.name}</span>
        <ActionBar artifact={activeArtifact} containerRef={canvasRef} />
      </div>
      <div className="canvas-body">
        <ArtifactIframe
          artifactId={activeArtifactId}
          files={activeArtifact.files}
          state={activeArtifact.state}
        />
      </div>
      <VersionTimeline artifact={activeArtifact} />
    </div>
  );
}
