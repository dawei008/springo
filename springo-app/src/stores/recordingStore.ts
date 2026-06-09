import { create } from 'zustand';

interface RecordingState {
  isRecording: boolean;
  isPaused: boolean;
  startTime: number | null;
  elapsed: number; // seconds
  mediaRecorder: MediaRecorder | null;
  stream: MediaStream | null;
  chunks: Blob[];
  /** Absolute path of the most recent successful save. Persists across reloads. */
  lastSavedPath: string | null;
  /** Timestamp (ms) of the most recent save. */
  lastSavedAt: number | null;

  // Actions
  startRecording: () => Promise<boolean>;
  stopRecording: () => Promise<string | null>;
  pauseRecording: () => void;
  resumeRecording: () => void;
  tick: () => void;
  reset: () => void;
  clearLastSaved: () => void;
}

const LAST_SAVED_KEY = 'springo-recording-last-saved';

function readLastSaved(): { path: string | null; at: number | null } {
  try {
    const raw = localStorage.getItem(LAST_SAVED_KEY);
    if (!raw) return { path: null, at: null };
    const parsed = JSON.parse(raw);
    return { path: parsed.path ?? null, at: parsed.at ?? null };
  } catch {
    return { path: null, at: null };
  }
}

function writeLastSaved(path: string | null, at: number | null): void {
  try {
    if (path) {
      localStorage.setItem(LAST_SAVED_KEY, JSON.stringify({ path, at }));
    } else {
      localStorage.removeItem(LAST_SAVED_KEY);
    }
  } catch { /* ignore quota */ }
}

export const useRecordingStore = create<RecordingState>()((set, get) => {
  const initial = readLastSaved();
  return {
  isRecording: false,
  isPaused: false,
  startTime: null,
  elapsed: 0,
  mediaRecorder: null,
  stream: null,
  chunks: [],
  lastSavedPath: initial.path,
  lastSavedAt: initial.at,

  startRecording: async () => {
    try {
      // Read recording target from settings cache
      let target: string = 'window';
      try {
        const raw = await window.electronAPI?.cache?.get('recording') as Record<string, unknown> | null;
        if (raw?.recordTarget) target = raw.recordTarget as string;
      } catch { /* ignore */ }

      const source = await window.electronAPI?.recording?.getSource(target as 'window' | 'screen');
      if (!source) {
        console.error(`[Recording] Could not find ${target} source`);
        return false;
      }

      // Request the media stream using desktopCapturer source
      const stream = await (navigator.mediaDevices as unknown as {
        getUserMedia: (constraints: unknown) => Promise<MediaStream>;
      }).getUserMedia({
        audio: false,
        video: {
          mandatory: {
            chromeMediaSource: 'desktop',
            chromeMediaSourceId: source.id,
          },
        },
      });

      const chunks: Blob[] = [];
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'video/webm;codecs=vp9',
      });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorder.start(1000); // collect data every second

      set({
        isRecording: true,
        isPaused: false,
        startTime: Date.now(),
        elapsed: 0,
        mediaRecorder,
        stream,
        chunks,
      });

      return true;
    } catch (err) {
      console.error('[Recording] Failed to start:', err);
      return false;
    }
  },

  stopRecording: async () => {
    const { mediaRecorder, stream, chunks } = get();
    if (!mediaRecorder) return null;

    return new Promise<string | null>((resolve) => {
      mediaRecorder.onstop = async () => {
        // Stop all tracks
        stream?.getTracks().forEach((t) => t.stop());

        // Build the final blob
        const blob = new Blob(chunks, { type: 'video/webm' });
        const buffer = await blob.arrayBuffer();
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `springo-${timestamp}.webm`;

        // Save via IPC
        let savedPath: string | null = null;
        try {
          savedPath = await window.electronAPI?.recording?.save(
            buffer,
            filename,
          ) ?? null;
        } catch (err) {
          console.error('[Recording] Failed to save:', err);
        }

        const now = Date.now();
        if (savedPath) {
          // Persist so the panel can show "open last recording" across reloads.
          writeLastSaved(savedPath, now);
        }
        set({
          isRecording: false,
          isPaused: false,
          startTime: null,
          elapsed: 0,
          mediaRecorder: null,
          stream: null,
          chunks: [],
          lastSavedPath: savedPath ?? get().lastSavedPath,
          lastSavedAt: savedPath ? now : get().lastSavedAt,
        });

        resolve(savedPath);
      };

      mediaRecorder.stop();
    });
  },

  pauseRecording: () => {
    const { mediaRecorder } = get();
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.pause();
      set({ isPaused: true });
    }
  },

  resumeRecording: () => {
    const { mediaRecorder } = get();
    if (mediaRecorder && mediaRecorder.state === 'paused') {
      mediaRecorder.resume();
      set({ isPaused: false });
    }
  },

  tick: () => {
    const { startTime, isPaused } = get();
    if (startTime && !isPaused) {
      set({ elapsed: Math.floor((Date.now() - startTime) / 1000) });
    }
  },

  reset: () => {
    const { stream, mediaRecorder } = get();
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    stream?.getTracks().forEach((t) => t.stop());
    set({
      isRecording: false,
      isPaused: false,
      startTime: null,
      elapsed: 0,
      mediaRecorder: null,
      stream: null,
      chunks: [],
    });
  },

  clearLastSaved: () => {
    writeLastSaved(null, null);
    set({ lastSavedPath: null, lastSavedAt: null });
  },
  };
});
