import { useEffect, useRef, useState, useCallback } from 'react';
import { useRecordingStore } from '@/stores/recordingStore';
import { useReplayStore } from '@/stores/replayStore';
import { useUIStore } from '@/stores/uiStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';

const BASE_URL = 'http://127.0.0.1:8081';

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
        <RecordingSettings />
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

// ─── Recording settings (moved here from SettingsModal) ────────────────
//
// Configuration belongs next to the feature. The Settings modal kept these
// in a Recording subsection that nobody discovered until they were
// already deep in the app — and even then, you had to open Settings to
// change "where do my recordings go?". Now they live one collapse-toggle
// below the Start button.

function RecordingSettings() {
  const [open, setOpen] = useState(false);
  const [recordTarget, setRecordTarget] = useState<'window' | 'screen' | 'screen-ext'>('window');
  const [recordingDir, setRecordingDir] = useState('~/.springo/recordings');
  const [replayMode, setReplayMode] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [typingAnimation, setTypingAnimation] = useState(true);
  const loadedRef = useRef(false);

  // Load once when first expanded — don't pay the IPC cost if the user
  // never opens settings.
  useEffect(() => {
    if (!open || loadedRef.current) return;
    loadedRef.current = true;
    void (async () => {
      try {
        const raw = (await window.electronAPI?.cache?.get('recording')) as Record<string, unknown> | null;
        if (raw) {
          setRecordTarget((raw.recordTarget as 'window' | 'screen' | 'screen-ext') || 'window');
          setRecordingDir((raw.outputDir as string) || '~/.springo/recordings');
          setReplayMode(raw.replayMode === true);
          setReplaySpeed((raw.replaySpeed as number) || 1);
          setTypingAnimation(raw.typingAnimation !== false);
        }
      } catch (e) {
        console.warn('[recording-settings] load failed', e);
      }
    })();
  }, [open]);

  const save = useCallback(async (partial: Record<string, unknown>) => {
    try {
      const raw = ((await window.electronAPI?.cache?.get('recording')) as Record<string, unknown>) || {};
      await window.electronAPI?.cache?.set('recording', { ...raw, ...partial });
    } catch (e) {
      console.warn('[recording-settings] save failed', e);
    }
  }, []);

  const browseDir = useCallback(async () => {
    if (!window.electronAPI?.recording) return;
    const dir = await window.electronAPI.recording.selectDir();
    if (dir) {
      setRecordingDir(dir);
      void save({ outputDir: dir });
    }
  }, [save]);

  return (
    <div className="recording-settings">
      <button
        className="recording-settings-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}>
          <path d="m9 6 6 6-6 6" />
        </svg>
        Recording settings
      </button>

      {open && (
        <div className="recording-settings-body">
          <div className="hint" style={{ marginBottom: 10 }}>
            Use <kbd className="recording-settings-kbd">Cmd+Shift+R</kbd> or the button above to start. These settings persist locally.
          </div>

          <div className="setting-group">
            <label>Record Target</label>
            <select
              value={recordTarget}
              onChange={(e) => {
                const v = e.target.value as 'window' | 'screen' | 'screen-ext';
                setRecordTarget(v);
                void save({ recordTarget: v });
              }}
            >
              <option value="window">Springo Window</option>
              <option value="screen">Current Screen</option>
              <option value="screen-ext">Extended Screen</option>
            </select>
          </div>

          <div className="setting-group">
            <label>Output Directory</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="text"
                placeholder="~/.springo/recordings"
                style={{ flex: 1 }}
                value={recordingDir}
                onChange={(e) => {
                  setRecordingDir(e.target.value);
                  void save({ outputDir: e.target.value });
                }}
              />
              <button onClick={browseDir} className="browse-btn" title="Browse…">
                <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
              </button>
            </div>
            <div className="hint">Where video files are saved</div>
          </div>

          <div className="setting-group">
            <label className="setting-checkbox-label">
              <input
                type="checkbox"
                checked={replayMode}
                onChange={(e) => {
                  setReplayMode(e.target.checked);
                  void save({ replayMode: e.target.checked });
                }}
              />
              <span>Replay Mode</span>
            </label>
            <div className="hint" style={{ marginTop: -4 }}>
              When enabled, starting a recording replays the current session with typing animation and auto-stops when complete.
            </div>
          </div>

          {replayMode && (
            <>
              <div className="setting-group">
                <label>Replay Speed</label>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <input
                    type="range"
                    min={1}
                    max={8}
                    step={1}
                    value={replaySpeed}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setReplaySpeed(v);
                      void save({ replaySpeed: v });
                    }}
                    style={{ flex: 1 }}
                  />
                  <span style={{ minWidth: 30, textAlign: 'right', fontSize: 13, fontFamily: 'var(--font-mono, monospace)' }}>{replaySpeed}x</span>
                </div>
              </div>
              <div className="setting-group">
                <label className="setting-checkbox-label">
                  <input
                    type="checkbox"
                    checked={typingAnimation}
                    onChange={(e) => {
                      setTypingAnimation(e.target.checked);
                      void save({ typingAnimation: e.target.checked });
                    }}
                  />
                  <span>Typing Animation</span>
                  <span className="hint" style={{ marginLeft: 4 }}> — AI replies appear character-by-character</span>
                </label>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
