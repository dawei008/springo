import { useState, useCallback, useRef, useEffect } from 'react';
import Header from './Header';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import type { RightPanelTab } from '@/stores/uiStore';

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
        // Sync to server
        try {
          await fetch('http://127.0.0.1:8081/v1/config/working-dir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ working_dir: value }),
          });
        } catch (err) {
          console.warn('Failed to sync working directory:', err);
        }
      }
    },
    [displayDir, setWorkingDir],
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
    { key: 'news', label: 'News' },
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
          </div>
        </div>

        {/* Team section */}
        <div
          className={`right-panel-section${rightPanelTab === 'team' ? ' active' : ''}`}
          id="panel-team"
        >
          <div className="team-split-panel" id="team-split-panel">
            <div className="team-split-placeholder" id="team-split-placeholder">
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                opacity="0.5"
              >
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              <span>No active team</span>
              <span className="panel-placeholder-hint">
                Enable Team Mode and send a request to see agent progress here
              </span>
            </div>
            <div
              className="team-split-content"
              id="team-split-content"
              style={{ display: 'none' }}
            >
              <div className="team-split-header" id="team-split-header">
                <div className="team-split-status-row">
                  <span className="team-split-status-badge" id="team-split-status-badge">
                    idle
                  </span>
                  <span
                    className="team-split-request-preview"
                    id="team-split-request-preview"
                  />
                  <button
                    id="team-stop-btn"
                    className="team-stop-btn"
                    style={{ display: 'none' }}
                    title="Stop team execution"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="4" y="4" width="16" height="16" rx="2" />
                    </svg>
                    Stop
                  </button>
                </div>
              </div>
              <div className="team-split-agents" id="team-split-agents" />
            </div>
          </div>
        </div>

        {/* Schedules section */}
        <div
          className={`right-panel-section${rightPanelTab === 'schedules' ? ' active' : ''}`}
          id="panel-schedules"
        >
          <div className="panel-schedules-list" id="panel-schedules-list">
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
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <span>No scheduled tasks</span>
              <span className="panel-placeholder-hint">
                Ask Claude to create reminders or scheduled tasks
              </span>
            </div>
          </div>
        </div>

        {/* News section */}
        <div
          className={`right-panel-section${rightPanelTab === 'news' ? ' active' : ''}`}
          id="panel-news"
        >
          <div className="news-header">
            <span className="news-title">For You</span>
            <button className="news-refresh-btn" title="Refresh">
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path
                  d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 .79-.15 1.56-.44 2.25l1.52 1.52C19.68 14.62 20 13.35 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-.79.15-1.56.44-2.25L4.92 8.23C4.32 9.38 4 10.65 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
                  fill="currentColor"
                />
              </svg>
            </button>
          </div>
          <div className="news-interests" id="news-interests">
            <div className="news-interests-label">Your Interests</div>
            <div className="news-interests-tags" id="news-interests-tags">
              <span className="news-interest-hint">
                Say &quot;&#25105;&#20851;&#27880;...&quot; in chat to add interests
              </span>
            </div>
          </div>
          <div className="news-updated" id="news-updated" />
          <div id="panel-news-list">
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
                <path d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 12h10" />
              </svg>
              <span>Loading news...</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==================== MainContent ====================

export default function MainContent() {
  // Keyboard shortcut: Cmd/Ctrl + / to toggle right panel
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel);

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
