import { useRef, useEffect, useCallback } from 'react';
import { buildMultiFileRuntime, SPRINGO_TOKENS_STYLE_TAG } from '@/utils/multiFileRuntime';
import { generateBridgeSdk, BRIDGE_MESSAGE_TYPES } from '@/utils/bridgeSdk';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import type { ArtifactFile } from '@/stores/unifiedArtifactStore';
import { api } from '@/services/api';

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

  const handleMessage = useCallback((e: MessageEvent) => {
    if (!e.data || typeof e.data.type !== 'string') return;
    if (e.source !== iframeRef.current?.contentWindow) return;
    const { type, payload } = e.data;
    const store = useUnifiedArtifactStore.getState();

    switch (type) {
      case BRIDGE_MESSAGE_TYPES.SET_STATE:
        store.updateState(artifactId, payload);
        break;

      case BRIDGE_MESSAGE_TYPES.ELEMENT_PINNED:
        store.pinElement(payload);
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

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || files.length === 0) return;

    const srcdoc = buildArtifactHtml(files, state);
    if (srcdoc === lastSrcdocRef.current) return;
    lastSrcdocRef.current = srcdoc;
    iframe.srcdoc = srcdoc;
  }, [files, state]);

  return (
    <iframe
      ref={iframeRef}
      className="artifact-iframe"
      sandbox="allow-scripts allow-same-origin"
    />
  );
}
