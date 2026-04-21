import { useState, useCallback, useEffect } from 'react';
import Header from './Header';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';
import ArtifactPanel from '@/components/ArtifactPanel/ArtifactPanel';
import DesignPanel from '@/components/DesignPanel/DesignPanel';
import PlanPanel from '@/components/PlanPanel/PlanPanel';
import DesignDashboard from '@/components/DesignPanel/DesignDashboard';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useTeamStore } from '@/stores/teamStore';
import { useArtifactStore } from '@/stores/artifactStore';
import { useDesignStore } from '@/stores/designStore';
import { usePlanStore } from '@/stores/planStore';
import { useModeStore } from '@/stores/modeStore';

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
          const result = await window.electronAPI.selectFolder();
          const folders = Array.isArray(result) ? result : result ? [result] : [];
          if (folders.length > 0) {
            const currentFolders = useSettingsStore.getState().workingFolders;
            const updatedFolders = [...currentFolders];
            for (const folder of folders) {
              if (!updatedFolders.includes(folder)) {
                updatedFolders.push(folder);
              }
            }
            useSettingsStore.setState({ workingFolders: updatedFolders });
            setWorkingDir(folders[0]);
          }
        }
        // Reset select to current value
        e.target.value = displayDir;
      } else if (value) {
        setWorkingDir(value);
        // Also update current session's workingDir (local + backend)
        if (currentSessionId) {
          useSessionStore.setState((state) => ({
            sessions: state.sessions.map((s) =>
              s.id === currentSessionId ? { ...s, workingDir: value } : s,
            ),
          }));
          useSessionStore.getState().updateSessionMetadata(currentSessionId, { workingDir: value });
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
          title={displayDir ? `Click to open in Finder: ${displayDir}` : 'Click to select working directory'}
          style={{
            cursor: 'pointer',
            ...(!displayDir ? { color: 'var(--text-tertiary)' } : {}),
          }}
          onClick={() => {
            if (displayDir && window.electronAPI?.openFolder) {
              window.electronAPI.openFolder(displayDir);
            }
          }}
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

// ==================== MainContent ====================

export default function MainContent() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);

  // Restore team panel and clear stale UI state when switching sessions
  useEffect(() => {
    // Restore todos and queue for the session (or clear if none saved)
    const savedTodos = currentSessionId
      ? useUIStore.getState().getSessionTodos(currentSessionId)
      : [];
    useUIStore.getState().setTodos(savedTodos);
    useUIStore.getState().switchSessionQueue(currentSessionId ?? null);

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

  // Save/restore artifact panel, design, plan, and mode state per session
  useEffect(() => {
    useArtifactStore.getState().switchSession(currentSessionId ?? null);
    useDesignStore.getState().switchSession(currentSessionId ?? null);
    usePlanStore.getState().switchSession(currentSessionId ?? null);
    useModeStore.getState().switchSession(currentSessionId ?? null);

    // Restore design versions from message history if switching to a design-mode
    // session with no in-memory snapshot (e.g. after app restart)
    if (currentSessionId) {
      const session = useSessionStore.getState().sessions.find(s => s.id === currentSessionId);
      if (session?.mode === 'design') {
        setTimeout(() => {
          const ds = useDesignStore.getState();
          if (ds.versions.length === 0) {
            const runtime = useChatStore.getState().runtimes[currentSessionId];
            if (runtime?.messages?.length) {
              ds.restoreFromMessages(runtime.messages);
            }
          }
        }, 300);
      }
    }
  }, [currentSessionId]);

  const designActive = useDesignStore((s) => s.active);
  const designVersionCount = useDesignStore((s) => s.versions.length);
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const hasMessages = useChatStore((s) => {
    if (!currentSessionId) return false;
    const rt = s.runtimes[currentSessionId];
    return rt ? rt.messages.length > 0 : false;
  });
  const showDesignDashboard = designActive && designVersionCount === 0 && !isStreaming && !hasMessages;

  return (
    <div className="main-content">
      <Header />
      {showDesignDashboard ? (
        <DesignDashboard />
      ) : (
        <>
          <div className="chat-panel-wrapper">
            <div className="chat-area">
              <ChatArea />
              <StatusBar />
            </div>
            <ArtifactPanel />
            <DesignPanel />
            <PlanPanel />
          </div>
          <MessageInput />
        </>
      )}
    </div>
  );
}
