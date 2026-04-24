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
  | 'query'
  | 'patch'
  | 'dispatch';

interface CanvasRequest {
  id: string;
  payload: {
    action: CanvasAction;
    artifactId?: string;
    path?: string;
    selector?: string;
    files?: Array<{ path: string; action: 'replace' | 'create' | 'delete'; content?: string; file_type?: string }>;
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

function handlePatch(
  artifactId: string,
  files: CanvasRequest['payload']['files'],
): CanvasResult {
  if (!files?.length) return { success: false, error: 'patch requires files=[]' };
  const s = useUnifiedArtifactStore.getState();
  if (!s.artifacts[artifactId]) {
    return { success: false, error: `Artifact not found: ${artifactId}` };
  }
  const mapped = files.map((f) => ({
    path: f.path,
    action: f.action,
    content: f.content ?? '',
    fileType: f.file_type || 'jsx',
  }));
  s.applyPatch(artifactId, mapped);
  const after = useUnifiedArtifactStore.getState().artifacts[artifactId];
  return {
    success: true,
    data: {
      version: after?.versions.length ?? 0,
      fileCount: after?.files.length ?? 0,
    },
  };
}

function handleDispatch(artifactId: string, selector: string | undefined): CanvasResult {
  if (!selector) return { success: false, error: 'dispatch requires selector' };
  const s = useUnifiedArtifactStore.getState();
  if (s.activeArtifactId !== artifactId) {
    return {
      success: false,
      error: `Artifact ${artifactId} is not active. Open it before dispatching.`,
    };
  }
  const iframe = activeIframe();
  const win = iframe?.contentWindow as (Window & typeof globalThis) | null | undefined;
  if (!win) return { success: false, error: 'No iframe mounted' };

  // Same caveats as the dev hook: React 18 in srcdoc can swallow synthesized
  // events. Prefer <springo-action> for reliable state changes.
  try {
    const runEval = ((win as unknown as { eval: (s: string) => unknown }).eval);
    const ok = runEval(
      '(function(sel){' +
        'var el=document.querySelector(sel);' +
        'if(!el) return false;' +
        'for (var t of ["mousedown","mouseup","click"]) {' +
          'el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window}));' +
        '}' +
        'return true;' +
      '})(' + JSON.stringify(selector) + ')',
    );
    return {
      success: true,
      data: {
        dispatched: Boolean(ok),
        note: ok
          ? 'Click dispatched. React 18 in sandboxed iframes may not always commit the resulting state update — verify with canvas(action="state") or prefer <springo-action>.'
          : `Selector not found: ${selector}`,
      },
    };
  } catch (e) {
    return { success: false, error: `Dispatch failed: ${(e as Error).message}` };
  }
}

function execute(req: CanvasRequest): CanvasResult {
  const p = req.payload;
  const id = p.artifactId || '';
  switch (p.action) {
    case 'list':     return handleList();
    case 'read':     return handleRead(id, p.path);
    case 'state':    return handleState(id);
    case 'query':    return handleQuery(id, p.selector);
    case 'patch':    return handlePatch(id, p.files);
    case 'dispatch': return handleDispatch(id, p.selector);
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
