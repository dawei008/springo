import { useSessionStore } from '@/stores/sessionStore';
import { useUIStore } from '@/stores/uiStore';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import { useRecordingStore } from '@/stores/recordingStore';
import { useVoiceStore } from '@/stores/voiceStore';

function openInternalPanel(
  component: 'tasks' | 'schedules' | 'meeting' | 'recording' | 'kb-graph',
  title: string,
) {
  useUnifiedArtifactStore.getState().openInternal(component, title);
}

function HeaderToolButton({
  icon,
  label,
  badge,
  rec,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  badge?: string | number;
  rec?: boolean;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      className={`header-tool-btn${active ? ' active' : ''}`}
      title={label}
      onClick={onClick}
    >
      {icon}
      {rec && <span className="header-tool-status recording" />}
      {badge != null && <span className="header-tool-badge">{badge}</span>}
    </button>
  );
}

function HeaderTools() {
  const todos = useUIStore((s) => s.todos);
  const activeArtifact = useUnifiedArtifactStore((s) =>
    s.activeArtifactId ? s.artifacts[s.activeArtifactId] ?? null : null,
  );
  const isRecording = useRecordingStore((s) => s.isRecording);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const hasActiveTasks = todos.some((t) => t.status === 'in_progress');

  return (
    <div className="header-tools">
      <HeaderToolButton
        icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>}
        label="Tasks"
        badge={todos.length > 0 ? todos.length : undefined}
        rec={hasActiveTasks}
        active={activeArtifact?.internalComponent === 'tasks'}
        onClick={() => openInternalPanel('tasks', 'Tasks')}
      />
      <HeaderToolButton
        icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>}
        label="Schedules"
        active={activeArtifact?.internalComponent === 'schedules'}
        onClick={() => openInternalPanel('schedules', 'Schedules')}
      />
      <div className="header-tool-group">
        <HeaderToolButton
          icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>}
          label="Knowledge"
          active={activeArtifact?.internalComponent === 'kb-graph'}
          onClick={() => openInternalPanel('kb-graph', 'Knowledge Base')}
        />
        <button
          className="header-tool-plus"
          title="Ingest text into KB"
          onClick={async (e) => {
            e.stopPropagation();
            const title = window.prompt('KB ingest — title for this snippet:');
            if (!title || !title.trim()) return;
            const content = window.prompt('Paste content (will be saved to ~/.springo/kb/raw/):');
            if (!content || !content.trim()) return;
            const { useKBStore } = await import('@/stores/kbStore');
            const r = await useKBStore.getState().ingestText({ title: title.trim(), content: content.trim() });
            if (r) {
              useUIStore.getState().showToast(`Ingested → ${r.raw_path}`, 'success');
              openInternalPanel('kb-graph', 'Knowledge Base');
            }
          }}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>
      <HeaderToolButton
        icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>}
        label="Meeting Notes"
        rec={isTranscribing}
        active={activeArtifact?.internalComponent === 'meeting'}
        onClick={() => openInternalPanel('meeting', 'Meeting Notes')}
      />
      <HeaderToolButton
        icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><circle cx="12" cy="10" r="3"/></svg>}
        label="Screen Recording"
        rec={isRecording}
        active={activeArtifact?.internalComponent === 'recording'}
        onClick={() => openInternalPanel('recording', 'Screen Recording')}
      />
    </div>
  );
}

export default function Header() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );

  const headerTitle =
    currentSessionId && session?.title ? session.title : 'New Chat';

  return (
    <div className="header" style={!sidebarOpen ? { paddingLeft: 78, gap: 8 } : undefined}>
      {!sidebarOpen && (
        <button className="titlebar-sidebar-toggle" onClick={toggleSidebar} title="Show sidebar (⌘⇧S)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
        </button>
      )}
      <span className="header-title" id="header-title">
        {headerTitle}
      </span>
      <HeaderTools />
    </div>
  );
}
