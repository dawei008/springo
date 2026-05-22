import { useCallback, useEffect, useRef, useState } from 'react';
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
import KBGraphPanel from '@/components/RightPanel/KBGraphPanel';
import Markdown from '@/components/common/Markdown';

/**
 * Native document renderer (Quick-inspired). When an artifact is a `document`
 * type with a single .md/.markdown file, we render it via the same Markdown
 * component used in chat — no iframe / sandbox / Babel cost. Saves ~2MB of
 * runtime payload and gives the user readable text instead of an HTML wrapper.
 */
function DocumentRenderer({ artifact }: { artifact: Artifact }) {
  const mdFile = artifact.files.find((f) =>
    /\.(md|markdown|mdx)$/i.test(f.path) || f.type === 'text',
  );
  const content = mdFile?.content ?? '';
  if (!content.trim()) {
    return (
      <div className="canvas-empty">
        <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--font-size-sm)' }}>
          Empty document — waiting for content…
        </p>
      </div>
    );
  }
  return (
    <div className="canvas-document">
      <div className="canvas-document-inner">
        <Markdown content={content} />
      </div>
    </div>
  );
}

function isDocumentArtifact(a: Artifact): boolean {
  if (a.type !== 'document') return false;
  // Must have at least one md-ish file and no JSX/HTML to fall through to native.
  const hasMd = a.files.some((f) => /\.(md|markdown|mdx)$/i.test(f.path));
  const hasCode = a.files.some((f) => f.type === 'jsx' || (f.type === 'html' && /\.(html?)$/i.test(f.path)));
  return hasMd && !hasCode;
}

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
    case 'kb-graph': return <KBGraphPanel />;
    default: return null;
  }
}

function SessionTabs() {
  const sessionIds = useUnifiedArtifactStore((s) => s.sessionArtifactIds);
  const artifacts = useUnifiedArtifactStore((s) => s.artifacts);
  const activeId = useUnifiedArtifactStore((s) => s.activeArtifactId);
  const openArtifact = useUnifiedArtifactStore((s) => s.openArtifact);
  const closeTab = useUnifiedArtifactStore((s) => s.closeArtifactTab);
  const reorder = useUnifiedArtifactStore((s) => s.reorderSessionArtifacts);

  // useRef MUST run on every render — keep it above any early return so we
  // don't violate Rules of Hooks when the tab count crosses 1↔2.
  const dragState = useRef<{ id: string | null }>({ id: null });

  const tabs = sessionIds
    .map((id) => artifacts[id])
    .filter((a): a is Artifact => !!a);

  // Hide the strip entirely if there's at most one tab — keeps a clean header
  // for the single-artifact case (which is most of the time).
  if (tabs.length <= 1) return null;

  return (
    <div className="canvas-tabs" role="tablist">
      {tabs.map((art) => {
        const isActive = art.id === activeId;
        return (
          <div
            key={art.id}
            role="tab"
            aria-selected={isActive}
            className={`canvas-tab${isActive ? ' active' : ''}`}
            draggable
            onDragStart={(e) => {
              dragState.current.id = art.id;
              e.dataTransfer.effectAllowed = 'move';
            }}
            onDragOver={(e) => {
              if (dragState.current.id && dragState.current.id !== art.id) e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              const draggedId = dragState.current.id;
              dragState.current.id = null;
              if (!draggedId || draggedId === art.id) return;
              const order = tabs.map((t) => t.id).filter((id) => id !== draggedId);
              const insertAt = order.indexOf(art.id);
              order.splice(insertAt, 0, draggedId);
              reorder(order);
            }}
            onClick={() => openArtifact(art.id)}
            title={art.name}
          >
            <ArtifactIcon name={art.icon} size={12} className="canvas-tab-icon" />
            <span className="canvas-tab-label">{art.name}</span>
            <button
              className="canvas-tab-close"
              aria-label={`Close ${art.name}`}
              onClick={(e) => {
                e.stopPropagation();
                closeTab(art.id);
              }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
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

function ActionBar({ artifact, containerRef, isFullscreen, onToggleFullscreen }: {
  artifact: Artifact;
  containerRef: React.RefObject<HTMLDivElement | null>;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}) {
  const pinArtifact = useUnifiedArtifactStore((s) => s.pinArtifact);
  const unpinArtifact = useUnifiedArtifactStore((s) => s.unpinArtifact);
  const closeArtifact = useUnifiedArtifactStore((s) => s.closeArtifact);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Click-outside to close the overflow menu.
  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [menuOpen]);

  const handlePin = useCallback(() => {
    if (artifact.pinned) unpinArtifact(artifact.id);
    else pinArtifact(artifact.id);
    setMenuOpen(false);
  }, [artifact.id, artifact.pinned, pinArtifact, unpinArtifact]);

  const handleOpenExternal = useCallback(() => {
    if (!window.electronAPI?.openArtifactWindow || !containerRef.current) return;
    const iframe = containerRef.current.querySelector('.artifact-iframe') as HTMLIFrameElement | null;
    if (iframe?.srcdoc) window.electronAPI.openArtifactWindow(iframe.srcdoc, artifact.name);
    setMenuOpen(false);
  }, [artifact.name, containerRef]);

  const handleEditWithChat = useCallback(() => {
    const el = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (!el) return;
    const placeholder = `修改 artifact「${artifact.name}」(${artifact.id}): `;
    const nativeSet = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    nativeSet?.call(el, placeholder + (el.value || ''));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.focus();
    try { el.setSelectionRange(placeholder.length, placeholder.length); } catch { /* ignore */ }
  }, [artifact.id, artifact.name]);

  const handleDownload = useCallback(() => {
    if (!containerRef.current) return;
    const iframe = containerRef.current.querySelector('.artifact-iframe') as HTMLIFrameElement | null;
    const html = iframe?.srcdoc;
    if (!html) return;
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const safe = artifact.name.replace(/[^a-zA-Z0-9\-_一-鿿]+/g, '_').slice(0, 80) || 'artifact';
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safe}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [artifact.name, containerRef]);

  return (
    <div className="canvas-action-bar">
      <button
        className="canvas-action-btn canvas-action-btn-icon"
        onClick={handleEditWithChat}
        title="Edit with chat — focus the message input prefilled to modify this artifact"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 4l5 5-9.5 9.5H6V14L15 4z" />
          <path d="M3 21h18" />
        </svg>
      </button>
      <button
        className="canvas-action-btn canvas-action-btn-icon"
        onClick={handleDownload}
        title="Download as standalone HTML"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      </button>
      <button
        className={`canvas-action-btn canvas-action-btn-icon${isFullscreen ? ' active' : ''}`}
        onClick={onToggleFullscreen}
        title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
      >
        {isFullscreen ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 3v6H3M21 9h-6V3M3 15h6v6M15 21v-6h6" />
          </svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6" />
          </svg>
        )}
      </button>
      <div ref={menuRef} className="canvas-action-menu-wrap">
        <button
          className="canvas-action-btn canvas-action-btn-icon"
          onClick={() => setMenuOpen((v) => !v)}
          title="More"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="5" cy="12" r="1.6" />
            <circle cx="12" cy="12" r="1.6" />
            <circle cx="19" cy="12" r="1.6" />
          </svg>
        </button>
        {menuOpen && (
          <div className="canvas-action-menu" role="menu">
            <button className="canvas-action-menu-item" onClick={handlePin} role="menuitem">
              <svg width="14" height="14" viewBox="0 0 24 24" fill={artifact.pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 17v5" />
                <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
              </svg>
              {artifact.pinned ? 'Unpin from APPS' : 'Pin to APPS'}
            </button>
            <button className="canvas-action-menu-item" onClick={handleOpenExternal} role="menuitem">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              Open in new window
            </button>
            <button className="canvas-action-menu-item canvas-action-menu-danger" onClick={() => { setMenuOpen(false); closeArtifact(); }} role="menuitem">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Close artifact
            </button>
          </div>
        )}
      </div>
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
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Esc exits fullscreen.
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen]);

  // Reset fullscreen when active artifact changes.
  useEffect(() => { setIsFullscreen(false); }, [activeArtifactId]);

  if (!activeArtifact || !activeArtifactId) {
    return (
      <div className="canvas-panel" ref={canvasRef}>
        <div className="canvas-resize" ref={resizeHandleRef} />
        <EmptyCanvas />
      </div>
    );
  }

  const isInternal = !!activeArtifact.internalComponent;
  const isDocument = !isInternal && isDocumentArtifact(activeArtifact);

  return (
    <div className={`canvas-panel${isFullscreen ? ' fullscreen' : ''}`} ref={canvasRef}>
      <div className="canvas-resize" ref={resizeHandleRef} />
      <SessionTabs />
      <div className="canvas-header">
        <ArtifactIcon name={activeArtifact.icon} size={16} className="canvas-header-icon" />
        <span className="canvas-header-title">{activeArtifact.name}</span>
        <LiveIndicator artifact={activeArtifact} />
        <SyncIndicator />
        {isInternal ? (
          <InternalActionBar />
        ) : (
          <ActionBar
            artifact={activeArtifact}
            containerRef={canvasRef}
            isFullscreen={isFullscreen}
            onToggleFullscreen={() => setIsFullscreen((v) => !v)}
          />
        )}
      </div>
      <div className="canvas-body">
        {isInternal ? (
          <InternalRenderer component={activeArtifact.internalComponent!} />
        ) : isDocument ? (
          <DocumentRenderer artifact={activeArtifact} />
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

/**
 * "Live" pulse — like Quick's live=True panel. Shows for ~1.5s after every
 * applyPatch/updateState burst, then fades. Tells the user "this artifact is
 * being actively rewritten by the model right now" without flooding the UI.
 */
function LiveIndicator({ artifact }: { artifact: Artifact }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const ageMs = now - (artifact.updatedAt || 0);
  if (artifact.internalComponent) return null;
  if (ageMs < 1500) {
    return (
      <span
        className="canvas-live-indicator"
        title="Artifact updated just now"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          fontSize: '11px',
          color: 'var(--accent)',
          marginLeft: '6px',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: 'var(--accent)',
            animation: 'pulse 1.2s ease-in-out infinite',
          }}
        />
        Live
      </span>
    );
  }
  return null;
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
