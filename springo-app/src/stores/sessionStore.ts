import { create } from 'zustand';
import type {
  Conversation,
  ConversationStatus,
} from '@/types';
import { useSettingsStore } from '@/stores/settingsStore';

const BASE_URL = 'http://127.0.0.1:8081';

interface SessionState {
  sessions: Conversation[];
  currentSessionId: string | null;
  loading: boolean;

  loadSessions: (workingDir?: string) => Promise<void>;
  createSession: (title?: string) => string;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  updateSessionStatus: (id: string, status: ConversationStatus) => void;
  saveSession: (
    id: string,
    messages: unknown[],
    metadata?: Record<string, unknown>,
  ) => Promise<boolean>;
  updateSessionMetadata: (
    id: string,
    metadata: Record<string, unknown>,
  ) => Promise<boolean>;
  getSession: (id: string) => Conversation | undefined;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  loading: false,

  loadSessions: async (workingDir?: string) => {
    set({ loading: true });
    const maxAttempts = 30;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        // Health check first
        const healthRes = await fetch(`${BASE_URL}/health`);
        if (!healthRes.ok) throw new Error('Server not healthy');

        const url = workingDir
          ? `${BASE_URL}/v1/sessions?working_dir=${encodeURIComponent(workingDir)}`
          : `${BASE_URL}/v1/sessions`;

        const response = await fetch(url);
        if (!response.ok) throw new Error(`Sessions API returned ${response.status}`);

        const data = await response.json();
        const rawSessions = data.sessions || [];

        const sessions: Conversation[] = rawSessions
          .map((s: Record<string, unknown>) => {
            const meta = (s.metadata || {}) as Record<string, unknown>;
            const createdAt =
              (meta.createdAt as number) ||
              (s.createdAt as number) ||
              (s.modified ? new Date(s.modified as string).getTime() : Date.now());
            const updatedAt = s.modified
              ? new Date(s.modified as string).getTime()
              : createdAt;

            return {
              id: (s.session_id || s.id) as string,
              title: (meta.title || s.title || 'Untitled') as string,
              createdAt,
              updatedAt,
              status: 'idle' as ConversationStatus,
              workingDir: (meta.workingDir || s.workingDir || '') as string,
              isCustomTitle: (meta.isCustomTitle || false) as boolean,
              messages: [],
            };
          })
          .sort(
            (a: Conversation, b: Conversation) => b.createdAt - a.createdAt,
          );

        set({ sessions, loading: false });
        return;
      } catch (e) {
        console.warn(
          `[Sessions] Backend not ready (attempt ${attempt}/${maxAttempts}):`,
          (e as Error).message,
        );
        if (attempt < maxAttempts) {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    }

    console.error('[Sessions] Failed to load sessions after all retries');
    set({ loading: false });
  },

  createSession: (title?: string) => {
    // Use unique ID with random suffix to avoid collisions (matches legacy)
    const id =
      Date.now().toString() +
      '-' +
      Math.random().toString(36).substring(2, 11);
    // Use default working folder for new sessions
    const settings = useSettingsStore.getState();
    const defaultDir = settings.defaultWorkingFolder || settings.workingDir || '';
    const session: Conversation = {
      id,
      title: title || 'New Chat',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      status: 'idle',
      workingDir: defaultDir,
      isCustomTitle: !!title,
      messages: [],
    };

    set((state) => ({
      sessions: [session, ...state.sessions],
      currentSessionId: id,
    }));

    // Sync working dir to backend so tools use the correct directory
    if (defaultDir) {
      useSettingsStore.getState().setWorkingDir(defaultDir);
    }

    return id;
  },

  switchSession: (id: string) => {
    set({ currentSessionId: id });
  },

  deleteSession: async (id: string) => {
    try {
      const response = await fetch(`${BASE_URL}/v1/sessions/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        console.error('Failed to delete session:', response.status);
      }
    } catch (e) {
      console.error('SessionAPI.delete error:', e);
    }

    set((state) => {
      const sessions = state.sessions.filter((s) => s.id !== id);
      let currentSessionId = state.currentSessionId;

      if (state.currentSessionId === id) {
        if (sessions.length > 0) {
          currentSessionId = sessions[0].id;
        } else {
          // Legacy behavior: create a new session when deleting the last one
          const newId =
            Date.now().toString() +
            '-' +
            Math.random().toString(36).substring(2, 11);
          const newSession: Conversation = {
            id: newId,
            title: 'New Chat',
            createdAt: Date.now(),
            updatedAt: Date.now(),
            status: 'idle',
            workingDir: '',
            isCustomTitle: false,
            messages: [],
          };
          sessions.push(newSession);
          currentSessionId = newId;
        }
      }

      return { sessions, currentSessionId };
    });
  },

  renameSession: async (id: string, title: string) => {
    // Update local state immediately
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, title, isCustomTitle: true } : s,
      ),
    }));

    // Persist to backend
    try {
      await fetch(`${BASE_URL}/v1/sessions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metadata: { title, isCustomTitle: true } }),
      });
    } catch (e) {
      console.error('SessionAPI.updateMetadata error:', e);
    }
  },

  updateSessionStatus: (id: string, status: ConversationStatus) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, status, updatedAt: Date.now() } : s,
      ),
    }));
  },

  saveSession: async (
    id: string,
    messages: unknown[],
    metadata: Record<string, unknown> = {},
  ) => {
    try {
      const response = await fetch(`${BASE_URL}/v1/sessions/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, metadata }),
      });
      return response.ok;
    } catch (e) {
      console.error('SessionAPI.save error:', e);
      return false;
    }
  },

  updateSessionMetadata: async (
    id: string,
    metadata: Record<string, unknown>,
  ) => {
    try {
      const response = await fetch(`${BASE_URL}/v1/sessions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metadata }),
      });
      return response.ok;
    } catch (e) {
      console.error('SessionAPI.updateMetadata error:', e);
      return false;
    }
  },

  getSession: (id: string) => {
    return get().sessions.find((s) => s.id === id);
  },
}));
