/**
 * Canvas bridge client.
 *
 * After the fs-backed artifact store rewrite, the only canvas tool action
 * that still needs the renderer is `query` — it evaluates a CSS selector
 * against the live iframe DOM, which only exists here. `list`, `read`,
 * and `state` are served directly by the backend from
 * ~/.springo/artifacts/ and never hit this bridge.
 */

import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';

const BASE_URL = 'http://127.0.0.1:8081';
const POLL_INTERVAL_MS = 500;

interface CanvasRequest {
  id: string;
  payload: {
    action: 'query';
    artifactId?: string;
    selector?: string;
  };
}

interface CanvasResult {
  success: boolean;
  error?: string;
  data?: Record<string, unknown>;
}

function activeIframe(): HTMLIFrameElement | null {
  return document.querySelector<HTMLIFrameElement>('.artifact-iframe');
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
  if (p.action === 'query') return handleQuery(id, p.selector);
  return { success: false, error: `Unknown action: ${(p as { action: string }).action}` };
}

async function postResult(reqId: string, result: CanvasResult): Promise<void> {
  try {
    await fetch(`${BASE_URL}/v1/canvas/result/${reqId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result),
    });
  } catch {
    /* timeout on backend is the surfaced error */
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
    /* retry next tick */
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
