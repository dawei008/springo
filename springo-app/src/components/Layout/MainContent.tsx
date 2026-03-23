import { useState, useCallback, useRef, useEffect } from 'react';
import Header from './Header';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useTeamStore } from '@/stores/teamStore';
import type { RightPanelTab, TodoItem } from '@/stores/uiStore';
import TeamPanel from '../RightPanel/TeamPanel';
import SchedulesPanel from '../RightPanel/SchedulesPanel';
import MeetingPanel from '../RightPanel/MeetingPanel';

// ==================== RightPanel Todo List ====================

function RightPanelTodoList({ todos }: { todos: TodoItem[] }) {
  const completedCount = todos.filter((t) => t.status === 'completed').length;

  return (
    <div className="panel-todo-list">
      <div className="panel-todo-header">
        <span className="panel-todo-progress">{completedCount}/{todos.length}</span>
      </div>
      {todos.map((todo) => {
        let statusIcon = '\u25CB'; // pending
        let statusClass = 'pending';
        if (todo.status === 'in_progress') {
          statusIcon = '\u25D4'; // in progress
          statusClass = 'in-progress';
        } else if (todo.status === 'completed') {
          statusIcon = '\u2713'; // done
          statusClass = 'completed';
        }
        return (
          <div key={todo.id} className={`panel-todo-item ${statusClass}`}>
            <span className="panel-todo-icon">{statusIcon}</span>
            <span className="panel-todo-subject">{todo.subject}</span>
          </div>
        );
      })}
    </div>
  );
}

// ==================== StatusBar ====================

function StatusBar() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );

  const workingDir = useSettingsStore((s) => s.workingDir);
  const workingFolders = useSettingsStore((s) => s.workingFolders);
  const setWorkingDir = useSettingsStore((s) => s.setWorkingDir);

  // Health polling state
  const [serverHealthy, setServerHealthy] = useState(false);
  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8081/health');
        const data = await res.json();
        if (mounted) setServerHealthy(data.status === 'healthy');
      } catch {
        if (mounted) setServerHealthy(false);
      }
    };
    checkHealth();
    // Fast checks during startup (3s), then slow (30s)
    const fastInterval = setInterval(() => {
      if (!serverHealthy) checkHealth();
    }, 3000);
    const slowInterval = setInterval(checkHealth, 30000);
    return () => {
      mounted = false;
      clearInterval(fastInterval);
      clearInterval(slowInterval);
    };
  }, [serverHealthy]);

  // Derive status from health + session + streaming state
  const status = !serverHealthy ? 'error' : isStreaming ? 'running' : session?.status || 'idle';

  // The display directory: prefer session's workingDir, fall back to global
  const displayDir = session?.workingDir || workingDir || '';

  const statusText: Record<string, string> = {
    idle: '\u25cf Ready',
    running: '\u25d0 Running...',
    completed: '\u2713 Completed',
    error: !serverHealthy ? '\u25d0 Connecting...' : '\u2715 Error',
    compacting: '\u25d0 Compacting...',
  };

  const statusClass: Record<string, string> = {
    idle: 'status-connected',
    running: 'status-running',
    completed: 'status-completed',
    error: !serverHealthy ? 'status-connecting' : 'status-error',
    compacting: 'status-running',
  };

  const handleWorkdirChange = useCallback(
    async (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value;
      if (value === '__add__') {
        // Use Electron dialog to add new folder
        if (window.electronAPI?.selectFolder) {
          const folders = await window.electronAPI.selectFolder();
          if (folders && folders.length > 0) {
            setWorkingDir(folders[0]);
          }
        }
        // Reset select to current value
        e.target.value = displayDir;
      } else if (value) {
        setWorkingDir(value);
        // Also update current session's workingDir
        if (currentSessionId) {
          useSessionStore.setState((state) => ({
            sessions: state.sessions.map((s) =>
              s.id === currentSessionId ? { ...s, workingDir: value } : s,
            ),
          }));
        }
      }
    },
    [displayDir, setWorkingDir, currentSessionId],
  );

  return (
    <div className="status-bar">
      <span id="status" className={statusClass[status] || ''}>
        {statusText[status] || '\u25cf Ready'}
      </span>
      <div className="status-workdir-area">
        <span
          className="workdir-path"
          id="workdir-path-display"
          title={displayDir || 'Click to select working directory'}
          style={
            !displayDir ? { color: 'var(--text-tertiary)' } : undefined
          }
        >
          {displayDir || '(No working directory)'}
        </span>
        <div className="status-workdir-selector">
          <svg
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
          <select
            id="status-workdir-select"
            value={displayDir}
            onChange={handleWorkdirChange}
          >
            {workingFolders.map((folder) => {
              const name = folder.split('/').pop() || folder;
              return (
                <option key={folder} value={folder} title={folder}>
                  {name}
                </option>
              );
            })}
            {workingFolders.length > 0 && (
              <option disabled>{'──────────'}</option>
            )}
            <option value="__add__">+ Add folder...</option>
          </select>
        </div>
      </div>
    </div>
  );
}

// ==================== RightPanel ====================

function RightPanel() {
  const rightPanelOpen = useUIStore((s) => s.rightPanelOpen);
  const rightPanelTab = useUIStore((s) => s.rightPanelTab);
  const setRightPanelTab = useUIStore((s) => s.setRightPanelTab);
  const todos = useUIStore((s) => s.todos);

  const panelRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  // Resize logic
  useEffect(() => {
    const resizeHandle = resizeRef.current;
    const panel = panelRef.current;
    if (!resizeHandle || !panel) return;

    let isResizing = false;
    let startX = 0;
    let startWidth = 0;

    const onMouseDown = (e: MouseEvent) => {
      isResizing = true;
      startX = e.clientX;
      startWidth = panel.offsetWidth;
      resizeHandle.classList.add('dragging');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const diff = startX - e.clientX;
      const maxW = Math.floor(window.innerWidth * 0.7);
      const newWidth = Math.min(maxW, Math.max(200, startWidth + diff));
      panel.style.width = newWidth + 'px';
    };

    const onMouseUp = () => {
      if (isResizing) {
        isResizing = false;
        resizeHandle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    resizeHandle.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);

    return () => {
      resizeHandle.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const tabs: { key: RightPanelTab; label: string }[] = [
    { key: 'tasks', label: 'Tasks' },
    { key: 'team', label: 'Team' },
    { key: 'schedules', label: 'Schedules' },
    { key: 'meeting', label: 'Meeting' },
  ];

  return (
    <div
      className={`right-panel${rightPanelOpen ? '' : ' hidden'}`}
      id="right-panel"
      ref={panelRef}
    >
      <div className="right-panel-resize" id="right-panel-resize" ref={resizeRef} />
      <div className="right-panel-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`right-panel-tab${rightPanelTab === tab.key ? ' active' : ''}`}
            data-tab={tab.key}
            onClick={() => setRightPanelTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="right-panel-content">
        {/* Tasks section */}
        <div
          className={`right-panel-section${rightPanelTab === 'tasks' ? ' active' : ''}`}
          id="panel-tasks"
        >
          <div className="panel-tasks-list" id="panel-tasks-list">
            {todos.length === 0 ? (
              <div className="panel-placeholder">
                <svg
                  width="32"
                  height="32"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  opacity="0.5"
                >
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
                <span>No background tasks</span>
              </div>
            ) : (
              <RightPanelTodoList todos={todos} />
            )}
          </div>
        </div>

        {/* Team section */}
        <div
          className={`right-panel-section${rightPanelTab === 'team' ? ' active' : ''}`}
          id="panel-team"
        >
          <TeamPanel />
        </div>

        {/* Schedules section */}
        <div
          className={`right-panel-section${rightPanelTab === 'schedules' ? ' active' : ''}`}
          id="panel-schedules"
        >
          <SchedulesPanel />
        </div>

        {/* Meeting section */}
        <div
          className={`right-panel-section${rightPanelTab === 'meeting' ? ' active' : ''}`}
          id="panel-meeting"
        >
          <MeetingPanel />
        </div>
      </div>
    </div>
  );
}

// ==================== MainContent ====================

export default function MainContent() {
  // Keyboard shortcut: Cmd/Ctrl + / to toggle right panel
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        toggleRightPanel();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [toggleRightPanel]);

  // Restore team panel and clear stale UI state when switching sessions
  useEffect(() => {
    // Restore todos for the session (or clear if none saved)
    const savedTodos = currentSessionId
      ? useUIStore.getState().getSessionTodos(currentSessionId)
      : [];
    useUIStore.getState().setTodos(savedTodos);

    if (!currentSessionId) {
      useTeamStore.getState().resetTeam();
      return;
    }
    const teamId = useUIStore.getState().getSessionTeam(currentSessionId);
    if (teamId) {
      // Load historical team data from backend API and restore team mode
      useTeamStore.getState().loadTeamFromAPI(teamId).then((loaded) => {
        if (loaded) {
          useUIStore.getState().setActiveTeamId(teamId);
          useUIStore.getState().setTeamModeEnabled(true);
        }
      });
    } else {
      // No team for this session — reset team state and disable team mode
      useTeamStore.getState().resetTeam();
      useUIStore.getState().setActiveTeamId(null);
      useUIStore.getState().setTeamModeEnabled(false);
    }
  }, [currentSessionId]);

  return (
    <div className="main-content">
      <Header />
      <div className="chat-panel-wrapper">
        <div className="chat-area">
          <ChatArea />
          <StatusBar />
        </div>
        <RightPanel />
      </div>
      <MessageInput />
    </div>
  );
}
