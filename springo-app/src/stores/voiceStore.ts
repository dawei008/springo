import { create } from 'zustand';

const WS_BASE = 'ws://127.0.0.1:8081/v1/transcribe';

interface ElectronAPI {
  checkMicAccess?: () => Promise<boolean>;
}

interface VoiceState {
  isTranscribing: boolean;
  activeSessionId: string | null;
  partialText: string;
  transcripts: Record<string, string>;
  language: string;
  _ws: WebSocket | null;
  _streams: MediaStream[];
  _audioCtx: AudioContext | null;
  startTranscription: (sessionId: string) => Promise<void>;
  stopTranscription: () => void;
  clearTranscript: (sessionId: string) => void;
  setLanguage: (lang: string) => void;
  getTranscript: (sessionId: string) => string;
}

function appendError(sessionId: string, msg: string) {
  useVoiceStore.setState((s) => ({
    transcripts: {
      ...s.transcripts,
      [sessionId]: (s.transcripts[sessionId] || '') + `\n[${msg}]\n`,
    },
  }));
}


function getElectronAPI(): ElectronAPI | null {
  return (window as unknown as { electronAPI?: ElectronAPI }).electronAPI || null;
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  isTranscribing: false,
  activeSessionId: null,
  partialText: '',
  transcripts: {},
  language: 'auto',
  _ws: null,
  _streams: [],
  _audioCtx: null,

  setLanguage: (lang) => set({ language: lang }),
  getTranscript: (sessionId) => get().transcripts[sessionId] || '',

  clearTranscript: (sessionId) =>
    set((s) => {
      const next = { ...s.transcripts };
      delete next[sessionId];
      return { transcripts: next, partialText: '' };
    }),

  stopTranscription: () => {
    const { _audioCtx, _streams, _ws } = get();
    try { _audioCtx?.close(); } catch {}
    _streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    if (_ws && _ws.readyState <= WebSocket.OPEN) _ws.close();
    set({
      isTranscribing: false,
      partialText: '',
      _ws: null,
      _streams: [],
      _audioCtx: null,
    });
  },

  startTranscription: async (sessionId) => {
    const { language } = get();
    const api = getElectronAPI();

    // Step 1: Check macOS mic permission
    try {
      if (api?.checkMicAccess) {
        const granted = await api.checkMicAccess();
        if (!granted) {
          appendError(sessionId, 'Microphone permission denied.');
          return;
        }
      }
    } catch {}

    // Step 2: Get audio streams (system audio + microphone)
    const streams: MediaStream[] = [];

    // 2a: Try to get system audio via getDisplayMedia (uses setDisplayMediaRequestHandler in main process)
    let desktopStream: MediaStream | null = null;
    try {
      desktopStream = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        video: { width: 1, height: 1 }, // minimal video, we only want audio
      });
      // Stop video tracks — we only need audio (safe with getDisplayMedia, unlike desktopCapturer)
      desktopStream.getVideoTracks().forEach((t) => t.stop());
      const audioTracks = desktopStream.getAudioTracks();
      console.log('[voice] Display audio tracks:', audioTracks.length, audioTracks.map(t => `${t.label} (${t.readyState})`));
      if (audioTracks.length > 0) {
        streams.push(desktopStream);
        // Monitor track state
        audioTracks[0].onended = () => console.warn('[voice] Display audio track ended unexpectedly');
      } else {
        desktopStream = null;
      }
    } catch (err) {
      // Don't show error — just fall back to mic only
      console.warn('[voice] Display audio capture failed (will use mic only):', err);
    }

    // 2b: Get microphone stream
    let micStream: MediaStream | null = null;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streams.push(micStream);
    } catch (err) {
      // If we have desktop audio, mic failure is acceptable
      if (!desktopStream) {
        appendError(sessionId, `Mic error: ${err instanceof Error ? err.message : err}`);
        streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
        return;
      }
      console.warn('Mic capture failed, using desktop audio only:', err);
    }

    if (streams.length === 0) {
      appendError(sessionId, 'No audio source available.');
      return;
    }

    // Step 3: Connect WebSocket
    let ws: WebSocket;
    try {
      ws = new WebSocket(`${WS_BASE}?lang=${language}`);
      ws.binaryType = 'arraybuffer';
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error('WebSocket connection failed'));
        setTimeout(() => reject(new Error('WebSocket timeout')), 5000);
      });
    } catch (err: unknown) {
      streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
      appendError(sessionId, `Connection error: ${err instanceof Error ? err.message : err}`);
      return;
    }

    // Step 4: Message handler
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'transcript') {
          if (msg.is_partial) {
            set({ partialText: msg.text });
          } else {
            set((s) => {
              const prev = s.transcripts[sessionId] || '';
              // Add space between segments unless previous ends with newline or is empty
              const sep = prev && !prev.endsWith('\n') && !prev.endsWith(' ') ? ' ' : '';
              return {
                transcripts: {
                  ...s.transcripts,
                  [sessionId]: prev + sep + msg.text,
                },
                partialText: '',
              };
            });
          }
        } else if (msg.type === 'error') {
          appendError(sessionId, `Server: ${msg.message}`);
        }
      } catch {}
    };
    ws.onerror = () => { appendError(sessionId, 'WebSocket error'); get().stopTranscription(); };
    ws.onclose = () => set({ isTranscribing: false });

    // Step 5: Audio pipeline — native rate AudioContext, downsample in worklet to 16kHz
    // NOTE: AudioContext({sampleRate:16000}) does NOT work with desktopCapturer in Electron
    try {
      const audioCtx = new AudioContext(); // native rate (48kHz)
      const nativeRate = audioCtx.sampleRate;
      console.log(`[voice] AudioContext sampleRate: ${nativeRate}`);

      // Load AudioWorklet processor from file (does 48kHz→16kHz downsampling + 4096-sample buffering)
      await audioCtx.audioWorklet.addModule('./pcm-processor.js?v=' + Date.now());
      console.log('[voice] AudioWorklet module loaded successfully');

      // Mix all audio sources — boost system audio
      const mixGain = audioCtx.createGain();
      mixGain.gain.value = 1.0;

      for (const s of streams) {
        const audioTracks = s.getAudioTracks();
        if (audioTracks.length > 0) {
          const src = audioCtx.createMediaStreamSource(s);
          const label = audioTracks[0].label;
          const isSystemAudio = label.toLowerCase().includes('system') || s === desktopStream;
          if (isSystemAudio) {
            const boost = audioCtx.createGain();
            boost.gain.value = 15.0;
            src.connect(boost);
            boost.connect(mixGain);
            console.log(`[voice] Connected audio source: ${label} (boosted 15x)`);
          } else {
            src.connect(mixGain);
            console.log(`[voice] Connected audio source: ${label}`);
          }
        }
      }

      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-capture');
      mixGain.connect(workletNode);

      // Worklet outputs 4096 samples at 16kHz (~256ms) — convert Float32 to Int16 PCM
      workletNode.port.onmessage = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const float32: Float32Array = e.data;
        const pcm16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32768)));
        }
        ws.send(pcm16.buffer);
      };

      set({
        isTranscribing: true,
        activeSessionId: sessionId,
        _ws: ws,
        _streams: streams,
        _audioCtx: audioCtx,
      });
    } catch (err: unknown) {
      streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
      ws.close();
      appendError(sessionId, `Audio error: ${err instanceof Error ? err.message : err}`);
    }
  },
}));
