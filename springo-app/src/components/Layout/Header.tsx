import { useSessionStore } from '@/stores/sessionStore';
import { useUIStore } from '@/stores/uiStore';
import { useRecordingStore } from '@/stores/recordingStore';
import { useReplayStore } from '@/stores/replayStore';

export default function Header() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel);
  const rightPanelOpen = useUIStore((s) => s.rightPanelOpen);
  const isRecording = useRecordingStore((s) => s.isRecording);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );

  const headerTitle =
    currentSessionId && session?.title ? session.title : 'New Chat';

  const handleRecordToggle = async () => {
    if (isRecording) {
      // Stop: also stop replay if active
      if (useReplayStore.getState().isReplaying) {
        useReplayStore.getState().stopReplay();
      }
      const path = await useRecordingStore.getState().stopRecording();
      if (path) {
        useUIStore.getState().showToast(`Recording saved: ${path}`, 'success');
      }
    } else {
      // Start recording — check if replay mode is on
      let replayMode = false;
      try {
        const raw = await window.electronAPI?.cache?.get('recording') as Record<string, unknown> | null;
        if (raw) replayMode = raw.replayMode === true;
      } catch { /* ignore */ }

      if (replayMode && currentSessionId) {
        // Replay mode: start recording first, then create new session and replay into it
        const sourceSessionId = currentSessionId;
        const ok = await useRecordingStore.getState().startRecording();
        if (!ok) {
          useUIStore.getState().showToast('Failed to start recording', 'error');
          return;
        }
        const replaySessionId = useSessionStore.getState().createSession('Replay');
        useReplayStore.getState().startReplay(sourceSessionId, replaySessionId);
      } else {
        // Normal recording: just capture the window
        const ok = await useRecordingStore.getState().startRecording();
        if (!ok) {
          useUIStore.getState().showToast('Failed to start recording', 'error');
        }
      }
    }
  };

  return (
    <div className="header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          className="sidebar-toggle"
          onClick={toggleSidebar}
          title="Toggle sidebar"
        >
          <svg
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M3 6h12M3 12h12" />
          </svg>
        </button>
        <span className="header-title" id="header-title">
          {headerTitle}
        </span>
      </div>
      <div className="header-actions">
        <button
          className={`header-record-btn${isRecording ? ' recording' : ''}`}
          onClick={handleRecordToggle}
          title={isRecording ? 'Stop recording' : 'Start recording (Cmd+Shift+R)'}
        >
          {isRecording ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="8" />
              <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
            </svg>
          )}
        </button>
        <button
          className={`panel-toggle${rightPanelOpen ? ' active' : ''}`}
          id="right-panel-toggle"
          onClick={toggleRightPanel}
          title="Toggle panel"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M9 3v18" />
          </svg>
        </button>
      </div>
    </div>
  );
}
