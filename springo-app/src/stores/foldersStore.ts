/**
 * Folders store — thin client over /v1/folders.
 *
 * Mirrors the backend list (~/.springo/folders.json) and exposes optimistic
 * CRUD. Folder ↔ session is recorded on the session metadata via the existing
 * sessions PATCH endpoint, so deleting a folder here doesn't touch sessions —
 * sessionStore.detachFolder handles the cascade locally and the orphaned
 * folder_id on disk is harmless until the next session save replaces it.
 */
import { create } from 'zustand';

const BASE_URL = 'http://127.0.0.1:8081';

export interface Folder {
  id: string;
  name: string;
  createdAt: number;
}

interface FoldersState {
  folders: Folder[];
  loaded: boolean;

  loadFolders: () => Promise<void>;
  createFolder: (name: string) => Promise<Folder | null>;
  renameFolder: (id: string, name: string) => Promise<boolean>;
  deleteFolder: (id: string) => Promise<boolean>;
}

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = '';
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch { /* ignore */ }
    throw new Error(`${method} ${path} → ${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

export const useFoldersStore = create<FoldersState>((set, get) => ({
  folders: [],
  loaded: false,

  loadFolders: async () => {
    try {
      const r = await api<{ folders: Folder[] }>('GET', '/v1/folders');
      set({ folders: r.folders ?? [], loaded: true });
    } catch (e) {
      console.warn('[folders] loadFolders failed', (e as Error).message);
      set({ loaded: true });
    }
  },

  createFolder: async (name) => {
    try {
      const folder = await api<Folder>('POST', '/v1/folders', { name });
      set((s) => ({ folders: [...s.folders, folder] }));
      return folder;
    } catch (e) {
      console.warn('[folders] create failed', (e as Error).message);
      return null;
    }
  },

  renameFolder: async (id, name) => {
    const prev = get().folders;
    // Optimistic
    set((s) => ({ folders: s.folders.map((f) => (f.id === id ? { ...f, name } : f)) }));
    try {
      await api('PATCH', `/v1/folders/${id}`, { name });
      return true;
    } catch (e) {
      console.warn('[folders] rename failed, rolling back', (e as Error).message);
      set({ folders: prev });
      return false;
    }
  },

  deleteFolder: async (id) => {
    const prev = get().folders;
    set((s) => ({ folders: s.folders.filter((f) => f.id !== id) }));
    try {
      await api('DELETE', `/v1/folders/${id}`);
      return true;
    } catch (e) {
      console.warn('[folders] delete failed, rolling back', (e as Error).message);
      set({ folders: prev });
      return false;
    }
  },
}));

if (typeof window !== 'undefined') {
  void useFoldersStore.getState().loadFolders();
}
