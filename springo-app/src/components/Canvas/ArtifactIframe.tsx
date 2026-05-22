import { useRef, useEffect, useCallback, useState } from 'react';
import { buildMultiFileRuntime, SPRINGO_TOKENS_STYLE_TAG } from '@/utils/multiFileRuntime';
import { generateBridgeSdk, BRIDGE_MESSAGE_TYPES } from '@/utils/bridgeSdk';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import type { ArtifactFile } from '@/stores/unifiedArtifactStore';
import { api } from '@/services/api';

interface SelectionInfo {
  text: string;
  rect: { x: number; y: number; width: number; height: number } | null;
}

function injectAsContext(text: string) {
  const el = document.getElementById('message-input') as HTMLTextAreaElement | null;
  if (!el) return;
  const quoted = text.split('\n').map((l) => '> ' + l).join('\n') + '\n\n';
  const current = el.value || '';
  const next = quoted + current;
  const nativeSet = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  nativeSet?.call(el, next);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  // Place caret right after the quoted block so the user can keep typing.
  const caret = quoted.length;
  el.focus();
  try { el.setSelectionRange(caret, caret); } catch { /* ignore */ }
}

const TOOL_ALLOWLIST = new Set([
  'read_file', 'write_file', 'list_directory',
  'search_files', 'get_weather', 'web_search',
]);

interface ArtifactIframeProps {
  artifactId: string;
  files: ArtifactFile[];
  state: Record<string, unknown>;
}

function buildArtifactHtml(files: ArtifactFile[], state: Record<string, unknown>): string {
  const bridgeScript = generateBridgeSdk(state);
  const hasJsx = files.some(f => f.type === 'jsx');
  const htmlFile = files.find(f => f.path === 'index.html');

  if (!hasJsx && htmlFile) {
    // Raw-HTML artifact: inject Springo design tokens FIRST so any <style> blocks
    // already in the file can override if they need to, then the bridge SDK LAST
    // so it runs after everything else is parsed.
    const withTokens = htmlFile.content.includes('</head>')
      ? htmlFile.content.replace('</head>', SPRINGO_TOKENS_STYLE_TAG + bridgeScript + '</head>')
      // No <head> — prepend one.
      : `<!DOCTYPE html><html><head>${SPRINGO_TOKENS_STYLE_TAG}${bridgeScript}</head><body>${htmlFile.content}</body></html>`;
    return withTokens;
  }

  const runtime = buildMultiFileRuntime(
    files.map(f => ({ path: f.path, type: f.type as 'html' | 'jsx' | 'css' | 'json' | 'text', content: f.content })),
  );

  return runtime.replace('</head>', bridgeScript + '</head>');
}

export default function ArtifactIframe({ artifactId, files, state }: ArtifactIframeProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const lastSrcdocRef = useRef<string>('');
  const [selection, setSelection] = useState<SelectionInfo | null>(null);

  // Reset selection when switching artifacts.
  useEffect(() => { setSelection(null); }, [artifactId]);

  const handleMessage = useCallback((e: MessageEvent) => {
    if (!e.data || typeof e.data.type !== 'string') return;
    if (e.source !== iframeRef.current?.contentWindow) return;
    const { type, payload } = e.data;
    // Only accept the documented bridge message types — the iframe sandbox
    // can technically post anything, so cheap validation here closes the gap.
    if (typeof type !== 'string' || !type.startsWith('springo:')) return;
    const store = useUnifiedArtifactStore.getState();

    switch (type) {
      case BRIDGE_MESSAGE_TYPES.SET_STATE:
        store.updateState(artifactId, payload);
        break;

      case BRIDGE_MESSAGE_TYPES.ELEMENT_PINNED:
        store.pinElement(payload);
        break;

      case BRIDGE_MESSAGE_TYPES.SELECTION_CONTEXT:
        if (payload && typeof payload.text === 'string') {
          setSelection({ text: payload.text, rect: payload.rect ?? null });
        } else {
          setSelection(null);
        }
        break;

      case BRIDGE_MESSAGE_TYPES.SEND_TO_CHAT: {
        const el = document.getElementById('message-input') as HTMLTextAreaElement | null;
        if (el) {
          const nativeSet = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
          nativeSet?.call(el, payload.message);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.focus();
        }
        break;
      }

      case BRIDGE_MESSAGE_TYPES.CALL_TOOL: {
        const { id, name, input } = payload;
        if (!TOOL_ALLOWLIST.has(name)) {
          iframeRef.current?.contentWindow?.postMessage({
            type: BRIDGE_MESSAGE_TYPES.TOOL_RESULT,
            payload: { id, error: `Tool "${name}" is not permitted for artifacts` },
          }, '*');
          break;
        }
        if (!input || typeof input !== 'object' || Array.isArray(input)) {
          iframeRef.current?.contentWindow?.postMessage({
            type: BRIDGE_MESSAGE_TYPES.TOOL_RESULT,
            payload: { id, error: 'Invalid tool input' },
          }, '*');
          break;
        }
        const iframe = iframeRef.current;
        api.tools.execute(name, input)
          .then(res => {
            iframe?.contentWindow?.postMessage({
              type: BRIDGE_MESSAGE_TYPES.TOOL_RESULT,
              payload: { id, result: res.data?.result ?? null },
            }, '*');
          })
          .catch(err => {
            iframe?.contentWindow?.postMessage({
              type: BRIDGE_MESSAGE_TYPES.TOOL_RESULT,
              payload: { id, error: err.message },
            }, '*');
          });
        break;
      }

      case BRIDGE_MESSAGE_TYPES.NOTIFICATION:
        break;

      case BRIDGE_MESSAGE_TYPES.CLIPBOARD:
        navigator.clipboard.writeText(payload.text).catch(() => {});
        break;

      case BRIDGE_MESSAGE_TYPES.READY:
        break;

      case BRIDGE_MESSAGE_TYPES.RESIZE:
        break;
    }
  }, [artifactId]);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  // Rebuild the iframe srcdoc only when files change. State changes are
  // propagated *from* the iframe (artifact calls window.springo.setState
  // → host store). If we re-inject state into srcdoc on every state update
  // we destroy the iframe's working DOM and cause visible flicker. The
  // artifact itself owns its runtime state (e.g. localStorage); on first
  // mount we still pass in `state` so restored sessions can resume.
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || files.length === 0) return;

    const srcdoc = buildArtifactHtml(files, state);
    if (srcdoc === lastSrcdocRef.current) return;
    lastSrcdocRef.current = srcdoc;
    iframe.srcdoc = srcdoc;
    // state intentionally omitted from deps — see comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  // Position the chip near the selection rect (clamped within the canvas body).
  // The rect is in iframe-content coords, which equal viewport coords because
  // the iframe spans the body; we just need to add the iframe's offset.
  const chipStyle: React.CSSProperties = (() => {
    if (!selection?.rect) return { right: 16, bottom: 16 };
    const iframe = iframeRef.current;
    if (!iframe) return { right: 16, bottom: 16 };
    const ir = iframe.getBoundingClientRect();
    const top = Math.max(ir.top, ir.top + selection.rect.y - 36);
    const left = Math.min(
      ir.right - 220,
      Math.max(ir.left + 8, ir.left + selection.rect.x + selection.rect.width / 2 - 110),
    );
    return { position: 'fixed', top, left };
  })();

  return (
    <>
      <iframe
        ref={iframeRef}
        className="artifact-iframe"
        sandbox="allow-scripts allow-same-origin"
      />
      {selection && (
        <button
          type="button"
          className="canvas-selection-chip"
          style={chipStyle}
          onClick={() => {
            injectAsContext(selection.text);
            setSelection(null);
          }}
          title={`Add ${selection.text.length.toLocaleString()} chars as context`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add as context
        </button>
      )}
    </>
  );
}
