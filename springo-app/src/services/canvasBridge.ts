/**
 * Canvas bridge client.
 *
 * Short-polls `/v1/canvas/pending` and executes incoming requests against
 * the live Canvas iframe + unified artifact store, then posts the result
 * back to `/v1/canvas/result/{id}`.
 *
 * The backend's `canvas_bridge.py` queues requests from the `canvas` tool
 * and waits for results keyed by request id.
 */

import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';

const BASE_URL = 'http://127.0.0.1:8081';
const POLL_INTERVAL_MS = 500;

type CanvasAction =
  | 'list'
  | 'read'
  | 'state'
  | 'query';

interface CanvasRequest {
  id: string;
  payload: {
    action: CanvasAction;
    artifactId?: string;
    path?: string;
    selector?: string;
  };
}

interface CanvasResult {
  success: boolean;
  error?: string;
  data?: Record<string, unknown>;
}

// -----------------------------------------------------------------------------
// Action handlers — each reads the live store / iframe and returns a plain JSON
// payload the tool will surface to the assistant.
// -----------------------------------------------------------------------------

function activeIframe(): HTMLIFrameElement | null {
  return document.querySelector<HTMLIFrameElement>('.artifact-iframe');
}

function handleList(): CanvasResult {
  const s = useUnifiedArtifactStore.getState();
  const artifacts = Object.values(s.artifacts).map((a) => ({
    id: a.id,
    name: a.name,
    type: a.type,
    icon: a.icon,
    pinned: a.pinned,
    fileCount: a.files.length,
    version: a.versions.length,
    isActive: a.id === s.activeArtifactId,
  }));
  return { success: true, data: { artifacts, activeArtifactId: s.activeArtifactId } };
}

function handleRead(artifactId: string, path: string | undefined): CanvasResult {
  const s = useUnifiedArtifactStore.getState();
  const a = s.artifacts[artifactId];
  if (!a) return { success: false, error: `Artifact not found: ${artifactId}` };
  if (path) {
    const f = a.files.find((x) => x.path === path);
    if (!f) return { success: false, error: `File not found in artifact ${artifactId}: ${path}` };
    return { success: true, data: { path: f.path, type: f.type, content: f.content } };
  }
  return {
    success: true,
    data: {
      files: a.files.map((f) => ({ path: f.path, type: f.type, content: f.content })),
    },
  };
}

function handleState(artifactId: string): CanvasResult {
  const s = useUnifiedArtifactStore.getState();
  const a = s.artifacts[artifactId];
  if (!a) return { success: false, error: `Artifact not found: ${artifactId}` };
  return { success: true, data: { state: a.state ?? {} } };
}

function handleQuery(artifactId: string, selector: string | undefined): CanvasResult {
  if (!selector) return { success: false, error: 'query requires selector' };
  const s = useUnifiedArtifactStore.getState();
  if (s.activeArtifactId !== artifactId) {
    return {
      success: false,
      error: `Artifact ${artifactId} is not the active Canvas artifact. Active: ${s.activeArtifactId ?? 'none'}. Open it first.`,
    };
  }
  const doc = activeIframe()?.contentDocument;
  if (!doc) return { success: false, error: 'No iframe mounted' };
  try {
    const el = doc.querySelector(selector);
    if (!el) return { success: true, data: { exists: false } };
    return {
      success: true,
      data: {
        exists: true,
        tagName: el.tagName.toLowerCase(),
        text: (el.textContent || '').slice(0, 500),
        classes: Array.from(el.classList),
        id: (el as HTMLElement).id || undefined,
      },
    };
  } catch (e) {
    return { success: false, error: `Invalid selector: ${(e as Error).message}` };
  }
}

function execute(req: CanvasRequest): CanvasResult {
  const p = req.payload;
  const id = p.artifactId || '';
  switch (p.action) {
    case 'list':  return handleList();
    case 'read':  return handleRead(id, p.path);
    case 'state': return handleState(id);
    case 'query': return handleQuery(id, p.selector);
    default:
      return { success: false, error: `Unknown action: ${(p as { action: string }).action}` };
  }
}

async function postResult(reqId: string, result: CanvasResult): Promise<void> {
  try {
    await fetch(`${BASE_URL}/v1/canvas/result/${reqId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result),
    });
  } catch {
    // If the result can't be posted, the backend-side tool will time out.
  }
}

async function pollOnce(): Promise<void> {
  try {
    const res = await fetch(`${BASE_URL}/v1/canvas/pending`);
    if (!res.ok) return;
    const data = (await res.json()) as { requests: CanvasRequest[] };
    for (const req of data.requests || []) {
      let result: CanvasResult;
      try {
        result = execute(req);
      } catch (e) {
        result = { success: false, error: (e as Error).message };
      }
      await postResult(req.id, result);
    }
  } catch {
    // Network blip — try again next tick.
  }
}

let _timer: ReturnType<typeof setInterval> | null = null;

export function startCanvasBridgeClient(): void {
  if (_timer) return;
  _timer = setInterval(pollOnce, POLL_INTERVAL_MS);
}

export function stopCanvasBridgeClient(): void {
  if (_timer) {
    clearInterval(_timer);
    _timer = null;
  }
}
