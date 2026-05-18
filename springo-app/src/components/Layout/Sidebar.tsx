import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useRecordingStore } from '@/stores/recordingStore';
import { useVoiceStore } from '@/stores/voiceStore';
import { useReplayStore } from '@/stores/replayStore';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import { ArtifactIcon } from '@/components/Canvas/ArtifactIcon';
import { getCleanupSuggestions, countActionableSuggestions } from '@/utils/cleanupSuggestions';
import CleanupModal from '@/components/Layout/CleanupModal';
import type { SessionMode } from '@/types';

// ─── Section Header (collapsible) ───

function SectionHeader({
  title,
  collapsed,
  onToggle,
  onAdd,
}: {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  onAdd?: () => void;
}) {
  return (
    <div className="nav-section-header" onClick={onToggle}>
      <div className="nav-section-title">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {collapsed ? <path d="m9 6 6 6-6 6" /> : <path d="m6 9 6 6 6-6" />}
        </svg>
        {title}
      </div>
      {onAdd && (
        <div
          className="nav-section-action"
          onClick={(e) => { e.stopPropagation(); onAdd(); }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </div>
      )}
    </div>
  );
}

// ─── Context Menu ───

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  sessionId: string;
  sessionTitle: string;
}

function ConversationContextMenu({
  menu,
  pinned,
  onClose,
  onRename,
  onExport,
  onCopyId,
  onTogglePin,
}: {
  menu: ContextMenuState;
  pinned: boolean;
  onClose: () => void;
  onRename: () => void;
  onExport: () => void;
  onCopyId: () => void;
  onTogglePin: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  if (!menu.visible) return null;

  const style: React.CSSProperties = {
    position: 'fixed',
    top: menu.y,
    left: menu.x,
    zIndex: 1000,
  };

  return (
    <div className="conv-context-menu" ref={menuRef} style={style}>
      <div
        className="conv-context-menu-item"
        onClick={(e) => { e.stopPropagation(); onTogglePin(); }}
      >
        <svg width="14" height="14" fill={pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          <path d="M12 17v5" fill="none" />
          <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
        </svg>
        {pinned ? 'Unpin from top' : 'Pin to top'}
      </div>
      <div
        className="conv-context-menu-item"
        onClick={(e) => { e.stopPropagation(); onRename(); }}
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
        Rename
      </div>
      <div
        className="conv-context-menu-item"
        onClick={(e) => { e.stopPropagation(); onExport(); }}
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        Export
      </div>
      <div
        className="conv-context-menu-item"
        onClick={(e) => { e.stopPropagation(); onCopyId(); }}
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
        Copy Session ID
      </div>
    </div>
  );
}

// ─── Nav Item ───

function NavItem({
  icon,
  label,
  badge,
  status,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  badge?: string | number;
  status?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <div className={`nav-item${active ? ' active' : ''}`} onClick={onClick}>
      <div className="nav-item-icon">{icon}</div>
      <div className="nav-item-label">{label}</div>
      {status && <div className={`nav-item-status${status === 'rec' ? ' recording' : ''}`} />}
      {badge != null && <div className="nav-item-badge">{badge}</div>}
    </div>
  );
}

// ─── Session Mode Icon (used in session list) ───

function SessionModeIcon({ mode, status }: { mode?: SessionMode; status?: string }) {
  const isAnimated = status === 'running' || status === 'compacting';
  const statusClass = ['error', 'completed-unseen'].includes(status || '') ? ` ${status}` : '';
  const cls = `session-mode-icon${isAnimated ? ' animated' : ''}${statusClass}`;

  switch (mode) {
    case 'design':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="13.5" cy="6.5" r="2.5"/><path d="M17 2h2a2 2 0 0 1 2 2v2"/><path d="M2 17v2a2 2 0 0 0 2 2h2"/><circle cx="10.5" cy="17.5" r="2.5"/><path d="M2 7V4a2 2 0 0 1 2-2h3"/><path d="M22 17v3a2 2 0 0 1-2 2h-3"/></svg>
        </div>
      );
    case 'plan':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        </div>
      );
    case 'team':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </div>
      );
    case 'meeting':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
        </div>
      );
    case 'recording':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><circle cx="12" cy="10" r="3"/></svg>
        </div>
      );
    case 'novel':
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
        </div>
      );
    default:
      return (
        <div className={cls}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
      );
  }
}

// ─── Pinned Section (chats + artifacts mixed, sorted by last used) ───

interface PinnedItem {
  kind: 'chat' | 'artifact';
  id: string;
  title: string;
  mode?: SessionMode;
  iconName?: string;
  lastUsed: number;
}

function PinnedSection({
  collapsed,
  onToggle,
  items,
  onOpenChat,
  onUnpinChat,
  onDeleteChat,
  onOpenArtifact,
  onUnpinArtifact,
  onDeleteArtifact,
  activeChatId,
  activeArtifactId,
}: {
  collapsed: boolean;
  onToggle: () => void;
  items: PinnedItem[];
  onOpenChat: (id: string) => void;
  onUnpinChat: (id: string) => void;
  onDeleteChat: (id: string, title: string) => void;
  onOpenArtifact: (id: string) => void;
  onUnpinArtifact: (id: string) => void;
  onDeleteArtifact: (id: string, name: string) => void;
  activeChatId: string | null;
  activeArtifactId: string | null;
}) {
  if (items.length === 0) return null;

  return (
    <div className="nav-section">
      <SectionHeader title="Pinned" collapsed={collapsed} onToggle={onToggle} />
      {!collapsed && items.map((item) => {
        const isActive = item.kind === 'chat'
          ? activeChatId === item.id
          : activeArtifactId === item.id;
        const onOpen = item.kind === 'chat'
          ? () => onOpenChat(item.id)
          : () => onOpenArtifact(item.id);
        const onUnpin = item.kind === 'chat'
          ? () => onUnpinChat(item.id)
          : () => onUnpinArtifact(item.id);
        const onDelete = item.kind === 'chat'
          ? () => onDeleteChat(item.id, item.title)
          : () => onDeleteArtifact(item.id, item.title);
        return (
          <div key={`${item.kind}-${item.id}`} className="nav-item-with-action">
            <NavItem
              icon={
                item.kind === 'chat'
                  ? <SessionModeIcon mode={item.mode} />
                  : <ArtifactIcon name={item.iconName} size={14} />
              }
              label={item.title}
              active={isActive}
              onClick={onOpen}
            />
            <button
              className="nav-item-pin-toggle"
              title={item.kind === 'chat' ? 'Unpin chat' : 'Unpin app'}
              onClick={(e) => { e.stopPropagation(); onUnpin(); }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 17v5" fill="none" />
                <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
              </svg>
            </button>
            <button
              className="nav-item-delete"
              title={item.kind === 'chat' ? 'Delete chat' : 'Delete artifact'}
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ─── Apps Section (session-only artifacts; pinned ones moved to PINNED) ───

function AppsSection({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const sessionIds = useUnifiedArtifactStore((s) => s.sessionArtifactIds);
  const pinnedIds = useUnifiedArtifactStore((s) => s.pinnedArtifactIds);
  const artifactMap = useUnifiedArtifactStore((s) => s.artifacts);
  const activeArtifactId = useUnifiedArtifactStore((s) => s.activeArtifactId);
  const openUnifiedArtifact = useUnifiedArtifactStore((s) => s.openArtifact);
  const pinUnifiedArtifact = useUnifiedArtifactStore((s) => s.pinArtifact);
  const deleteArtifact = useUnifiedArtifactStore((s) => s.deleteArtifact);

  // Artifacts belonging to the current session that the user hasn't pinned yet.
  // Pinned artifacts live in the dedicated PINNED section at the top of the sidebar.
  // Internal panels (Tasks/Schedules/Meeting/Recording) have their own TOOLS row.
  const sessionArtifacts = useMemo(
    () => sessionIds.map((id) => artifactMap[id]).filter((a) => a && !a.pinned && !a.internalComponent),
    [sessionIds, artifactMap],
  );

  // "Unattached" artifacts: exist in the store but don't belong to the current
  // session and aren't pinned. Without this section they'd be invisible in the
  // sidebar even though they still take disk space under ~/.springo/artifacts/.
  // Common sources: artifact created in an older session the user hasn't
  // cleaned up, or a botched op left the record around.
  const unattachedArtifacts = useMemo(() => {
    const sessionSet = new Set(sessionIds);
    const pinnedSet = new Set(pinnedIds);
    return Object.values(artifactMap)
      .filter((a) => a && !a.pinned && !a.internalComponent && !sessionSet.has(a.id) && !pinnedSet.has(a.id))
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  }, [artifactMap, sessionIds, pinnedIds]);

  const handleDelete = useCallback((id: string, name: string) => {
    if (window.confirm(`Delete artifact "${name}"? Source and version history will be lost.`)) {
      deleteArtifact(id);
    }
  }, [deleteArtifact]);

  if (sessionArtifacts.length === 0 && unattachedArtifacts.length === 0) return null;

  const showSubheaders = sessionArtifacts.length > 0 && unattachedArtifacts.length > 0;

  const renderArtifactRow = (art: typeof sessionArtifacts[number], orphan: boolean) => (
    <div key={art.id} className="nav-item-with-action">
      <NavItem
        icon={<ArtifactIcon name={art.icon} size={14} />}
        label={art.name}
        active={activeArtifactId === art.id}
        onClick={() => openUnifiedArtifact(art.id)}
      />
      {orphan && (
        <button
          className="nav-item-pin-toggle"
          title="Pin to keep this artifact in your sidebar"
          onClick={(e) => { e.stopPropagation(); pinUnifiedArtifact(art.id); }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 17v5" />
            <path d="M9 10.76a2 2 0 0 1-1.11 1.79L6 13.5V15h12v-1.5l-1.89-.95A2 2 0 0 1 15 10.76V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1Z" />
          </svg>
        </button>
      )}
      <button
        className="nav-item-delete"
        title="Delete artifact"
        onClick={(e) => { e.stopPropagation(); handleDelete(art.id, art.name); }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );

  return (
    <div className="nav-section">
      <SectionHeader title="Apps" collapsed={collapsed} onToggle={onToggle} />
      {!collapsed && (
        <>
          {showSubheaders && sessionArtifacts.length > 0 && (
            <div className="nav-subheader">This session</div>
          )}
          {sessionArtifacts.map((art) => renderArtifactRow(art, false))}
          {unattachedArtifacts.length > 0 && (
            <div className="nav-subheader">Unattached</div>
          )}
          {unattachedArtifacts.map((art) => renderArtifactRow(art, true))}
        </>
      )}
    </div>
  );
}

// ─── Background Tasks Section ───

function openInternalPanel(component: 'tasks' | 'schedules' | 'meeting' | 'recording', title: string) {
  useUnifiedArtifactStore.getState().openInternal(component, title);
}

function ToolsSection({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const todos = useUIStore((s) => s.todos);
  const activeArtifact = useUnifiedArtifactStore((s) =>
    s.activeArtifactId ? s.artifacts[s.activeArtifactId] ?? null : null,
  );
  const isRecording = useRecordingStore((s) => s.isRecording);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const language = useVoiceStore((s) => s.language);

  const activeTasks = todos.filter((t) => t.status === 'in_progress');
  const pendingTasks = todos.filter((t) => t.status === 'pending');

  const handleMeetingToggle = useCallback(() => {
    if (isTranscribing) {
      useVoiceStore.getState().stopTranscription();
      return;
    }
    const sid = useSessionStore.getState().createSession(undefined, 'meeting');
    setTimeout(() => {
      useUnifiedArtifactStore.getState().openInternal('meeting', 'Meeting Notes');
    }, 100);
    useVoiceStore.getState().startTranscription(sid);
  }, [isTranscribing]);

  const handleRecordToggle = useCallback(async () => {
    if (isRecording) {
      if (useReplayStore.getState().isReplaying) {
        useReplayStore.getState().stopReplay();
      }
      await useRecordingStore.getState().stopRecording();
    } else {
      useSessionStore.getState().createSession(undefined, 'recording');
      await useRecordingStore.getState().startRecording();
      setTimeout(() => {
        useUnifiedArtifactStore.getState().openInternal('recording', 'Screen Recording');
      }, 100);
    }
  }, [isRecording]);

  return (
    <div className="nav-section">
      <SectionHeader title="Tools" collapsed={collapsed} onToggle={onToggle} />
      {!collapsed && (
        <>
          <NavItem
            icon={<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>}
            label="Tasks"
            badge={todos.length > 0 ? todos.length : undefined}
            active={activeArtifact?.internalComponent === 'tasks'}
            onClick={() => openInternalPanel('tasks', 'Tasks')}
          />
          <NavItem
            icon={<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>}
            label="Schedules"
            active={activeArtifact?.internalComponent === 'schedules'}
            onClick={() => openInternalPanel('schedules', 'Schedules')}
          />
          <div className="nav-item-with-action">
            <NavItem
              icon={<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>}
              label="Meeting Notes"
              status={isTranscribing ? 'rec' : undefined}
              active={isTranscribing}
              onClick={handleMeetingToggle}
            />
            {isTranscribing && (
              <button
                className="meeting-lang-toggle"
                onClick={(e) => {
                  e.stopPropagation();
                  const cur = useVoiceStore.getState().language;
                  const cycle: Record<string, string> = { zh: 'en', en: 'auto', auto: 'zh' };
                  useVoiceStore.getState().setLanguage(cycle[cur] || 'auto');
                }}
                title="Switch language"
              >
                {language === 'zh' ? 'ZH' : language === 'en' ? 'EN' : 'AUTO'}
              </button>
            )}
          </div>
          <NavItem
            icon={<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><circle cx="12" cy="10" r="3"/></svg>}
            label="Screen Recording"
            status={isRecording ? 'rec' : undefined}
            onClick={handleRecordToggle}
          />
          {activeTasks.length > 0 && (
            <div className="nav-sub">
              {activeTasks.map((task) => (
                <NavItem
                  key={task.id}
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>}
                  label={task.subject}
                  status="rec"
                  onClick={() => openInternalPanel('tasks', 'Tasks')}
                />
              ))}
              {pendingTasks.map((task) => (
                <NavItem
                  key={task.id}
                  icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>}
                  label={task.subject}
                  onClick={() => openInternalPanel('tasks', 'Tasks')}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Sidebar() {
  // ─── Session store ───
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);
  const unseenCompletedSessions = useSessionStore((s) => s.unseenCompletedSessions);
  const pinSession = useSessionStore((s) => s.pinSession);
  const unpinSession = useSessionStore((s) => s.unpinSession);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  // ─── Unified artifact store ───
  const unifiedPinnedIds = useUnifiedArtifactStore((s) => s.pinnedArtifactIds);
  const unifiedArtifacts = useUnifiedArtifactStore((s) => s.artifacts);
  const unifiedActiveArtifactId = useUnifiedArtifactStore((s) => s.activeArtifactId);
  const openUnifiedArtifact = useUnifiedArtifactStore((s) => s.openArtifact);
  const unpinUnifiedArtifact = useUnifiedArtifactStore((s) => s.unpinArtifact);
  const deleteUnifiedArtifact = useUnifiedArtifactStore((s) => s.deleteArtifact);

  // ─── UI store ───
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  // ─── Local state ───
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [cleanupModalOpen, setCleanupModalOpen] = useState(false);
  const [cleanupDismissedIds, setCleanupDismissedIds] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem('springo-cleanup-dismissed');
      return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      return new Set();
    }
  });
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    sessionId: '',
    sessionTitle: '',
  });

  const toggleSection = useCallback((key: string) => {
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // ─── Session auto-title refresh ───
  const prevStreamingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const unsub = useChatStore.subscribe((state) => {
      const currentlyStreaming = new Set<string>();
      for (const [id, runtime] of Object.entries(state.runtimes)) {
        if (runtime.isStreaming) currentlyStreaming.add(id);
      }

      const justFinished: string[] = [];
      for (const id of prevStreamingRef.current) {
        if (!currentlyStreaming.has(id)) {
          justFinished.push(id);
        }
      }

      prevStreamingRef.current = currentlyStreaming;

      for (const id of justFinished) {
        const session = useSessionStore.getState().sessions.find((s) => s.id === id);
        if (session && !session.isCustomTitle) {
          setTimeout(() => {
            let newTitle = '';
            const runtime = useChatStore.getState().runtimes[id];
            if (runtime?.messages) {
              for (let i = runtime.messages.length - 1; i >= 0; i--) {
                const msg = runtime.messages[i];
                if (msg.role === 'user') {
                  let text = '';
                  if (typeof msg.content === 'string') {
                    text = msg.content;
                  } else if (Array.isArray(msg.content)) {
                    const tb = msg.content.find((b: any) => b.type === 'text') as { text?: string } | undefined;
                    text = tb?.text || '';
                  }
                  text = text.replace(/^\[Current time:[^\]]*\]\s*/, '');
                  const skillMatch = text.match(/^<skill\s+name="([^"]+)">[\s\S]*?<\/skill>\s*/);
                  if (skillMatch) {
                    const after = text.slice(skillMatch[0].length);
                    const req = after.replace(/^User request:\s*/i, '').replace(/\s*Please follow the skill instructions above.*$/s, '').trim();
                    text = req ? `/${skillMatch[1]} ${req}` : `/${skillMatch[1]}`;
                  }
                  if (text.trim()) {
                    newTitle = text.trim().substring(0, 40);
                    if (text.trim().length > 40) newTitle += '...';
                    break;
                  }
                }
              }
            }

            const defaultTitles = ['New Chat', 'New Design', 'New Plan', 'Team Chat', 'Meeting Notes', 'Screen Recording', 'Untitled'];
            if (newTitle && !defaultTitles.includes(newTitle)) {
              useSessionStore.setState((s) => ({
                sessions: s.sessions.map((sess) =>
                  sess.id === id ? { ...sess, title: newTitle } : sess,
                ),
              }));
              fetch(`http://127.0.0.1:8081/v1/sessions/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ metadata: { title: newTitle } }),
              }).catch(() => {});
            }
          }, 500);
        }
      }
    });
    return unsub;
  }, []);

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  // ─── Filtered sessions (search) ───
  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase().trim();
    return sessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  // ─── Handlers ───

  const handleNewChat = useCallback(() => {
    createSession();
  }, [createSession]);

  const handleSwitch = useCallback(
    (id: string) => {
      if (renamingId) return;
      switchSession(id);
    },
    [switchSession, renamingId],
  );

  const handleDelete = useCallback(
    (id: string) => {
      deleteSession(id);
    },
    [deleteSession],
  );

  const handlePinnedChatDelete = useCallback(
    (id: string, title: string) => {
      if (window.confirm(`Delete chat "${title}"? This removes all messages.`)) {
        deleteSession(id);
      }
    },
    [deleteSession],
  );

  const handlePinnedArtifactDelete = useCallback(
    (id: string, name: string) => {
      if (window.confirm(`Delete artifact "${name}"? Source and version history will be lost.`)) {
        deleteUnifiedArtifact(id);
      }
    },
    [deleteUnifiedArtifact],
  );

  const startRename = useCallback(
    (id: string, title: string) => {
      setRenamingId(id);
      setRenameValue(title);
    },
    [],
  );

  const finishRename = useCallback(() => {
    if (renamingId && renameValue.trim()) {
      renameSession(renamingId, renameValue.trim().slice(0, 200));
    }
    setRenamingId(null);
    setRenameValue('');
  }, [renamingId, renameValue, renameSession]);

  const cancelRename = useCallback(() => {
    setRenamingId(null);
    setRenameValue('');
  }, []);

  // Context menu handlers
  const handleContextMenu = useCallback(
    (id: string, title: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setContextMenu({
        visible: true,
        x: e.clientX,
        y: e.clientY,
        sessionId: id,
        sessionTitle: title,
      });
    },
    [],
  );

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, []);

  const handleContextRename = useCallback(() => {
    startRename(contextMenu.sessionId, contextMenu.sessionTitle);
    closeContextMenu();
  }, [contextMenu, startRename, closeContextMenu]);

  const handleContextExport = useCallback(async () => {
    const id = contextMenu.sessionId;
    closeContextMenu();
    try {
      const res = await fetch(`http://127.0.0.1:8081/v1/sessions/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `session-${id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  }, [contextMenu, closeContextMenu]);

  const handleContextCopyId = useCallback(() => {
    const id = contextMenu.sessionId;
    closeContextMenu();
    navigator.clipboard.writeText(id).catch(() => {});
  }, [contextMenu, closeContextMenu]);

  const handleContextTogglePin = useCallback(() => {
    const id = contextMenu.sessionId;
    const current = sessions.find((s) => s.id === id);
    closeContextMenu();
    if (!current) return;
    if (current.pinned) unpinSession(id);
    else pinSession(id);
  }, [contextMenu, closeContextMenu, sessions, pinSession, unpinSession]);

  const contextMenuPinned = useMemo(
    () => !!sessions.find((s) => s.id === contextMenu.sessionId)?.pinned,
    [sessions, contextMenu.sessionId],
  );

  const handleOpenSettings = useCallback(() => {
    setSettingsOpen(true);
  }, [setSettingsOpen]);

  // ─── Pinned items (chats + artifacts mixed, sorted by last used) ───
  const pinnedItems = useMemo<PinnedItem[]>(() => {
    const items: PinnedItem[] = [];
    for (const s of sessions) {
      if (!s.pinned) continue;
      items.push({
        kind: 'chat',
        id: s.id,
        title: s.title,
        mode: s.mode,
        lastUsed: s.updatedAt || s.pinnedAt || s.createdAt || 0,
      });
    }
    for (const id of unifiedPinnedIds) {
      const a = unifiedArtifacts[id];
      if (!a) continue;
      items.push({
        kind: 'artifact',
        id: a.id,
        title: a.name,
        iconName: a.icon,
        lastUsed: a.updatedAt || a.createdAt || 0,
      });
    }
    items.sort((a, b) => b.lastUsed - a.lastUsed);
    return items;
  }, [sessions, unifiedPinnedIds, unifiedArtifacts]);

  // ─── Cleanup suggestions (replaces the old "empty chats" auto-fold) ───
  // Periodic background scan: re-compute disposable-chat suggestions every 30m,
  // and on mount. Updates `cleanupTick` to force the memo below to re-run.
  const [cleanupTick, setCleanupTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setCleanupTick((n) => n + 1), 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const runtimesSnapshot = useChatStore((s) => s.runtimes);
  const cleanupSuggestions = useMemo(
    () => getCleanupSuggestions(sessions, runtimesSnapshot),
    // cleanupTick intentionally included to pick up age changes without
    // waiting for an external store update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessions, runtimesSnapshot, cleanupTick],
  );
  const actionableCleanupCount = useMemo(
    () => countActionableSuggestions(cleanupSuggestions, cleanupDismissedIds),
    [cleanupSuggestions, cleanupDismissedIds],
  );

  const persistDismissed = useCallback((next: Set<string>) => {
    setCleanupDismissedIds(next);
    try {
      localStorage.setItem('springo-cleanup-dismissed', JSON.stringify(Array.from(next)));
    } catch { /* quota — ignore */ }
  }, []);

  const dismissCleanupSuggestions = useCallback((ids: string[]) => {
    const next = new Set(cleanupDismissedIds);
    for (const id of ids) next.add(id);
    persistDismissed(next);
  }, [cleanupDismissedIds, persistDismissed]);

  const handleBulkCleanupDelete = useCallback(async (ids: string[]) => {
    // Also drop these from dismissed set since they're gone anyway.
    const next = new Set(cleanupDismissedIds);
    for (const id of ids) next.delete(id);
    persistDismissed(next);
    for (const id of ids) {
      await deleteSession(id);
    }
  }, [cleanupDismissedIds, persistDismissed, deleteSession]);

  // ─── Date-grouped sessions (pinned excluded — they live in PINNED section) ───
  // All non-pinned chats show up here — no auto-folding. The CleanupBanner
  // surfaces abandoned ones explicitly when it's time to prune.
  const groupedSessions = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayStart = todayStart - 86400000;
    const weekStart = todayStart - 6 * 86400000;

    const groups: { label: string; isToday?: boolean; sessions: typeof filteredSessions }[] = [
      { label: 'Today', isToday: true, sessions: [] },
      { label: 'Yesterday', sessions: [] },
      { label: 'Last 7 days', sessions: [] },
      { label: 'Older', sessions: [] },
    ];

    for (const session of filteredSessions) {
      if (session.pinned) continue;
      const ts = session.updatedAt || session.createdAt || 0;
      if (ts >= todayStart) groups[0].sessions.push(session);
      else if (ts >= yesterdayStart) groups[1].sessions.push(session);
      else if (ts >= weekStart) groups[2].sessions.push(session);
      else groups[3].sessions.push(session);
    }

    return { groups: groups.filter((g) => g.sessions.length > 0) };
  }, [filteredSessions]);

  const totalCount = sessions.filter((s) => !s.pinned).length;

  const sidebarRef = useRef<HTMLElement>(null);
  const sidebarResizeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handle = sidebarResizeRef.current;
    const sidebar = sidebarRef.current;
    if (!handle || !sidebar) return;

    let dragging = false;
    let startX = 0;
    let startW = 0;

    const onDown = (e: MouseEvent) => {
      dragging = true;
      startX = e.clientX;
      startW = sidebar.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      const w = Math.min(480, Math.max(200, startW + (e.clientX - startX)));
      sidebar.style.width = w + 'px';
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    handle.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      handle.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  return (
    <aside className={`sidebar${sidebarOpen ? '' : ' collapsed'}`} ref={sidebarRef}>
      <div className="sidebar-resize" ref={sidebarResizeRef} />
      {/* Sidebar header */}
      <div className="sidebar-header">
        <button className="titlebar-sidebar-toggle" onClick={toggleSidebar} title="Hide sidebar (⌘⇧S)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
        </button>
        <div className="brand-name">Springo</div>
      </div>

      {/* Scrollable content */}
      <div className="sidebar-scroll">
        {/* Primary new-chat button */}
        <button className="sidebar-primary-btn" onClick={handleNewChat}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Start new chat
        </button>

        {/* Pinned section (chats + artifacts) */}
        <PinnedSection
          collapsed={!!collapsed.pinned}
          onToggle={() => toggleSection('pinned')}
          items={pinnedItems}
          onOpenChat={handleSwitch}
          onUnpinChat={unpinSession}
          onDeleteChat={handlePinnedChatDelete}
          onOpenArtifact={openUnifiedArtifact}
          onUnpinArtifact={unpinUnifiedArtifact}
          onDeleteArtifact={handlePinnedArtifactDelete}
          activeChatId={currentSessionId}
          activeArtifactId={unifiedActiveArtifactId}
        />

        {/* Conversations */}
        <div className="nav-section">
          <SectionHeader
            title={`Chats (${totalCount})`}
            collapsed={!!collapsed.conversations}
            onToggle={() => toggleSection('conversations')}
            onAdd={handleNewChat}
          />
          {!collapsed.conversations && (
            <>
              {/* Search bar inside conversations */}
              <div className="sidebar-search">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
                <input
                  type="text"
                  placeholder="Search conversations..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  id="sidebar-search"
                />
                {searchQuery ? (
                  <button
                    className="search-clear-btn"
                    onClick={() => setSearchQuery('')}
                  >
                    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M2 2l8 8M10 2l-8 8"/>
                    </svg>
                  </button>
                ) : (
                  <span className="kbd">⌘K</span>
                )}
              </div>
              {actionableCleanupCount > 0 && !searchQuery.trim() && (
                <div className="cleanup-banner">
                  <div className="cleanup-banner-icon" aria-hidden="true">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                      <path d="M10 11v6M14 11v6" />
                    </svg>
                  </div>
                  <div className="cleanup-banner-text">
                    <strong>{actionableCleanupCount}</strong> chat{actionableCleanupCount === 1 ? '' : 's'} look disposable
                  </div>
                  <button
                    className="cleanup-banner-action"
                    onClick={() => setCleanupModalOpen(true)}
                  >
                    Review
                  </button>
                  <button
                    className="cleanup-banner-dismiss"
                    title="Dismiss until new chats qualify"
                    onClick={() => dismissCleanupSuggestions(cleanupSuggestions.map((s) => s.session.id))}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              )}
            <div className="session-list">
              {groupedSessions.groups.map((group) => (
                <div key={group.label}>
                  <div className="session-date-group">{group.label}</div>
                  {group.sessions.map((session) => {
                    const rawStatus = session.status || 'idle';
                    const isActive = session.id === currentSessionId;
                    const isRenaming = renamingId === session.id;

                    let visualStatus: string = rawStatus;
                    if (rawStatus === 'idle') {
                      if (unseenCompletedSessions.has(session.id)) {
                        visualStatus = 'completed-unseen';
                      } else if (isActive) {
                        visualStatus = 'current';
                      } else if (group.isToday || group.label === 'Yesterday') {
                        visualStatus = 'recent';
                      }
                    }

                    return (
                      <div
                        key={session.id}
                        className={`session-item${isActive ? ' active' : ''}`}
                        onClick={() => handleSwitch(session.id)}
                        onContextMenu={(e) => handleContextMenu(session.id, session.title, e)}
                        data-id={session.id}
                      >
                        <SessionModeIcon mode={session.mode} status={visualStatus} />
                        <div className="session-content">
                          {isRenaming ? (
                            <input
                              ref={renameInputRef}
                              type="text"
                              className="rename-input"
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault();
                                  finishRename();
                                } else if (e.key === 'Escape') {
                                  e.preventDefault();
                                  cancelRename();
                                }
                              }}
                              onBlur={finishRename}
                              onClick={(e) => e.stopPropagation()}
                            />
                          ) : (
                            <div
                              className="session-title"
                              onDoubleClick={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                                startRename(session.id, session.title);
                              }}
                              title="Double-click to rename"
                            >
                              {session.title}
                            </div>
                          )}
                        </div>
                        <DelegationBadges convId={session.id} />
                        <button
                          className="session-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(session.id);
                          }}
                          title="Delete session"
                        >
                          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M3 3l8 8M11 3l-8 8"/>
                          </svg>
                        </button>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            </>
          )}
        </div>

        {/* Apps (session-only artifacts) */}
        <AppsSection collapsed={!!collapsed.apps} onToggle={() => toggleSection('apps')} />

        {/* Tools (system panels) */}
        <ToolsSection
          collapsed={!!collapsed.tools}
          onToggle={() => toggleSection('tools')}
        />
      </div>

      {/* Conversation context menu */}
      <ConversationContextMenu
        menu={contextMenu}
        pinned={contextMenuPinned}
        onClose={closeContextMenu}
        onRename={handleContextRename}
        onExport={handleContextExport}
        onCopyId={handleContextCopyId}
        onTogglePin={handleContextTogglePin}
      />

      {cleanupModalOpen && (
        <CleanupModal
          suggestions={cleanupSuggestions}
          onDelete={handleBulkCleanupDelete}
          onDismissIds={dismissCleanupSuggestions}
          onClose={() => setCleanupModalOpen(false)}
        />
      )}

      {/* Sidebar footer */}
      <div className="sidebar-footer">
        <div className="footer-avatar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
        <div className="footer-user-info">
          <div className="footer-user-name">Springo User</div>
          <div className="footer-user-plan">Local · Bedrock</div>
        </div>
        <button className="icon-btn-sm" onClick={handleOpenSettings} title="Settings">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>
    </aside>
  );
}

function DelegationBadges({ convId }: { convId: string }) {
  const runtime = useChatStore((s) => s.runtimes[convId]);
  if (!runtime) return null;

  const delegated = Object.values(runtime.delegatedTasks || {});
  const activeDelegations = delegated.filter(
    (t) => t.status === 'pending' || t.status === 'running',
  );
  const incoming = Object.values(runtime.incomingTasks || {});
  const activeIncoming = incoming.filter(
    (t) => t.status === 'pending' || t.status === 'running',
  );

  if (activeDelegations.length === 0 && activeIncoming.length === 0) return null;

  return (
    <div className="delegation-badges">
      {activeDelegations.length > 0 && (
        <span
          className={`delegation-badge outgoing ${activeDelegations.some((t) => t.status === 'running') ? 'executing' : ''}`}
          title={`Delegated ${activeDelegations.length} task(s)`}
        >
          &rarr;{activeDelegations.length}
        </span>
      )}
      {activeIncoming.length > 0 && (
        <span
          className={`delegation-badge incoming ${activeIncoming.some((t) => t.status === 'running') ? 'executing' : ''}`}
          title={`Executing ${activeIncoming.length} delegated task(s)`}
        >
          &larr;{activeIncoming.length}
        </span>
      )}
    </div>
  );
}
