/**
 * DesignToolbar - viewport switch, preview/code toggle, version select, export
 */
import { useDesignStore, type ViewportMode, type DesignViewMode } from '@/stores/designStore';

const VIEWPORTS: { mode: ViewportMode; label: string; icon: string }[] = [
  { mode: 'desktop', label: 'Desktop', icon: 'M4 6h16v10H4zM1 18h22' },
  { mode: 'tablet', label: 'Tablet', icon: 'M6 2h12a2 2 0 012 2v16a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01' },
  { mode: 'mobile', label: 'Mobile', icon: 'M8 2h8a2 2 0 012 2v16a2 2 0 01-2 2H8a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01' },
];

export default function DesignToolbar() {
  const viewport = useDesignStore((s) => s.viewport);
  const setViewport = useDesignStore((s) => s.setViewport);
  const viewMode = useDesignStore((s) => s.viewMode);
  const setViewMode = useDesignStore((s) => s.setViewMode);
  const versions = useDesignStore((s) => s.versions);
  const activeVersionIndex = useDesignStore((s) => s.activeVersionIndex);
  const selectVersion = useDesignStore((s) => s.selectVersion);

  const currentDesign = activeVersionIndex >= 0 && activeVersionIndex < versions.length
    ? versions[activeVersionIndex]
    : null;
  const hasMultiFile = currentDesign?.files && currentDesign.files.length > 0;

  const handleExport = async () => {
    const design = useDesignStore.getState().currentDesign();
    if (!design) return;

    if (design.files && design.files.length > 0) {
      // Multi-file: export as ZIP
      try {
        const JSZip = (await import('jszip')).default;
        const zip = new JSZip();
        for (const file of design.files) {
          zip.file(file.path, file.content);
        }
        const blob = await zip.generateAsync({ type: 'blob' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${design.title || 'design'}.zip`;
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        // Fallback: export just the entry HTML
        exportSingleHtml(design);
      }
    } else {
      exportSingleHtml(design);
    }
  };

  return (
    <div className="design-toolbar">
      <div className="design-toolbar-left">
        {/* Preview / Code toggle */}
        <div className="design-view-tabs">
          <button
            className={`design-view-tab${viewMode === 'preview' ? ' active' : ''}`}
            onClick={() => setViewMode('preview')}
          >
            Preview
          </button>
          <button
            className={`design-view-tab${viewMode === 'code' ? ' active' : ''}`}
            onClick={() => setViewMode('code')}
          >
            Code
          </button>
        </div>

        {/* Viewport toggles (only in preview mode) */}
        {viewMode === 'preview' && (
          <div className="design-viewport-group">
            {VIEWPORTS.map((v) => (
              <button
                key={v.mode}
                className={`design-viewport-btn${viewport === v.mode ? ' active' : ''}`}
                onClick={() => setViewport(v.mode)}
                title={v.label}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={v.icon} />
                </svg>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="design-toolbar-center">
        {/* Version selector */}
        {versions.length > 1 && (
          <select
            className="design-version-select"
            value={activeVersionIndex}
            onChange={(e) => selectVersion(Number(e.target.value))}
          >
            {versions.map((v, i) => (
              <option key={v.id} value={i}>
                v{i + 1} — {v.title}
              </option>
            ))}
          </select>
        )}
        {versions.length <= 1 && versions.length > 0 && (
          <span className="design-version-label">v1 — {versions[0]?.title}</span>
        )}
        {hasMultiFile && (
          <span className="design-project-badge">{currentDesign!.files.length} files</span>
        )}
      </div>

      <div className="design-toolbar-right">
        <button
          className="design-export-btn"
          onClick={handleExport}
          title={hasMultiFile ? 'Export as ZIP' : 'Export as HTML'}
          disabled={versions.length === 0}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          <span>Export</span>
        </button>
      </div>
    </div>
  );
}

function exportSingleHtml(design: { html: string; title: string }) {
  const blob = new Blob([design.html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${design.title || 'design'}.html`;
  a.click();
  URL.revokeObjectURL(url);
}
