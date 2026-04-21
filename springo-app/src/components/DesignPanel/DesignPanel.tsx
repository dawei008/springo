/**
 * DesignPanel - Main design mode panel with file browser, toolbar, canvas/code, and version timeline
 */
import { useRef, useEffect, useCallback } from 'react';
import { useDesignStore, selectCurrentDesign } from '@/stores/designStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import type { DesignTemplate } from '@/data/designTemplates';
import DesignToolbar from './DesignToolbar';
import DesignCanvas from './DesignCanvas';
import DesignCodeEditor from './DesignCodeEditor';
import DesignFileBrowser from './DesignFileBrowser';
import DesignVersionTimeline from './DesignVersionTimeline';
import DesignElementPopover from './DesignElementPopover';
import DesignTweaksPanel from './DesignTweaksPanel';
import DesignComparisonView from './DesignComparisonView';

export default function DesignPanel() {
  const active = useDesignStore((s) => s.active);
  const currentDesign = useDesignStore(selectCurrentDesign);
  const activeVersionIndex = useDesignStore((s) => s.activeVersionIndex);
  const viewport = useDesignStore((s) => s.viewport);
  const viewMode = useDesignStore((s) => s.viewMode);
  const deactivate = useDesignStore((s) => s.deactivateDesignMode);
  const comparisonMode = useDesignStore((s) => s.comparisonMode);

  const panelRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  // Resize handle (same pattern as ArtifactPanel / PlanPanel)
  useEffect(() => {
    const handle = resizeRef.current;
    const panel = panelRef.current;
    if (!handle || !panel) return;

    let dragging = false;
    let startX = 0;
    let startW = 0;

    const onDown = (e: MouseEvent) => {
      dragging = true;
      startX = e.clientX;
      startW = panel.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      const diff = startX - e.clientX;
      const maxW = Math.floor(window.innerWidth * 0.75);
      panel.style.width = Math.min(maxW, Math.max(400, startW + diff)) + 'px';
    };
    const onUp = () => {
      if (dragging) {
        dragging = false;
        handle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    handle.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      handle.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleTemplateSelect = useCallback((template: DesignTemplate) => {
    let sessionId = useSessionStore.getState().currentSessionId;
    if (!sessionId) sessionId = useSessionStore.getState().createSession();
    const settings = useSettingsStore.getState().settings;
    const designSystem = useDesignStore.getState().designSystem;
    useChatStore.getState().sendMessage(sessionId, template.prompt, [], {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId,
      designMode: true,
      designSystem: designSystem || undefined,
    });
  }, []);

  if (!active) return null;

  const hasMultiFile = currentDesign?.files && currentDesign.files.length > 0;

  return (
    <div className="design-panel" ref={panelRef}>
      <div className="design-resize-handle" ref={resizeRef} />

      {/* Header */}
      <div className="design-panel-header">
        <div className="design-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span className="design-header-title">Design Mode</span>
          {currentDesign && (
            <span className="design-header-version">v{activeVersionIndex + 1}</span>
          )}
        </div>
        <button className="design-header-close" onClick={deactivate} title="Exit design mode">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Toolbar */}
      <DesignToolbar />

      {/* Body: file browser + canvas/code + tweaks */}
      <div className="design-panel-body">
        {comparisonMode && viewMode === 'preview' ? (
          <DesignComparisonView />
        ) : (
          <>
            {hasMultiFile && <DesignFileBrowser />}
            <div className="design-panel-main">
              {viewMode === 'preview' ? (
                <DesignCanvas design={currentDesign} viewport={viewport} onTemplateSelect={handleTemplateSelect} />
              ) : (
                <DesignCodeEditor />
              )}
              {viewMode === 'preview' && <DesignElementPopover />}
            </div>
            {viewMode === 'preview' && <DesignTweaksPanel />}
          </>
        )}
      </div>

      {/* Version Timeline */}
      <DesignVersionTimeline />
    </div>
  );
}
