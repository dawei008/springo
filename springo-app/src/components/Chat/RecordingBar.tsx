import { useEffect, useRef } from 'react';
import { useRecordingStore } from '@/stores/recordingStore';
import { useReplayStore } from '@/stores/replayStore';
import { useUIStore } from '@/stores/uiStore';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function RecordingBar() {
  const isRecording = useRecordingStore((s) => s.isRecording);
  const isPaused = useRecordingStore((s) => s.isPaused);
  const elapsed = useRecordingStore((s) => s.elapsed);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Tick the elapsed timer
  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        useRecordingStore.getState().tick();
      }, 1000);
      return () => clearInterval(timerRef.current);
    }
  }, [isRecording]);

  if (!isRecording) return null;

  const handlePauseResume = () => {
    if (isPaused) {
      useRecordingStore.getState().resumeRecording();
    } else {
      useRecordingStore.getState().pauseRecording();
    }
  };

  const handleStop = async () => {
    // Stop replay first if running (so it doesn't keep injecting messages)
    if (useReplayStore.getState().isReplaying) {
      useReplayStore.getState().stopReplay();
    }
    const path = await useRecordingStore.getState().stopRecording();
    if (path) {
      useUIStore.getState().showToast(`Recording saved: ${path}`, 'success');
    }
  };

  return (
    <div className="recording-bar">
      <span className={`recording-dot${isPaused ? ' paused' : ''}`} />
      <span className="recording-label">
        {isPaused ? 'Paused' : 'Recording'}
      </span>
      <span className="recording-timer">{formatTime(elapsed)}</span>
      <button className="recording-btn" onClick={handlePauseResume} title={isPaused ? 'Resume' : 'Pause'}>
        {isPaused ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        )}
      </button>
      <button className="recording-btn recording-stop-btn" onClick={handleStop} title="Stop recording">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      </button>
    </div>
  );
}
