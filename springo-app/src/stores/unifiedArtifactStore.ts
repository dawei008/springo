/**
 * Unified Artifact Store
 *
 * Thin client over the backend's /v1/artifacts REST API.  The source of
 * truth lives on disk under ~/.springo/artifacts/; this store is an
 * in-memory mirror so React renders stay fast. Every mutation is echoed
 * to the backend; background reads keep the mirror fresh.
 */
import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type UnifiedArtifactType = 'app' | 'component' | 'document' | 'template';

/**
 * Registered artifact icon names. Runtime icon renderers live in
 * `components/Canvas/ArtifactIcon.tsx` — this type is the data-layer source of
 * truth so the store and serialized artifacts can type the `icon` field.
 */
export type ArtifactIconName =
  | 'app' | 'component' | 'document' | 'template'
  | 'dashboard' | 'chart' | 'todo' | 'web' | 'form' | 'counter'
  | 'mobile' | 'calendar' | 'chat' | 'image' | 'code' | 'box';

/** Runtime-checkable set, kept in sync with ArtifactIconName. */
export const ARTIFACT_ICON_NAMES = new Set<ArtifactIconName>([
  'app', 'component', 'document', 'template',
  'dashboard', 'chart', 'todo', 'web', 'form', 'counter',
  'mobile', 'calendar', 'chat', 'image', 'code', 'box',
]);

/** Coerce an arbitrary string to a valid icon name; fall back to `type` then `'box'`. */
export function resolveIconName(icon: string | undefined | null, type?: string): ArtifactIconName {
  if (icon && ARTIFACT_ICON_NAMES.has(icon as ArtifactIconName)) return icon as ArtifactIconName;
  if (type && ARTIFACT_ICON_NAMES.has(type as ArtifactIconName)) return type as ArtifactIconName;
  return 'box';
}

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
  icon: ArtifactIconName;
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
    /** Accepts any string (models may emit stale values); coerced to a valid `ArtifactIconName` at insert time. */
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

  // Persistence / sync
  loadFromBackend: () => Promise<void>;
  refreshArtifact: (id: string) => Promise<void>;

  // Selectors
  activeArtifact: () => Artifact | null;
  pinnedArtifacts: () => Artifact[];
  sessionArtifacts: () => Artifact[];
}

// ---------------------------------------------------------------------------
// Backend client
// ---------------------------------------------------------------------------

const BASE_URL = 'http://127.0.0.1:8081';

interface BackendArtifact {
  id: string;
  name: string;
  type: UnifiedArtifactType;
  icon: string;
  version: number;
  pinned: boolean;
  pinnedBy?: string[];
  sessionId?: string | null;
  createdAt: number;
  updatedAt: number;
  files?: Array<{ path: string; type: string; content: string }>;
  state?: Record<string, unknown>;
  versions?: Array<{ id: string; createdAt: number | null; fileCount: number }>;
}

function toArtifact(b: BackendArtifact): Artifact {
  const files: ArtifactFile[] = (b.files ?? []).map((f) => ({
    path: f.path,
    type: (['html', 'jsx', 'css', 'json', 'text'].includes(f.type) ? f.type : 'text') as ArtifactFile['type'],
    content: f.content,
  }));
  const state = b.state ?? {};
  const backendVersions = b.versions ?? [];
  // Frontend keeps a synthetic linear version history. File contents for
  // older versions are fetched lazily if the user actually browses them.
  const versions: ArtifactVersion[] = backendVersions.length > 0
    ? backendVersions.map((v, i) => ({
        id: v.id,
        files: i === backendVersions.length - 1 ? files : [],
        state: i === backendVersions.length - 1 ? state : {},
        title: b.name,
        timestamp: v.createdAt ?? b.updatedAt,
      }))
    : [{
        id: `${b.id}-v0`,
        files,
        state,
        title: b.name,
        timestamp: b.createdAt,
      }];
  return {
    id: b.id,
    name: b.name,
    icon: resolveIconName(b.icon, b.type),
    type: b.type,
    files,
    state,
    versions,
    activeVersionIndex: versions.length - 1,
    createdAt: b.createdAt,
    updatedAt: b.updatedAt,
    sessionId: b.sessionId ?? undefined,
    pinned: b.pinned,
  };
}

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

// Debounced PUT of state.json; per-artifact timer so high-frequency editors
// (the novel studio sends setState on every keystroke) coalesce into one
// round-trip per ~500ms.
const _stateTimers: Record<string, ReturnType<typeof setTimeout>> = {};
function flushState(id: string, state: Record<string, unknown>) {
  if (_stateTimers[id]) clearTimeout(_stateTimers[id]);
  _stateTimers[id] = setTimeout(() => {
    delete _stateTimers[id];
    api('PUT', `/v1/artifacts/${id}/state`, { state }).catch((e) => {
      console.warn('[artifacts] state sync failed', id, (e as Error).message);
    });
  }, 500);
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useUnifiedArtifactStore = create<UnifiedArtifactState>((set, get) => ({
  artifacts: {},
  activeArtifactId: null,
  sessionArtifactIds: [],
  pinnedArtifactIds: [],
  pinnedElement: null,
  sessionMap: {},
  currentSessionId: null,

  // ---- Artifact CRUD -------------------------------------------------------

  createArtifact: (props) => {
    const now = Date.now();
    const id = props.id ?? `art-${now}-${Math.random().toString(36).slice(2, 8)}`;
    const type: UnifiedArtifactType = props.type ?? 'app';
    const icon = resolveIconName(props.icon, type);
    const state = props.state ?? {};
    const files = props.files;

    // Optimistic local insert so Canvas renders immediately.
    const initialVersion: ArtifactVersion = {
      id: `${id}-v0`,
      files: files.map((f) => ({ ...f })),
      state: { ...state },
      title: props.name,
      timestamp: now,
    };
    const artifact: Artifact = {
      id,
      name: props.name,
      icon,
      type,
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

    // Server create, then refresh to pick up canonical meta (real version id etc).
    api<BackendArtifact>('POST', '/v1/artifacts', {
      id,
      name: props.name,
      type,
      icon,
      session_id: get().currentSessionId ?? null,
      files: files.map((f) => ({ path: f.path, type: f.type, content: f.content })),
      state,
    })
      .then((b) => {
        const merged = toArtifact(b);
        set((s) => ({ artifacts: { ...s.artifacts, [id]: merged } }));
      })
      .catch((e) => console.warn('[artifacts] create sync failed', (e as Error).message));

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
    api('DELETE', `/v1/artifacts/${id}`).catch((e) => {
      console.warn('[artifacts] delete sync failed', id, (e as Error).message);
    });
  },

  // ---- Code updates --------------------------------------------------------

  applyPatch: (id, filePatches) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;

    // Optimistic local apply so the iframe re-renders immediately.
    const files = [...artifact.files.map((f) => ({ ...f }))];
    for (const patch of filePatches) {
      switch (patch.action) {
        case 'replace': {
          const idx = files.findIndex((f) => f.path === patch.path);
          if (idx !== -1) files[idx] = { ...files[idx], content: patch.content };
          else files.push({ path: patch.path, type: patch.fileType as ArtifactFile['type'], content: patch.content });
          break;
        }
        case 'create':
          files.push({ path: patch.path, type: patch.fileType as ArtifactFile['type'], content: patch.content });
          break;
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

    // Server patch; refresh afterward to pick up canonical version id.
    api<BackendArtifact>('PATCH', `/v1/artifacts/${id}`, {
      files: filePatches.map((p) => ({
        path: p.path,
        action: p.action,
        content: p.content,
        file_type: p.fileType,
      })),
    })
      .then((b) => {
        const merged = toArtifact(b);
        set((s) => ({ artifacts: { ...s.artifacts, [id]: merged } }));
      })
      .catch((e) => console.warn('[artifacts] patch sync failed', id, (e as Error).message));
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
    // updateFiles is intentionally local-only (used by selectVersion);
    // the server already has the authoritative file tree.
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
    flushState(id, merged);
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
    flushState(id, newState);
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
    // Full version browsing / rollback remains a v2 — for now, selecting an
    // older version only updates the local view. Use <springo-artifact
    // op="patch"> to actually apply a change.
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
    api('POST', `/v1/artifacts/${id}/pin`, { pinned: true }).catch((e) =>
      console.warn('[artifacts] pin sync failed', id, (e as Error).message),
    );
  },

  unpinArtifact: (id) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;
    set((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...artifact, pinned: false } },
      pinnedArtifactIds: s.pinnedArtifactIds.filter((i) => i !== id),
    }));
    api('POST', `/v1/artifacts/${id}/pin`, { pinned: false }).catch((e) =>
      console.warn('[artifacts] unpin sync failed', id, (e as Error).message),
    );
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

  // ---- Backend sync --------------------------------------------------------

  loadFromBackend: async () => {
    try {
      const list = await api<{ artifacts: BackendArtifact[] }>('GET', '/v1/artifacts');
      // Hydrate metadata only; file contents come via refreshArtifact on demand.
      const byId: Record<string, Artifact> = {};
      const pinned: string[] = [];
      for (const b of list.artifacts) {
        byId[b.id] = toArtifact(b);
        if (b.pinned) pinned.push(b.id);
      }
      set({ artifacts: byId, pinnedArtifactIds: pinned });
    } catch (e) {
      console.warn('[artifacts] loadFromBackend failed', (e as Error).message);
    }
  },

  refreshArtifact: async (id) => {
    try {
      const b = await api<BackendArtifact>('GET', `/v1/artifacts/${id}`);
      const merged = toArtifact(b);
      set((s) => ({ artifacts: { ...s.artifacts, [id]: merged } }));
    } catch (e) {
      console.warn('[artifacts] refreshArtifact failed', id, (e as Error).message);
    }
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

// ---------------------------------------------------------------------------
// Startup: purge any leftover localStorage from the pre-filesystem era,
// then hydrate from the backend.
// ---------------------------------------------------------------------------

if (typeof window !== 'undefined') {
  try { localStorage.removeItem('springo-unified-artifacts'); } catch { /* noop */ }
  // Fire-and-forget initial sync.
  void useUnifiedArtifactStore.getState().loadFromBackend();
  // Expose for debugging.
  (window as any).__unifiedArtifactStore = useUnifiedArtifactStore;
}
