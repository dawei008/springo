import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import ToolsPanel from './ToolsPanel';
// ConversationStatus type used indirectly via session.status

function getStatusTitle(visualStatus: string): string {
  const titles: Record<string, string> = {
    idle: 'Inactive',
    active: 'Active',
    running: 'Running...',
    completed: 'Completed',
    error: 'Error',
    compacting: 'Compacting...',
  };
  return titles[visualStatus] || 'Inactive';
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
  onClose,
  onRename,
  onDelete,
  onExport,
}: {
  menu: ContextMenuState;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onExport: () => void;
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

  // Adjust position to stay within viewport
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
      <div className="conv-context-menu-divider" />
      <div
        className="conv-context-menu-item delete"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
        </svg>
        Delete
      </div>
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
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);

  // ─── Settings store (workspace) ───
  const workingDir = useSettingsStore((s) => s.workingDir);
  const workingFolders = useSettingsStore((s) => s.workingFolders);
  const defaultWorkingFolder = useSettingsStore((s) => s.defaultWorkingFolder);
  const setWorkingDir = useSettingsStore((s) => s.setWorkingDir);

  // ─── UI store ───
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  // ─── Local state ───
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    sessionId: '',
    sessionTitle: '',
  });

  // ─── Session auto-title refresh ───
  // Subscribe to chatStore runtimes to detect when streaming ends, then
  // re-fetch the session title from the backend (which auto-generates titles).
  const prevStreamingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const unsub = useChatStore.subscribe((state) => {
      const currentlyStreaming = new Set<string>();
      for (const [id, runtime] of Object.entries(state.runtimes)) {
        if (runtime.isStreaming) currentlyStreaming.add(id);
      }

      // Find sessions that just stopped streaming
      const justFinished: string[] = [];
      for (const id of prevStreamingRef.current) {
        if (!currentlyStreaming.has(id)) {
          justFinished.push(id);
        }
      }

      prevStreamingRef.current = currentlyStreaming;

      // For sessions that just finished streaming, re-fetch their title
      for (const id of justFinished) {
        const session = useSessionStore.getState().sessions.find((s) => s.id === id);
        if (session && !session.isCustomTitle) {
          // Small delay to let backend finish saving the session metadata
          setTimeout(() => {
            fetch(`http://127.0.0.1:8081/v1/sessions/${id}`)
              .then((res) => (res.ok ? res.json() : null))
              .then((data) => {
                let newTitle = '';
                if (data) {
                  const meta = data.metadata || {};
                  newTitle = meta.title || data.title || '';
                }
                // Fallback: generate title from local messages (like legacy)
                if (!newTitle || newTitle === 'New Chat' || newTitle === 'Untitled') {
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
                        // Strip time prefix: [Current time: ...]
                        text = text.replace(/^\[Current time:[^\]]*\]\s*/, '');
                        // Strip skill wrapper
                        const skillMatch = text.match(/^<skill\s+name="([^"]+)">[\s\S]*?<\/skill>\s*/);
                        if (skillMatch) {
                          const after = text.slice(skillMatch[0].length);
                          const req = after.replace(/^User request:\s*/i, '').replace(/\s*Please follow the skill instructions above.*$/s, '').trim();
                          text = req ? `/${skillMatch[1]} ${req}` : `/${skillMatch[1]}`;
                        }
                        if (text.trim()) {
                          newTitle = text.trim().substring(0, 30);
                          if (text.trim().length > 30) newTitle += '...';
                          break;
                        }
                      }
                    }
                  }
                }

                if (newTitle && newTitle !== 'New Chat' && newTitle !== 'Untitled') {
                  useSessionStore.setState((s) => ({
                    sessions: s.sessions.map((sess) =>
                      sess.id === id ? { ...sess, title: newTitle } : sess,
                    ),
                  }));
                  // Also persist to backend
                  fetch(`http://127.0.0.1:8081/v1/sessions/${id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ metadata: { title: newTitle } }),
                  }).catch(() => {});
                }
              })
              .catch(() => {});
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

  const handleContextDelete = useCallback(() => {
    handleDelete(contextMenu.sessionId);
    closeContextMenu();
  }, [contextMenu, handleDelete, closeContextMenu]);

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

  const handleAddFolder = useCallback(async () => {
    if (window.electronAPI?.selectFolder) {
      const result = await window.electronAPI.selectFolder();
      if (result) {
        // selectFolder returns a string (single folder path) or possibly array
        const folders = Array.isArray(result) ? result : [result];
        const currentFolders = useSettingsStore.getState().workingFolders;
        let newFolder: string | null = null;
        const updatedFolders = [...currentFolders];

        for (const folder of folders) {
          if (!updatedFolders.includes(folder)) {
            updatedFolders.push(folder);
            newFolder = folder;
          }
        }

        if (newFolder) {
          // Persist to store and cache
          const state = useSettingsStore.getState();
          useSettingsStore.setState({ workingFolders: updatedFolders });
          if (window.electronAPI?.cache) {
            window.electronAPI.cache.set('workspace', {
              workingFolders: updatedFolders,
              currentWorkingDir: newFolder,
              defaultWorkingFolder: state.defaultWorkingFolder,
            });
          }
          setWorkingDir(newFolder);
        }
      }
    } else {
      // Fallback: prompt for path
      const path = prompt('Enter folder path:');
      if (path && path.trim()) {
        const trimmedPath = path.trim();
        const currentFolders = useSettingsStore.getState().workingFolders;
        if (!currentFolders.includes(trimmedPath)) {
          const updatedFolders = [...currentFolders, trimmedPath];
          const state = useSettingsStore.getState();
          useSettingsStore.setState({ workingFolders: updatedFolders });
          if (window.electronAPI?.cache) {
            window.electronAPI.cache.set('workspace', {
              workingFolders: updatedFolders,
              currentWorkingDir: trimmedPath,
              defaultWorkingFolder: state.defaultWorkingFolder,
            });
          }
          setWorkingDir(trimmedPath);
        }
      }
    }
  }, [setWorkingDir]);

  const handleRemoveFolder = useCallback(
    (index: number, e: React.MouseEvent) => {
      e.stopPropagation();
      const currentFolders = useSettingsStore.getState().workingFolders;
      const updatedFolders = [...currentFolders];
      updatedFolders.splice(index, 1);

      const state = useSettingsStore.getState();
      useSettingsStore.setState({ workingFolders: updatedFolders });
      if (window.electronAPI?.cache) {
        window.electronAPI.cache.set('workspace', {
          workingFolders: updatedFolders,
          currentWorkingDir: state.workingDir,
          defaultWorkingFolder: state.defaultWorkingFolder,
        });
      }
    },
    [],
  );

  const handleFolderClick = useCallback(
    (folder: string, e: React.MouseEvent) => {
      // Prevent double-click from triggering single-click
      if (e.detail > 1) return;
      // Open file browser panel (matches legacy behavior)
      useUIStore.getState().openFileBrowser(folder);
    },
    [],
  );

  const handleFolderDoubleClick = useCallback((folder: string) => {
    if (window.electronAPI?.openFolder) {
      window.electronAPI.openFolder(folder);
    }
  }, []);

  const handleOpenSettings = useCallback(() => {
    setSettingsOpen(true);
  }, [setSettingsOpen]);

  // ─── Date-grouped sessions ───
  const groupedSessions = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayStart = todayStart - 86400000;
    const weekStart = todayStart - 6 * 86400000;

    const groups: { label: string; sessions: typeof filteredSessions }[] = [
      { label: 'Today', sessions: [] },
      { label: 'Yesterday', sessions: [] },
      { label: 'Last 7 days', sessions: [] },
      { label: 'Older', sessions: [] },
    ];

    for (const session of filteredSessions) {
      const ts = session.createdAt || 0;
      if (ts >= todayStart) {
        groups[0].sessions.push(session);
      } else if (ts >= yesterdayStart) {
        groups[1].sessions.push(session);
      } else if (ts >= weekStart) {
        groups[2].sessions.push(session);
      } else {
        groups[3].sessions.push(session);
      }
    }

    return groups.filter((g) => g.sessions.length > 0);
  }, [filteredSessions]);

  // ─── Derived state ───

  // Determine actual working dir (conversation's workdir takes priority)
  let actualWorkdir = workingDir;
  if (currentSessionId) {
    const conv = sessions.find((s) => s.id === currentSessionId);
    if (conv?.workingDir) {
      actualWorkdir = conv.workingDir;
    }
  }

  const totalCount = sessions.length;

  return (
    <div className={`sidebar${sidebarOpen ? '' : ' collapsed'}`}>
      {/* Sidebar header: dog SVG logo + "Springo" h1 */}
      <div className="sidebar-header">
        <svg width="24" height="24" viewBox="0 0 100 100" fill="none" stroke="currentColor" style={{ color: 'var(--accent)' }} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          {/* Springer Spaniel sketch style */}
          {/* Head */}
          <ellipse cx="50" cy="38" rx="22" ry="20"/>
          {/* Left ear (floppy) */}
          <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55"/>
          {/* Right ear (floppy) */}
          <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55"/>
          {/* Eyes */}
          <circle cx="40" cy="35" r="3" fill="currentColor"/>
          <circle cx="60" cy="35" r="3" fill="currentColor"/>
          {/* Nose */}
          <ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor"/>
          {/* Mouth */}
          <path d="M45 52 Q50 58, 55 52"/>
          {/* Body hint */}
          <path d="M35 56 Q50 65, 65 56"/>
        </svg>
        <h1>Springo</h1>
      </div>

      {/* Workspace Section */}
      <div className="working-folders-section">
        <div className="working-folders-header">
          <span>Workspace</span>
          <button className="add-folder-btn" onClick={handleAddFolder} title="Add folder">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 2v10M2 7h10"/>
            </svg>
          </button>
        </div>
        <div className="working-folders-list" id="working-folders-list">
          {workingFolders.length === 0 ? (
            <div className="working-folders-empty" id="working-folders-empty">
              Click + to add folders
            </div>
          ) : (
            workingFolders.map((folder, index) => {
              const name = folder.split('/').pop() || folder;
              const isActive = folder === actualWorkdir;
              const isDefault = folder === defaultWorkingFolder;

              return (
                <div
                  key={folder}
                  className={`folder-item${isActive ? ' active' : ''}${isDefault ? ' default' : ''}`}
                  draggable
                  onClick={(e) => handleFolderClick(folder, e)}
                  onDoubleClick={() => handleFolderDoubleClick(folder)}
                >
                  <span className="status-dot"></span>
                  <svg className="folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                  </svg>
                  <span className="folder-name" title={folder}>{name}</span>
                  {!isDefault && (
                    <button
                      className="remove-folder"
                      onClick={(e) => handleRemoveFolder(index, e)}
                      title="Remove folder"
                    >
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M2 2l8 8M10 2l-8 8"/>
                      </svg>
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Skills & Tools panel */}
      <ToolsPanel />

      {/* New Chat button */}
      <button className="new-chat-btn" onClick={handleNewChat}>
        <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 2v12M2 8h12"/>
        </svg>
        New Chat
      </button>

      {/* Conversation search */}
      <div className="conversation-search">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="8"/>
          <path d="M21 21l-4.35-4.35"/>
        </svg>
        <input
          type="text"
          className="conversation-search-input"
          placeholder="Search conversations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button
            className="conversation-search-clear"
            onClick={() => setSearchQuery('')}
          >
            <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M2 2l8 8M10 2l-8 8"/>
            </svg>
          </button>
        )}
      </div>

      {/* Conversations list */}
      <div className="conversations-list" id="conversations-list">
        {groupedSessions.map((group) => (
          <div key={group.label}>
            <div className="session-date-group">{group.label}</div>
            {group.sessions.map((session) => {
              const rawStatus = session.status || 'idle';
              // Session number: position in full (unfiltered) list, newest = highest
              const fullIndex = sessions.indexOf(session);
              const sessionNumber = totalCount - fullIndex;
              const isActive = session.id === currentSessionId;
              const isRenaming = renamingId === session.id;

              // Derive visual status: running > compacting > error > active > idle
              let visualStatus: string = rawStatus;
              if (rawStatus === 'idle' && isActive) {
                visualStatus = 'active';
              }

              return (
                <div
                  key={session.id}
                  className={`conversation-item${isActive ? ' active' : ''}`}
                  onClick={() => handleSwitch(session.id)}
                  onContextMenu={(e) => handleContextMenu(session.id, session.title, e)}
                  data-id={session.id}
                >
                  <div
                    className={`conversation-status ${visualStatus}`}
                    title={getStatusTitle(visualStatus)}
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
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        startRename(session.id, session.title);
                      }}
                      title="Double-click to rename"
                    >
                      {session.title}
                    </span>
                  )}
                  <DelegationBadges convId={session.id} />
                  <button
                    className="delete-btn"
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

      {/* Conversation context menu (right-click) */}
      <ConversationContextMenu
        menu={contextMenu}
        onClose={closeContextMenu}
        onRename={handleContextRename}
        onDelete={handleContextDelete}
        onExport={handleContextExport}
      />

      {/* Sidebar footer */}
      <div className="sidebar-footer">
        <button className="settings-btn" onClick={handleOpenSettings}>
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="8" cy="8" r="3"/>
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2M2.9 2.9l1.4 1.4M11.7 11.7l1.4 1.4M2.9 13.1l1.4-1.4M11.7 4.3l1.4-1.4"/>
          </svg>
          Settings
        </button>
      </div>
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
