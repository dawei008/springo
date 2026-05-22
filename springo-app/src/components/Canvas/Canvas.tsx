import { useCallback, useEffect, useRef } from 'react';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import type { Artifact, InternalComponentId } from '@/stores/unifiedArtifactStore';
import { ARTIFACT_TEMPLATES } from '@/data/artifactTemplates';
import type { ArtifactTemplate } from '@/data/artifactTemplates';
import ArtifactIframe from './ArtifactIframe';
import { ArtifactIcon } from './ArtifactIcon';
import { useUIStore } from '@/stores/uiStore';
import SchedulesPanel from '@/components/RightPanel/SchedulesPanel';
import MeetingPanel from '@/components/RightPanel/MeetingPanel';
import RecordingCanvasPanel from '@/components/RightPanel/RecordingCanvasPanel';

function TasksCanvasPanel() {
  const todos = useUIStore((s) => s.todos);
  const completedCount = todos.filter((t) => t.status === 'completed').length;

  if (todos.length === 0) {
    return (
      <div className="canvas-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--font-size-sm)', marginTop: '8px' }}>
          No background tasks
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px', overflow: 'auto', height: '100%' }}>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {completedCount}/{todos.length} completed
      </div>
      {todos.map((todo) => {
        let statusIcon = '○';
        let color = 'var(--text-tertiary)';
        if (todo.status === 'in_progress') { statusIcon = '◔'; color = 'var(--accent)'; }
        else if (todo.status === 'completed') { statusIcon = '✓'; color = 'var(--success, #22c55e)'; }
        return (
          <div key={todo.id} style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '6px 0', fontSize: '13px' }}>
            <span style={{ color, flexShrink: 0 }}>{statusIcon}</span>
            <span style={{ color: todo.status === 'completed' ? 'var(--text-tertiary)' : 'var(--text-primary)', textDecoration: todo.status === 'completed' ? 'line-through' : 'none' }}>
              {todo.subject}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function InternalRenderer({ component }: { component: InternalComponentId }) {
  switch (component) {
    case 'tasks': return <TasksCanvasPanel />;
    case 'schedules': return <SchedulesPanel />;
    case 'meeting': return <MeetingPanel />;
    case 'recording': return <RecordingCanvasPanel />;
    default: return null;
  }
}

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

function useCanvasResize(panelRef: React.RefObject<HTMLDivElement | null>) {
  const handleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handle = handleRef.current;
    const panel = panelRef.current;
    if (!handle || !panel) return;

    let dragging = false;
    let startX = 0;
    let startW = 0;

    const onDown = (e: MouseEvent) => {
      dragging = true;
      startX = e.clientX;
      startW = panel.offsetWidth;
      handle.classList.add('dragging');
      panel.classList.add('resizing');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      const diff = startX - e.clientX;
      const maxW = Math.floor(window.innerWidth * 0.75);
      const w = Math.min(maxW, Math.max(320, startW + diff));
      panel.style.width = w + 'px';
      panel.style.flex = '0 0 auto';
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('dragging');
      panel.classList.remove('resizing');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try {
        localStorage.setItem('springo-canvas-width', String(panel.offsetWidth));
      } catch { /* ignore quota */ }
    };

    handle.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      handle.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [panelRef]);

  // Restore persisted width on mount.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    try {
      const saved = localStorage.getItem('springo-canvas-width');
      if (saved) {
        const w = parseInt(saved, 10);
        if (w > 0) {
          panel.style.width = w + 'px';
          panel.style.flex = '0 0 auto';
        }
      }
    } catch { /* ignore */ }
  }, [panelRef]);

  return handleRef;
}

export default function Canvas() {
  const activeArtifactId = useUnifiedArtifactStore((s) => s.activeArtifactId);
  const activeArtifact = useUnifiedArtifactStore((s) =>
    s.activeArtifactId ? s.artifacts[s.activeArtifactId] ?? null : null,
  );
  const canvasRef = useRef<HTMLDivElement>(null);
  const resizeHandleRef = useCanvasResize(canvasRef);

  if (!activeArtifact || !activeArtifactId) {
    return (
      <div className="canvas-panel" ref={canvasRef}>
        <div className="canvas-resize" ref={resizeHandleRef} />
        <EmptyCanvas />
      </div>
    );
  }

  const isInternal = !!activeArtifact.internalComponent;

  return (
    <div className="canvas-panel" ref={canvasRef}>
      <div className="canvas-resize" ref={resizeHandleRef} />
      <div className="canvas-header">
        <ArtifactIcon name={activeArtifact.icon} size={16} className="canvas-header-icon" />
        <span className="canvas-header-title">{activeArtifact.name}</span>
        <SyncIndicator />
        {isInternal ? <InternalActionBar /> : <ActionBar artifact={activeArtifact} containerRef={canvasRef} />}
      </div>
      <div className="canvas-body">
        {isInternal ? (
          <InternalRenderer component={activeArtifact.internalComponent!} />
        ) : (
          <ArtifactIframe
            artifactId={activeArtifactId}
            files={activeArtifact.files}
            state={activeArtifact.state}
          />
        )}
      </div>
      {!isInternal && <VersionTimeline artifact={activeArtifact} />}
    </div>
  );
}

function SyncIndicator() {
  const pending = useUnifiedArtifactStore((s) => s.syncPendingCount);
  const offline = useUnifiedArtifactStore((s) => s.syncOffline);
  if (pending === 0) return null;
  const label = offline
    ? `Backend offline — ${pending} pending`
    : `Saving (${pending})…`;
  return (
    <span
      className="canvas-sync-indicator"
      title={label}
      style={{
        marginLeft: 'auto',
        marginRight: '8px',
        fontSize: '11px',
        color: offline ? 'var(--warning-text, #b45309)' : 'var(--text-tertiary)',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: offline ? 'var(--warning, #f59e0b)' : 'var(--accent, #6b5bff)',
          animation: offline ? 'none' : 'pulse 1.2s ease-in-out infinite',
        }}
      />
      {label}
    </span>
  );
}

function InternalActionBar() {
  const closeArtifact = useUnifiedArtifactStore((s) => s.closeArtifact);
  return (
    <div className="canvas-action-bar">
      <button className="canvas-action-btn" onClick={closeArtifact} title="Close">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}
