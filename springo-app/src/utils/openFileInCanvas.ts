import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import { buildFilePreviewHtml, getPreviewKind } from './filePreviewHtml';

/**
 * Open an on-disk file in the Canvas panel. Re-opening the same path reuses
 * the existing artifact (stable id per path), so version history accumulates.
 *
 * Non-HTML files (markdown, code, SVG, plain text) are wrapped in an HTML
 * shell that renders them. HTML files pass through unmodified.
 */
export async function openFileInCanvas(filePath: string): Promise<void> {
  const kind = getPreviewKind(filePath);
  if (!kind || !window.electronAPI?.readFileBase64) {
    window.electronAPI?.openPath(filePath);
    return;
  }
  try {
    const result = await window.electronAPI.readFileBase64(filePath);
    if (!result.success || !result.data) {
      window.electronAPI?.openPath(filePath);
      return;
    }
    // Decode base64 → binary → UTF-8 (atob alone mangles multi-byte chars like Chinese)
    const binary = atob(result.data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const content = new TextDecoder('utf-8').decode(bytes);
    const fileName = filePath.split('/').pop() || filePath;

    const htmlContent = kind === 'html' ? content : buildFilePreviewHtml(filePath, content, kind);

    const stableId = 'file-' + filePath.replace(/[^a-zA-Z0-9]+/g, '-').slice(-48);
    const store = useUnifiedArtifactStore.getState();
    const existing = store.artifacts[stableId];
    if (existing) {
      store.openArtifact(stableId);
      store.applyPatch(stableId, [
        { path: 'index.html', action: 'replace', fileType: 'html', content: htmlContent },
      ]);
      return;
    }

    store.createArtifact({
      id: stableId,
      name: fileName,
      type: 'app',
      icon: kind === 'html' ? 'web' : kind === 'svg' ? 'image' : 'document',
      files: [{ path: 'index.html', type: 'html', content: htmlContent }],
    });
  } catch {
    window.electronAPI?.openPath(filePath);
  }
}
