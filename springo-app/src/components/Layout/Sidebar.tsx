import { useState, useCallback, useRef, useEffect } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import type { Conversation, ConversationStatus } from '@/types';

function getStatusTitle(status: ConversationStatus): string {
  const titles: Record<string, string> = {
    idle: 'Ready',
    running: 'Running...',
    completed: 'Completed',
    error: 'Error',
    compacting: 'Compacting...',
  };
  return titles[status] || 'Ready';
}

function groupSessions(sessions: Conversation[]): Record<string, Conversation[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const weekAgo = today - 7 * 86400000;

  const groups: Record<string, Conversation[]> = {
    Today: [],
    Yesterday: [],
    'This Week': [],
    Older: [],
  };

  for (const s of sessions) {
    const ts = s.updatedAt || s.createdAt;
    if (ts >= today) groups.Today.push(s);
    else if (ts >= yesterday) groups.Yesterday.push(s);
    else if (ts >= weekAgo) groups['This Week'].push(s);
    else groups.Older.push(s);
  }

  return groups;
}

export default function Sidebar() {
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);

  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  const [search, setSearch] = useState('');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

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
    (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      deleteSession(id);
    },
    [deleteSession],
  );

  const startRename = useCallback(
    (id: string, title: string, e: React.MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
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

  const filtered = search
    ? sessions.filter((s) =>
        s.title.toLowerCase().includes(search.toLowerCase()),
      )
    : sessions;

  const grouped = groupSessions(filtered);
  const totalCount = sessions.length;

  return (
    <div className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
      <div className="sidebar-header">
        <button className="hamburger-btn" onClick={toggleSidebar} title="Toggle sidebar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        {sidebarOpen && (
          <button className="new-chat-btn" onClick={handleNewChat} title="New Chat">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        )}
      </div>

      {sidebarOpen && (
        <>
          <div className="sidebar-search">
            <input
              type="text"
              placeholder="Search sessions..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="search-input"
            />
          </div>

          <div className="conversations-list">
            {Object.entries(grouped).map(([group, items]) => {
              if (items.length === 0) return null;
              return (
                <div key={group} className="session-group">
                  <div className="session-group-label">{group}</div>
                  {items.map((session) => {
                    const sessionNumber =
                      totalCount - sessions.indexOf(session);
                    const isActive = session.id === currentSessionId;
                    const isRenaming = renamingId === session.id;

                    return (
                      <div
                        key={session.id}
                        className={`conversation-item ${isActive ? 'active' : ''}`}
                        onClick={() => handleSwitch(session.id)}
                        data-id={session.id}
                      >
                        <div
                          className={`conversation-status ${session.status}`}
                          title={getStatusTitle(session.status)}
                        />
                        <span className="session-number">#{sessionNumber}</span>
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
                          <span
                            className="title"
                            onDoubleClick={(e) =>
                              startRename(session.id, session.title, e)
                            }
                            title="Double-click to rename"
                          >
                            {session.title}
                          </span>
                        )}
                        <DelegationBadges convId={session.id} />
                        <button
                          className="delete-btn"
                          onClick={(e) => handleDelete(session.id, e)}
                          title="Delete session"
                        >
                          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M3 3l8 8M11 3l-8 8" />
                          </svg>
                        </button>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
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
