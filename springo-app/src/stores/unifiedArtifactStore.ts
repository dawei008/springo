/**
 * Unified Artifact Store
 *
 * Manages all artifacts (apps, components, documents, templates)
 * with per-session state, version history, and pinning.
 *
 * This will eventually replace designStore, novelStore, modeStore,
 * and the old artifactStore. For now it lives alongside them.
 */
import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type UnifiedArtifactType = 'app' | 'component' | 'document' | 'template';

export interface ArtifactFile {
  path: string;
  type: 'html' | 'jsx' | 'css' | 'json' | 'text';
  content: string;
}

export interface ArtifactVersion {
  id: string;
  files: ArtifactFile[];
  state: Record<string, unknown>;
  title: string;
  timestamp: number;
}

export interface Artifact {
  id: string;
  name: string;
  icon: string;
  type: UnifiedArtifactType;
  files: ArtifactFile[];
  state: Record<string, unknown>;
  versions: ArtifactVersion[];
  activeVersionIndex: number;
  createdAt: number;
  updatedAt: number;
  sessionId?: string;
  pinned: boolean;
}

export interface PinnedElement {
  componentName: string;
  cssPath: string;
  tagName: string;
  className?: string;
  id?: string;
}

// ---------------------------------------------------------------------------
// Store state
// ---------------------------------------------------------------------------

interface SessionSnapshot {
  activeArtifactId: string | null;
  sessionArtifactIds: string[];
}

export interface UnifiedArtifactState {
  artifacts: Record<string, Artifact>;
  activeArtifactId: string | null;
  sessionArtifactIds: string[];
  pinnedArtifactIds: string[];
  pinnedElement: PinnedElement | null;
  sessionMap: Record<string, SessionSnapshot>;
  currentSessionId: string | null;

  // Artifact CRUD
  createArtifact: (props: {
    id?: string;
    name: string;
    icon?: string;
    type?: UnifiedArtifactType;
    files: ArtifactFile[];
    state?: Record<string, unknown>;
  }) => string;
  openArtifact: (id: string) => void;
  closeArtifact: () => void;
  deleteArtifact: (id: string) => void;

  // Code updates
  applyPatch: (id: string, filePatches: Array<{
    path: string;
    action: 'replace' | 'create' | 'delete';
    content: string;
    fileType: string;
  }>) => void;
  updateFiles: (id: string, files: ArtifactFile[]) => void;

  // State updates
  updateState: (id: string, state: Record<string, unknown>) => void;
  replaceState: (id: string, state: Record<string, unknown>) => void;

  // Version management
  selectVersion: (id: string, versionIndex: number) => void;
  currentVersion: (id: string) => ArtifactVersion | null;

  // Pinning
  pinArtifact: (id: string) => void;
  unpinArtifact: (id: string) => void;

  // Element pinning (canvas interaction)
  pinElement: (el: PinnedElement | null) => void;
  clearPin: () => void;

  // Session management
  switchSession: (sessionId: string | null) => void;

  // Persistence
  persistToStorage: () => void;
  loadFromStorage: () => void;

  // Selectors
  activeArtifact: () => Artifact | null;
  pinnedArtifacts: () => Artifact[];
  sessionArtifacts: () => Artifact[];
}

// ---------------------------------------------------------------------------
// localStorage bootstrap
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'springo-unified-artifacts';

let _persistTimer: ReturnType<typeof setTimeout> | null = null;
function debouncedPersist() {
  if (_persistTimer) clearTimeout(_persistTimer);
  _persistTimer = setTimeout(() => {
    useUnifiedArtifactStore.getState().persistToStorage();
  }, 500);
}

const loaded = (() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { artifacts: {} as Record<string, Artifact>, pinnedIds: [] as string[] };
    const data = JSON.parse(raw);
    return {
      artifacts: (data.artifacts || {}) as Record<string, Artifact>,
      pinnedIds: (data.pinnedArtifactIds || []) as string[],
    };
  } catch {
    return { artifacts: {} as Record<string, Artifact>, pinnedIds: [] as string[] };
  }
})();

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useUnifiedArtifactStore = create<UnifiedArtifactState>((set, get) => ({
  artifacts: loaded.artifacts,
  activeArtifactId: null,
  sessionArtifactIds: [],
  pinnedArtifactIds: loaded.pinnedIds,
  pinnedElement: null,
  sessionMap: {},
  currentSessionId: null,

  // ---- Artifact CRUD -------------------------------------------------------

  createArtifact: (props) => {
    const now = Date.now();
    const id = props.id ?? `art-${now}-${Math.random().toString(36).slice(2, 8)}`;
    const state = props.state ?? {};
    const files = props.files;

    const initialVersion: ArtifactVersion = {
      id: `${id}-v0`,
      files: [...files],
      state: { ...state },
      title: props.name,
      timestamp: now,
    };

    const artifact: Artifact = {
      id,
      name: props.name,
      icon: props.icon ?? (props.type ?? 'app'),
      type: props.type ?? 'app',
      files,
      state,
      versions: [initialVersion],
      activeVersionIndex: 0,
      createdAt: now,
      updatedAt: now,
      pinned: false,
    };

    set((s) => ({
      artifacts: { ...s.artifacts, [id]: artifact },
      activeArtifactId: id,
      sessionArtifactIds: [...s.sessionArtifactIds, id],
    }));

    debouncedPersist();
    return id;
  },

  openArtifact: (id) => {
    set((s) => {
      const inSession = s.sessionArtifactIds.includes(id);
      return {
        activeArtifactId: id,
        sessionArtifactIds: inSession ? s.sessionArtifactIds : [...s.sessionArtifactIds, id],
      };
    });
  },

  closeArtifact: () => {
    set({ activeArtifactId: null, pinnedElement: null });
  },

  deleteArtifact: (id) => {
    set((s) => {
      const { [id]: _, ...rest } = s.artifacts;
      return {
        artifacts: rest,
        activeArtifactId: s.activeArtifactId === id ? null : s.activeArtifactId,
        sessionArtifactIds: s.sessionArtifactIds.filter((i) => i !== id),
        pinnedArtifactIds: s.pinnedArtifactIds.filter((i) => i !== id),
      };
    });
    debouncedPersist();
  },

  // ---- Code updates --------------------------------------------------------

  applyPatch: (id, filePatches) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    const files = [...artifact.files.map((f) => ({ ...f }))];

    for (const patch of filePatches) {
      switch (patch.action) {
        case 'replace': {
          const idx = files.findIndex((f) => f.path === patch.path);
          if (idx !== -1) {
            files[idx] = { ...files[idx], content: patch.content };
          } else {
            files.push({ path: patch.path, type: patch.fileType as ArtifactFile['type'], content: patch.content });
          }
          break;
        }
        case 'create': {
          files.push({ path: patch.path, type: patch.fileType as ArtifactFile['type'], content: patch.content });
          break;
        }
        case 'delete': {
          const delIdx = files.findIndex((f) => f.path === patch.path);
          if (delIdx !== -1) files.splice(delIdx, 1);
          break;
        }
      }
    }

    const now = Date.now();
    const newVersion: ArtifactVersion = {
      id: `${id}-v${artifact.versions.length}`,
      files: files.map((f) => ({ ...f })),
      state: { ...artifact.state },
      title: artifact.name,
      timestamp: now,
    };

    const versions = [...artifact.versions, newVersion];

    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: {
          ...artifact,
          files,
          versions,
          activeVersionIndex: versions.length - 1,
          updatedAt: now,
        },
      },
    }));

    debouncedPersist();
  },

  updateFiles: (id, files) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    const now = Date.now();
    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: { ...artifact, files, updatedAt: now },
      },
    }));
  },

  // ---- State updates -------------------------------------------------------

  updateState: (id, newState) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    const merged = { ...artifact.state, ...newState };
    const now = Date.now();

    const versions = [...artifact.versions];
    if (versions.length > 0) {
      const vi = artifact.activeVersionIndex;
      versions[vi] = { ...versions[vi], state: { ...merged } };
    }

    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: { ...artifact, state: merged, versions, updatedAt: now },
      },
    }));

    debouncedPersist();
  },

  replaceState: (id, newState) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    const versions = [...artifact.versions];
    if (versions.length > 0) {
      const vi = artifact.activeVersionIndex;
      versions[vi] = { ...versions[vi], state: { ...newState } };
    }

    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: { ...artifact, state: newState, versions },
      },
    }));

    debouncedPersist();
  },

  // ---- Version management --------------------------------------------------

  selectVersion: (id, versionIndex) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;
    if (versionIndex < 0 || versionIndex >= artifact.versions.length) return;

    const version = artifact.versions[versionIndex];

    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: {
          ...artifact,
          activeVersionIndex: versionIndex,
          files: version.files.map((f) => ({ ...f })),
          state: { ...version.state },
        },
      },
    }));
  },

  currentVersion: (id) => {
    const artifact = get().artifacts[id];
    if (!artifact) return null;
    const { versions, activeVersionIndex } = artifact;
    if (activeVersionIndex >= 0 && activeVersionIndex < versions.length) {
      return versions[activeVersionIndex];
    }
    return null;
  },

  // ---- Pinning -------------------------------------------------------------

  pinArtifact: (id) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    set((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...artifact, pinned: true } },
      pinnedArtifactIds: s.pinnedArtifactIds.includes(id)
        ? s.pinnedArtifactIds
        : [...s.pinnedArtifactIds, id],
    }));

    debouncedPersist();
  },

  unpinArtifact: (id) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    set((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...artifact, pinned: false } },
      pinnedArtifactIds: s.pinnedArtifactIds.filter((i) => i !== id),
    }));

    debouncedPersist();
  },

  // ---- Element pinning -----------------------------------------------------

  pinElement: (el) => set({ pinnedElement: el }),

  clearPin: () => set({ pinnedElement: null }),

  // ---- Session management --------------------------------------------------

  switchSession: (sessionId) => {
    const { currentSessionId, activeArtifactId, sessionArtifactIds, sessionMap } = get();

    const updatedMap = { ...sessionMap };
    if (currentSessionId) {
      updatedMap[currentSessionId] = { activeArtifactId, sessionArtifactIds };
    }

    const restored = sessionId ? updatedMap[sessionId] : null;

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      activeArtifactId: restored?.activeArtifactId ?? null,
      sessionArtifactIds: restored?.sessionArtifactIds ?? [],
    });
  },

  // ---- Persistence ---------------------------------------------------------

  persistToStorage: () => {
    try {
      const { artifacts, pinnedArtifactIds } = get();
      const pinnedArtifacts: Record<string, Artifact> = {};
      for (const id of pinnedArtifactIds) {
        if (artifacts[id]) pinnedArtifacts[id] = artifacts[id];
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        artifacts: pinnedArtifacts,
        pinnedArtifactIds,
      }));
    } catch { /* noop */ }
  },

  loadFromStorage: () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      const artifacts = (data.artifacts || {}) as Record<string, Artifact>;
      const pinnedIds = (data.pinnedArtifactIds || []) as string[];
      set((s) => ({
        artifacts: { ...artifacts, ...s.artifacts },
        pinnedArtifactIds: pinnedIds,
      }));
    } catch { /* noop */ }
  },

  // ---- Selectors -----------------------------------------------------------

  activeArtifact: () => {
    const { artifacts, activeArtifactId } = get();
    if (!activeArtifactId) return null;
    return artifacts[activeArtifactId] ?? null;
  },

  pinnedArtifacts: () => {
    const { artifacts, pinnedArtifactIds } = get();
    return pinnedArtifactIds.map((id) => artifacts[id]).filter(Boolean);
  },

  sessionArtifacts: () => {
    const { artifacts, sessionArtifactIds } = get();
    return sessionArtifactIds.map((id) => artifacts[id]).filter(Boolean);
  },
}));

// Expose for debugging
if (typeof window !== 'undefined') (window as any).__unifiedArtifactStore = useUnifiedArtifactStore;
