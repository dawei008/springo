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
 * IDs of built-in React panels that the Canvas can render instead of an
 * iframe. These artifacts never round-trip to the backend; they are
 * local-only singletons keyed by stable IDs (`internal-${id}`).
 */
export type InternalComponentId = 'tasks' | 'schedules' | 'meeting' | 'recording' | 'kb-graph' | 'plan';

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
  /**
   * If set, the Canvas renders the matching built-in React panel
   * (TasksCanvasPanel/SchedulesPanel/MeetingPanel/RecordingCanvasPanel)
   * instead of an iframe. These artifacts are never persisted to the backend
   * and are filtered out of the Apps sidebar section.
   */
  internalComponent?: InternalComponentId;
  /**
   * Whether the artifact is currently being actively built by the model.
   * Inspired by Quick's `live=True/False` pattern. While `live` is true:
   *   - the canvas header shows a "Building…" badge
   *   - patches arriving in quick succession are expected
   *   - the user is informed not to edit (but we don't lock the iframe;
   *     the AI is the author and can clobber)
   * Auto-flips to false 5 seconds after the last patch lands, or on
   * explicit op="finalize". `createArtifact` defaults to true.
   */
  live?: boolean;
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
  /** Number of backend ops currently waiting to retry. */
  syncPendingCount: number;
  /** Whether the most recent backend probe failed. */
  syncOffline: boolean;

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
  /** Close a tab: remove from sessionArtifactIds; switch active to next/prev sibling. */
  closeArtifactTab: (id: string) => void;
  deleteArtifact: (id: string) => void;
  /** Reorder tabs (drag/drop in Canvas tab strip). */
  reorderSessionArtifacts: (orderedIds: string[]) => void;
  /**
   * Open a built-in React panel as an artifact. Idempotent — calling twice
   * with the same id reuses the existing local artifact. Never hits the
   * backend.
   */
  openInternal: (component: InternalComponentId, name: string, icon?: ArtifactIconName) => void;

  // Code updates
  applyPatch: (id: string, filePatches: Array<{
    path: string;
    action: 'replace' | 'create' | 'delete';
    content: string;
    fileType: string;
  }>) => void;
  updateFiles: (id: string, files: ArtifactFile[]) => void;
  /**
   * Mark an artifact as no longer being actively built. Called automatically
   * 5s after the last patch settles, OR explicitly when the model emits
   * <springo-artifact op="finalize" id="...">.
   */
  finalizeArtifact: (id: string) => void;

  // State updates
  updateState: (id: string, state: Record<string, unknown>) => void;
  replaceState: (id: string, state: Record<string, unknown>) => void;

  // Version management
  selectVersion: (id: string, versionIndex: number) => Promise<void>;
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
// (any artifact that calls setState on every keystroke) coalesce into one
// round-trip per ~500ms.
const _stateTimers: Record<string, ReturnType<typeof setTimeout>> = {};

// Per-artifact "auto-finalize" timer. While the model is mid-build, every
// applyPatch call resets this timer; if no patch lands within FINALIZE_MS,
// the artifact transitions to live=false. Inspired by Quick's `live=False`
// hand-off semantic — the user knows it's safe to read/edit when the badge
// disappears, instead of guessing whether more patches are coming.
const _finalizeTimers: Record<string, ReturnType<typeof setTimeout>> = {};
const FINALIZE_MS = 5000;

function _scheduleAutoFinalize(id: string): void {
  if (_finalizeTimers[id]) clearTimeout(_finalizeTimers[id]);
  _finalizeTimers[id] = setTimeout(() => {
    delete _finalizeTimers[id];
    const cur = useUnifiedArtifactStore.getState().artifacts[id];
    if (!cur || cur.live === false) return;
    useUnifiedArtifactStore.setState((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...cur, live: false } },
    }));
  }, FINALIZE_MS);
}
function flushState(id: string, state: Record<string, unknown>) {
  if (_stateTimers[id]) clearTimeout(_stateTimers[id]);
  _stateTimers[id] = setTimeout(() => {
    delete _stateTimers[id];
    enqueueSync({
      kind: 'state',
      key: `state:${id}`,
      run: () => api('PUT', `/v1/artifacts/${id}/state`, { state }),
    });
  }, 500);
}

// ---------------------------------------------------------------------------
// Sync queue with exponential backoff. Ops are de-duplicated by `key` so
// rapid-fire updates collapse to the latest version. After max retries the
// op is dropped and logged (the local optimistic state remains).
// ---------------------------------------------------------------------------

type SyncOp = {
  kind: 'create' | 'patch' | 'state' | 'pin' | 'delete';
  key: string;
  run: () => Promise<unknown>;
  onSuccess?: (result: unknown) => void;
  attempts?: number;
};

const _queue = new Map<string, SyncOp>();
let _flushScheduled = false;
let _flushBackoff = 0;

function setSyncStatus(pendingDelta: number, offline?: boolean) {
  const s = useUnifiedArtifactStore.getState();
  const next = Math.max(0, s.syncPendingCount + pendingDelta);
  const patch: Partial<UnifiedArtifactState> = { syncPendingCount: next };
  if (typeof offline === 'boolean') patch.syncOffline = offline;
  useUnifiedArtifactStore.setState(patch);
}

function enqueueSync(op: SyncOp) {
  const existed = _queue.has(op.key);
  _queue.set(op.key, op);
  if (!existed) setSyncStatus(+1);
  scheduleFlush(0);
}

function scheduleFlush(delay: number) {
  if (_flushScheduled) return;
  _flushScheduled = true;
  setTimeout(() => {
    _flushScheduled = false;
    void flushQueue();
  }, delay);
}

async function flushQueue() {
  if (_queue.size === 0) return;
  // Snapshot keys so we don't re-process ops re-enqueued mid-loop.
  const keys = Array.from(_queue.keys());
  let anyFailed = false;
  for (const key of keys) {
    const op = _queue.get(key);
    if (!op) continue;
    try {
      const result = await op.run();
      _queue.delete(key);
      setSyncStatus(-1, false);
      op.onSuccess?.(result);
    } catch (e) {
      const attempts = (op.attempts ?? 0) + 1;
      // Cap retries; after 6 attempts (≈ 60s w/ backoff) drop the op.
      if (attempts >= 6) {
        _queue.delete(key);
        setSyncStatus(-1);
        console.warn('[artifacts] sync giving up', op.kind, key, (e as Error).message);
      } else {
        op.attempts = attempts;
        anyFailed = true;
      }
    }
  }
  if (_queue.size > 0) {
    setSyncStatus(0, anyFailed);
    _flushBackoff = anyFailed ? Math.min(30_000, Math.max(2000, _flushBackoff * 2 || 2000)) : 0;
    scheduleFlush(_flushBackoff || 1000);
  } else {
    _flushBackoff = 0;
    setSyncStatus(0, false);
  }
}

// Listen for browser online events to retry sooner when connectivity returns.
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    _flushBackoff = 0;
    if (_queue.size > 0) scheduleFlush(0);
  });
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
  syncPendingCount: 0,
  syncOffline: false,

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
      // Born "live" — the model just created me and may immediately patch
      // me. The applyPatch path resets the auto-finalize timer; if no
      // patch arrives within 5s the artifact transitions to live=false.
      live: true,
    };

    set((s) => ({
      artifacts: { ...s.artifacts, [id]: artifact },
      activeArtifactId: id,
      sessionArtifactIds: [...s.sessionArtifactIds, id],
    }));
    _scheduleAutoFinalize(id);

    // Server create, then refresh to pick up canonical meta (real version id
    // etc). If the backend is offline we keep retrying so the artifact is not
    // lost on reload.
    enqueueSync({
      kind: 'create',
      key: `create:${id}`,
      run: () =>
        api<BackendArtifact>('POST', '/v1/artifacts', {
          id,
          name: props.name,
          type,
          icon,
          session_id: get().currentSessionId ?? null,
          files: files.map((f) => ({ path: f.path, type: f.type, content: f.content })),
          state,
        }),
      onSuccess: (result) => {
        const merged = toArtifact(result as BackendArtifact);
        set((s) => ({ artifacts: { ...s.artifacts, [id]: merged } }));
      },
    });

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

  closeArtifactTab: (id) => {
    set((s) => {
      const ids = s.sessionArtifactIds;
      const idx = ids.indexOf(id);
      if (idx === -1) return s;
      const nextIds = ids.filter((x) => x !== id);
      // If we closed the active tab, jump to the right neighbor (or left).
      let nextActive = s.activeArtifactId;
      if (s.activeArtifactId === id) {
        nextActive = nextIds[idx] ?? nextIds[idx - 1] ?? null;
      }
      return {
        sessionArtifactIds: nextIds,
        activeArtifactId: nextActive,
        pinnedElement: nextActive === id ? null : s.pinnedElement,
      };
    });
  },

  reorderSessionArtifacts: (orderedIds) => {
    set((s) => {
      const known = new Set(s.sessionArtifactIds);
      // Keep only ids we actually know about, in the requested order, then
      // append anything that wasn't in the new order so we don't lose tabs.
      const filtered = orderedIds.filter((id) => known.has(id));
      const tail = s.sessionArtifactIds.filter((id) => !filtered.includes(id));
      return { sessionArtifactIds: [...filtered, ...tail] };
    });
  },

  openInternal: (component, name, icon) => {
    const id = `internal-${component}`;
    set((s) => {
      const existing = s.artifacts[id];
      const now = Date.now();
      const artifact: Artifact = existing ?? {
        id,
        name,
        icon: icon ?? 'component',
        type: 'component',
        files: [],
        state: {},
        versions: [{ id: `${id}-v0`, files: [], state: {}, title: name, timestamp: now }],
        activeVersionIndex: 0,
        createdAt: now,
        updatedAt: now,
        pinned: false,
        internalComponent: component,
      };
      const inSession = s.sessionArtifactIds.includes(id);
      return {
        artifacts: { ...s.artifacts, [id]: artifact },
        activeArtifactId: id,
        sessionArtifactIds: inSession ? s.sessionArtifactIds : [...s.sessionArtifactIds, id],
      };
    });
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
    enqueueSync({
      kind: 'delete',
      key: `delete:${id}`,
      run: () => api('DELETE', `/v1/artifacts/${id}`),
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
          // A patch arrived → re-enter "live" mode and reset the
          // auto-finalize timer. Quick-style live preview semantics.
          live: true,
        },
      },
    }));
    _scheduleAutoFinalize(id);

    // Server patch; refresh afterward to pick up canonical version id. The
    // queue retries if the backend is offline, so the local optimistic state
    // and the on-disk source eventually reconcile.
    enqueueSync({
      kind: 'patch',
      key: `patch:${id}:${now}`,
      run: () =>
        api<BackendArtifact>('PATCH', `/v1/artifacts/${id}`, {
          files: filePatches.map((p) => ({
            path: p.path,
            action: p.action,
            content: p.content,
            file_type: p.fileType,
          })),
        }),
      onSuccess: (result) => {
        const merged = toArtifact(result as BackendArtifact);
        set((s) => ({ artifacts: { ...s.artifacts, [id]: merged } }));
      },
    });
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

  finalizeArtifact: (id) => {
    if (_finalizeTimers[id]) {
      clearTimeout(_finalizeTimers[id]);
      delete _finalizeTimers[id];
    }
    const cur = get().artifacts[id];
    if (!cur || cur.live === false) return;
    set((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...cur, live: false } },
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

  selectVersion: async (id, versionIndex) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;
    if (versionIndex < 0 || versionIndex >= artifact.versions.length) return;
    const target = artifact.versions[versionIndex];

    // Selecting the current head version is a no-op.
    if (versionIndex === artifact.activeVersionIndex) return;

    // Optimistic local view swap. If the snapshot is empty (only metadata
    // was hydrated), pull files first so the iframe has something to render.
    let files = target.files;
    if (files.length === 0) {
      try {
        const fetched = await api<{ files: Array<{ path: string; type: string; content: string }> }>(
          'GET',
          `/v1/artifacts/${id}/versions/${target.id}/files`,
        );
        files = fetched.files.map((f) => ({
          path: f.path,
          type: (['html', 'jsx', 'css', 'json', 'text'].includes(f.type) ? f.type : 'text') as ArtifactFile['type'],
          content: f.content,
        }));
      } catch (e) {
        console.warn('[artifacts] fetch version files failed', target.id, (e as Error).message);
        return;
      }
    }

    set((s) => ({
      artifacts: {
        ...s.artifacts,
        [id]: {
          ...artifact,
          activeVersionIndex: versionIndex,
          files: files.map((f) => ({ ...f })),
          state: { ...target.state },
          versions: artifact.versions.map((v, i) =>
            i === versionIndex ? { ...v, files: files.map((f) => ({ ...f })) } : v,
          ),
        },
      },
    }));

    // Persist the rollback so the choice survives reload. The backend
    // snapshots the rollback as a new version; refresh to pick up canonical
    // version metadata.
    try {
      const merged = await api<BackendArtifact>(
        'POST',
        `/v1/artifacts/${id}/rollback/${target.id}`,
      );
      set((s) => ({ artifacts: { ...s.artifacts, [id]: toArtifact(merged) } }));
    } catch (e) {
      console.warn('[artifacts] rollback sync failed', id, (e as Error).message);
    }
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
    enqueueSync({
      kind: 'pin',
      key: `pin:${id}`,
      run: () => api('POST', `/v1/artifacts/${id}/pin`, { pinned: true }),
    });
  },

  unpinArtifact: (id) => {
    const artifact = get().artifacts[id];
    if (!artifact) return;
    set((s) => ({
      artifacts: { ...s.artifacts, [id]: { ...artifact, pinned: false } },
      pinnedArtifactIds: s.pinnedArtifactIds.filter((i) => i !== id),
    }));
    enqueueSync({
      kind: 'pin',
      key: `pin:${id}`,
      run: () => api('POST', `/v1/artifacts/${id}/pin`, { pinned: false }),
    });
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
