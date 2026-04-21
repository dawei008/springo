/**
 * DesignToolbar - viewport switch, preview/code toggle, version select, export, zoom, interaction modes
 */
import { useDesignStore, selectCurrentDesign, type ViewportMode } from '@/stores/designStore';
import DesignVerificationBadge from './DesignVerificationBadge';

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
  const selectedElement = useDesignStore((s) => s.selectedElement);
  const tweaksOpen = useDesignStore((s) => s.tweaksOpen);
  const setTweaksOpen = useDesignStore((s) => s.setTweaksOpen);
  const comparisonMode = useDesignStore((s) => s.comparisonMode);
  const setComparisonMode = useDesignStore((s) => s.setComparisonMode);
  const zoom = useDesignStore((s) => s.zoom);
  const zoomIn = useDesignStore((s) => s.zoomIn);
  const zoomOut = useDesignStore((s) => s.zoomOut);
  const resetZoom = useDesignStore((s) => s.resetZoom);
  const setPresentMode = useDesignStore((s) => s.setPresentMode);
  const reloadCanvas = useDesignStore((s) => s.reloadCanvas);
  const fileBrowserOpen = useDesignStore((s) => s.fileBrowserOpen);
  const setFileBrowserOpen = useDesignStore((s) => s.setFileBrowserOpen);
  const currentDesign = useDesignStore(selectCurrentDesign);
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
        {/* File browser toggle */}
        {hasMultiFile && (
          <button
            className={`design-toolbar-icon-btn${fileBrowserOpen ? ' active' : ''}`}
            onClick={() => setFileBrowserOpen(!fileBrowserOpen)}
            title={fileBrowserOpen ? 'Hide files' : 'Show files'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
        )}
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
        {selectedElement && (
          <div className="design-element-indicator" title={`Selected: ${selectedElement.cssPath}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 3l14 9-7 2-4 7-3-18z" />
            </svg>
            <span>{selectedElement.tagName}{selectedElement.id ? `#${selectedElement.id}` : ''}</span>
          </div>
        )}
        <DesignVerificationBadge />

        {/* Zoom controls */}
        {viewMode === 'preview' && (
          <div className="design-zoom-group">
            <button className="design-zoom-btn" onClick={zoomOut} title="Zoom out">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <button className="design-zoom-label" onClick={resetZoom} title="Reset zoom">
              {zoom}%
            </button>
            <button className="design-zoom-btn" onClick={zoomIn} title="Zoom in">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>
        )}

        {/* Reload */}
        {viewMode === 'preview' && (
          <button className="design-toolbar-icon-btn" onClick={reloadCanvas} title="Reload preview">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </button>
        )}

        {versions.length >= 2 && (
          <button
            className={`design-compare-toggle${comparisonMode ? ' active' : ''}`}
            onClick={() => setComparisonMode(!comparisonMode)}
            title="Compare versions side-by-side"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="3" width="20" height="18" rx="2" />
              <line x1="12" y1="3" x2="12" y2="21" />
            </svg>
          </button>
        )}
        <button
          className={`design-tweaks-toggle${tweaksOpen ? ' active' : ''}`}
          onClick={() => setTweaksOpen(!tweaksOpen)}
          title="Toggle tweaks panel"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
          </svg>
        </button>

        {/* Present mode */}
        <button
          className="design-toolbar-icon-btn design-present-btn"
          onClick={() => setPresentMode(true)}
          title="Present design fullscreen"
          disabled={versions.length === 0}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
          </svg>
        </button>

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
