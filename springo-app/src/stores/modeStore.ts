import { create } from 'zustand';
import type { SessionMode } from '@/types';
import { useDesignStore } from './designStore';
import { useUIStore } from './uiStore';
import { useArtifactStore, createArtifactId } from './artifactStore';
import { useSessionStore } from './sessionStore';

const BASE_URL = 'http://127.0.0.1:8081';

interface ModeState {
  activeMode: SessionMode;
  sessionModeMap: Record<string, SessionMode>;
  currentSessionId: string | null;

  switchMode: (mode: SessionMode) => void;
  switchSession: (sessionId: string | null) => void;
  getSessionMode: (sessionId: string) => SessionMode;
  hydrateFromSessions: () => void;
}

function deactivateAllModes() {
  useDesignStore.getState().deactivateDesignMode();
  useUIStore.getState().setPlanModeActive(false);
  const artifact = useArtifactStore.getState().activeArtifact;
  if (artifact?.componentId === 'team' || artifact?.componentId === 'plan' || artifact?.componentId === 'recording') {
    useArtifactStore.getState().closePanel();
  }
}

function activateMode(mode: SessionMode) {
  deactivateAllModes();

  switch (mode) {
    case 'design':
      useDesignStore.getState().activateDesignMode();
      break;
    case 'plan':
      useUIStore.getState().setPlanModeActive(true);
      useArtifactStore.getState().openArtifact({
        id: createArtifactId(),
        type: 'component',
        title: 'Plan',
        content: '',
        componentId: 'plan',
        timestamp: Date.now(),
      });
      break;
    case 'team':
      useArtifactStore.getState().openArtifact({
        id: createArtifactId(),
        type: 'component',
        title: 'Team',
        content: '',
        componentId: 'team',
        timestamp: Date.now(),
      });
      break;
  }
}

export const useModeStore = create<ModeState>((set, get) => ({
  activeMode: 'general',
  sessionModeMap: {},
  currentSessionId: null,

  switchMode: (mode) => {
    const currentMode = get().activeMode;

    if (mode === currentMode && mode !== 'general') {
      mode = 'general';
    }

    set({ activeMode: mode });
    activateMode(mode);

    const sessionId = get().currentSessionId;
    if (sessionId) {
      set((state) => ({
        sessionModeMap: { ...state.sessionModeMap, [sessionId]: mode },
      }));

      useSessionStore.setState((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId ? { ...sess, mode } : sess,
        ),
      }));

      fetch(`${BASE_URL}/v1/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metadata: { session_mode: mode } }),
      }).catch(() => {});
    }
  },

  switchSession: (sessionId) => {
    const { activeMode, sessionModeMap, currentSessionId: oldSessionId } = get();

    // Save current mode for the session we're leaving
    if (oldSessionId) {
      set((state) => ({
        sessionModeMap: { ...state.sessionModeMap, [oldSessionId]: activeMode },
      }));
    }

    // Restore mode for new session — check map, then session store, default to 'general'
    let restored: SessionMode = 'general';
    if (sessionId) {
      restored = sessionModeMap[sessionId]
        ?? useSessionStore.getState().sessions.find((s) => s.id === sessionId)?.mode
        ?? 'general';
    }
    set({ activeMode: restored, currentSessionId: sessionId });
    activateMode(restored);
  },

  getSessionMode: (sessionId) => {
    return get().sessionModeMap[sessionId] ?? 'general';
  },

  hydrateFromSessions: () => {
    const sessions = useSessionStore.getState().sessions;
    const map: Record<string, SessionMode> = {};
    for (const s of sessions) {
      if (s.mode && s.mode !== 'general') {
        map[s.id] = s.mode;
      }
    }
    set((state) => ({
      sessionModeMap: { ...map, ...state.sessionModeMap },
    }));
  },
}));
