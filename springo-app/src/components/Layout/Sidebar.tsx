import { useState, useCallback, useRef, useEffect } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import type { ConversationStatus } from '@/types';

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

export default function Sidebar() {
  // ─── Session store ───
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);

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

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

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
      // In the legacy app, single-click opens file browser.
      // For now, select the folder as working dir.
      setWorkingDir(folder);
    },
    [setWorkingDir],
  );

  const handleFolderDoubleClick = useCallback((folder: string) => {
    if (window.electronAPI?.openFolder) {
      window.electronAPI.openFolder(folder);
    }
  }, []);

  const handleOpenSettings = useCallback(() => {
    setSettingsOpen(true);
  }, [setSettingsOpen]);

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
    <div className="sidebar">
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

      {/* New Chat button */}
      <button className="new-chat-btn" onClick={handleNewChat}>
        <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 2v12M2 8h12"/>
        </svg>
        New Chat
      </button>

      {/* Conversations list — flat, NO date grouping, NO search */}
      <div className="conversations-list" id="conversations-list">
        {sessions.map((session, index) => {
          const status = session.status || 'idle';
          const sessionNumber = totalCount - index;
          const isActive = session.id === currentSessionId;
          const isRenaming = renamingId === session.id;

          return (
            <div
              key={session.id}
              className={`conversation-item${isActive ? ' active' : ''}`}
              onClick={() => handleSwitch(session.id)}
              data-id={session.id}
            >
              <div
                className={`conversation-status ${status}`}
                title={getStatusTitle(status)}
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
                  onDoubleClick={(e) => startRename(session.id, session.title, e)}
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
                  <path d="M3 3l8 8M11 3l-8 8"/>
                </svg>
              </button>
            </div>
          );
        })}
      </div>

      {/* Sidebar footer with Settings button */}
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
