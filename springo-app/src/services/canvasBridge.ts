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
import { api } from './api';

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
  if (p.action !== 'query') return { success: false, error: `Unknown action: ${(p as { action: string }).action}` };
  return handleQuery(p.artifactId || '', p.selector);
}

async function pollOnce(): Promise<void> {
  const res = await api.canvas.pending();
  if (!res.ok || !res.data) return;
  const requests = res.data.requests || [];
  // Run all pending requests in parallel — querying the iframe DOM is
  // synchronous, so the overlap is purely on the postResult round-trip.
  await Promise.all(
    requests.map(async (req) => {
      let result: CanvasResult;
      try {
        result = execute(req as CanvasRequest);
      } catch (e) {
        result = { success: false, error: (e as Error).message };
      }
      await api.canvas.postResult(req.id, result);
    }),
  );
}

let _running = false;
let _timer: ReturnType<typeof setTimeout> | null = null;

// Chain setTimeout instead of setInterval so a slow pollOnce can't stack up
// behind itself if the backend is sluggish.
async function tick(): Promise<void> {
  if (!_running) return;
  try { await pollOnce(); } catch (e) { console.warn('[canvas] poll failed:', e); /* retry next tick */ }
  if (!_running) return;
  _timer = setTimeout(tick, POLL_INTERVAL_MS);
}

export function startCanvasBridgeClient(): void {
  if (_running) return;
  _running = true;
  void tick();
}

export function stopCanvasBridgeClient(): void {
  _running = false;
  if (_timer) { clearTimeout(_timer); _timer = null; }
}
