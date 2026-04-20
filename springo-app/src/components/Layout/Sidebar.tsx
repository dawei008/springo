import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import ToolsPanel from './ToolsPanel';

function getStatusTitle(visualStatus: string): string {
  const titles: Record<string, string> = {
    idle: 'Inactive',
    recent: 'Recent',
    current: 'Current session',
    running: 'Running...',
    completed: 'Completed',
    'completed-unseen': 'Completed (unread)',
    error: 'Error',
    compacting: 'Compacting...',
  };
  return titles[visualStatus] || 'Inactive';
}

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
  onClose,
  onRename,
  onExport,
  onCopyId,
}: {
  menu: ContextMenuState;
  onClose: () => void;
  onRename: () => void;
  onExport: () => void;
  onCopyId: () => void;
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

export default function Sidebar() {
  // ─── Session store ───
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);
  const unseenCompletedSessions = useSessionStore((s) => s.unseenCompletedSessions);
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

            if (newTitle && newTitle !== 'New Chat' && newTitle !== 'Untitled') {
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

  const handleAddFolder = useCallback(async () => {
    if (window.electronAPI?.selectFolder) {
      const result = await window.electronAPI.selectFolder();
      if (result) {
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
      if (e.detail > 1) return;
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

    const groups: { label: string; isToday?: boolean; sessions: typeof filteredSessions }[] = [
      { label: 'Today', isToday: true, sessions: [] },
      { label: 'Yesterday', sessions: [] },
      { label: 'Last 7 days', sessions: [] },
      { label: 'Older', sessions: [] },
    ];

    for (const session of filteredSessions) {
      const ts = session.updatedAt || session.createdAt || 0;
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
  let actualWorkdir = workingDir;
  if (currentSessionId) {
    const conv = sessions.find((s) => s.id === currentSessionId);
    if (conv?.workingDir) {
      actualWorkdir = conv.workingDir;
    }
  }

  const totalCount = sessions.length;

  return (
    <aside className={`sidebar${sidebarOpen ? '' : ' collapsed'}`}>
      {/* Sidebar header: dog logo + "Springo" + new chat button */}
      <div className="sidebar-header">
        <div className="brand-mark">
          <svg width="16" height="16" viewBox="0 0 100 100" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="50" cy="38" rx="22" ry="20"/>
            <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55"/>
            <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55"/>
            <circle cx="40" cy="35" r="3" fill="white"/>
            <circle cx="60" cy="35" r="3" fill="white"/>
            <ellipse cx="50" cy="48" rx="5" ry="4" fill="white"/>
            <path d="M45 52 Q50 58, 55 52"/>
          </svg>
        </div>
        <div className="brand-name">Springo</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
          <button className="icon-btn-sm" onClick={handleNewChat} title="New chat (⌘N)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>
      </div>

      {/* Search bar */}
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

      {/* Scrollable content */}
      <div className="sidebar-scroll">
        {/* Workspace section */}
        <div className="nav-section">
          <SectionHeader
            title="Workspace"
            collapsed={!!collapsed.workspace}
            onToggle={() => toggleSection('workspace')}
            onAdd={handleAddFolder}
          />
          {!collapsed.workspace && (
            <>
              {workingFolders.length === 0 ? (
                <div className="nav-empty-hint">Click + to add folders</div>
              ) : (
                workingFolders.map((folder, index) => {
                  const name = folder.split('/').pop() || folder;
                  const isActive = folder === actualWorkdir;
                  const isDefault = folder === defaultWorkingFolder;

                  return (
                    <div
                      key={folder}
                      className={`nav-item${isActive ? ' active' : ''}`}
                      draggable
                      onClick={(e) => handleFolderClick(folder, e)}
                      onDoubleClick={() => handleFolderDoubleClick(folder)}
                    >
                      <div className="nav-item-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
                        </svg>
                      </div>
                      <div className="nav-item-label" title={folder}>{name}</div>
                      {isDefault && <div className="nav-item-badge">default</div>}
                      {isActive && <div className="nav-item-status" />}
                      {!isDefault && (
                        <button
                          className="nav-item-remove"
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
            </>
          )}
        </div>

        {/* Skills & Tools section */}
        <div className="nav-section">
          <SectionHeader
            title="Skills & Tools"
            collapsed={!!collapsed.tools}
            onToggle={() => toggleSection('tools')}
          />
          {!collapsed.tools && <ToolsPanel />}
        </div>

        {/* Recent conversations */}
        <div className="nav-section">
          <SectionHeader
            title={`Conversations (${totalCount})`}
            collapsed={!!collapsed.conversations}
            onToggle={() => toggleSection('conversations')}
          />
          {!collapsed.conversations && (
            <div className="session-list">
              {groupedSessions.map((group) => (
                <div key={group.label}>
                  <div className="session-date-group">{group.label}</div>
                  {group.sessions.map((session) => {
                    const rawStatus = session.status || 'idle';
                    const fullIndex = sessions.indexOf(session);
                    const sessionNumber = totalCount - fullIndex;
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
                        <div
                          className={`conversation-status ${visualStatus}`}
                          title={getStatusTitle(visualStatus)}
                        />
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
                          <div className="session-meta">
                            <span className="session-number">#{sessionNumber}</span>
                          </div>
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
          )}
        </div>
      </div>

      {/* Conversation context menu */}
      <ConversationContextMenu
        menu={contextMenu}
        onClose={closeContextMenu}
        onRename={handleContextRename}
        onExport={handleContextExport}
        onCopyId={handleContextCopyId}
      />

      {/* Sidebar footer */}
      <div className="sidebar-footer">
        <button className="icon-btn-sm" onClick={handleOpenSettings} title="Settings">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <span className="sidebar-footer-label">Settings</span>
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
