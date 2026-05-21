import { useEffect, useRef } from 'react';
import { useRecordingStore } from '@/stores/recordingStore';
import { useReplayStore } from '@/stores/replayStore';
import { useUIStore } from '@/stores/uiStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function RecordingCanvasPanel() {
  const isRecording = useRecordingStore((s) => s.isRecording);
  const isPaused = useRecordingStore((s) => s.isPaused);
  const elapsed = useRecordingStore((s) => s.elapsed);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const sourceMessageCount = useChatStore((s) =>
    currentSessionId ? s.runtimes[currentSessionId]?.messages.length ?? 0 : 0,
  );
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (isRecording && !isPaused) {
      timerRef.current = setInterval(() => {
        useRecordingStore.getState().tick();
      }, 1000);
    }
    return () => clearInterval(timerRef.current);
  }, [isRecording, isPaused]);

  const handlePauseResume = () => {
    if (isPaused) {
      useRecordingStore.getState().resumeRecording();
    } else {
      useRecordingStore.getState().pauseRecording();
    }
  };

  const handleStop = async () => {
    if (useReplayStore.getState().isReplaying) {
      useReplayStore.getState().stopReplay();
    }
    const path = await useRecordingStore.getState().stopRecording();
    if (path) {
      useUIStore.getState().showToast(`Recording saved: ${path}`, 'success');
    }
  };

  const handleStart = async () => {
    await useRecordingStore.getState().startRecording();
  };

  const handleReplayAndRecord = async () => {
    if (!currentSessionId || sourceMessageCount === 0) return;
    const sourceSessionId = currentSessionId;
    const ok = await useRecordingStore.getState().startRecording();
    if (!ok) {
      useUIStore.getState().showToast('Failed to start recording', 'error');
      return;
    }
    const replaySessionId = useSessionStore
      .getState()
      .createSession('Replay', 'recording');
    void useReplayStore
      .getState()
      .startReplay(sourceSessionId, replaySessionId);
  };

  if (!isRecording) {
    const canReplay = !!currentSessionId && sourceMessageCount > 0;
    return (
      <div className="recording-canvas-panel">
        <div className="recording-canvas-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <circle cx="12" cy="10" r="3" />
          </svg>
          <span>Recording stopped</span>
          <button className="recording-canvas-start-btn" onClick={handleStart}>
            Start Recording
          </button>
          <button
            className="recording-canvas-start-btn"
            onClick={handleReplayAndRecord}
            disabled={!canReplay}
            title={
              canReplay
                ? 'Replay current session messages with typing animation, while recording'
                : 'Open a session with messages to enable replay'
            }
          >
            Replay &amp; Record
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="recording-canvas-panel">
      <div className="recording-canvas-status">
        <span className={`recording-canvas-dot${isPaused ? ' paused' : ''}`} />
        <span className="recording-canvas-label">
          {isPaused ? 'Paused' : 'Recording'}
        </span>
      </div>
      <div className="recording-canvas-timer">{formatTime(elapsed)}</div>
      <div className="recording-canvas-controls">
        <button className="recording-canvas-btn" onClick={handlePauseResume} title={isPaused ? 'Resume' : 'Pause'}>
          {isPaused ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></svg>
          )}
          <span>{isPaused ? 'Resume' : 'Pause'}</span>
        </button>
        <button className="recording-canvas-btn recording-canvas-stop" onClick={handleStop} title="Stop recording">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
          <span>Stop</span>
        </button>
      </div>
    </div>
  );
}
