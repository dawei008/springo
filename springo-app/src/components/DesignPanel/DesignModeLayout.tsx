import { useRef, useEffect, useCallback, useState } from 'react';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';
import DesignCanvas from './DesignCanvas';
import DesignVersionTimeline from './DesignVersionTimeline';
import DesignSystemOnboarding from './DesignSystemOnboarding';
import { useDesignStore, selectCurrentDesign } from '@/stores/designStore';
import type { PinnedElement } from '@/stores/designStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';

function DesignSystemSelector() {
  const designSystem = useDesignStore((s) => s.designSystem);
  const designSystems = useDesignStore((s) => s.designSystems);
  const setDesignSystem = useDesignStore((s) => s.setDesignSystem);
  const [open, setOpen] = useState(false);

  if (!designSystem && designSystems.length === 0) return null;

  const colors = designSystem?.colors || {};
  const colorDots = Object.values(colors).slice(0, 4);

  return (
    <div className="ds-selector" onClick={() => setOpen(!open)}>
      <span className="ds-selector-label">
        {designSystem?.brandName || 'Design System'}
      </span>
      <span className="ds-selector-dots">
        {colorDots.map((c, i) => (
          <span key={i} className="ds-selector-dot" style={{ background: c }} />
        ))}
      </span>
      {open && (
        <div className="ds-selector-dropdown" onClick={(e) => e.stopPropagation()}>
          {designSystems.map((ds) => (
            <button
              key={ds.id}
              className={`ds-selector-option${ds.id === designSystem?.id ? ' active' : ''}`}
              onClick={() => { setDesignSystem(ds); setOpen(false); }}
            >
              <span className="ds-selector-option-colors">
                {Object.values(ds.colors).slice(0, 3).map((c, i) => (
                  <span key={i} className="ds-selector-dot" style={{ background: c }} />
                ))}
              </span>
              {ds.brandName || 'Unnamed'}
              {ds.isDefault && <span className="ds-selector-default-badge">default</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function PinnedElementTag() {
  const pinnedElement = useDesignStore((s) => s.pinnedElement);
  const clearPin = useDesignStore((s) => s.clearPin);
  if (!pinnedElement) return null;

  return (
    <div className="pinned-element-tag">
      <span className="pinned-element-icon">{'\ud83d\udccc'}</span>
      <span className="pinned-element-name">{pinnedElement.componentName || pinnedElement.tagName}</span>
      <button className="pinned-element-clear" onClick={clearPin} title="Remove pin">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

export default function DesignModeLayout() {
  const designSystem = useDesignStore((s) => s.designSystem);
  const designSystems = useDesignStore((s) => s.designSystems);
  const currentDesign = useDesignStore(selectCurrentDesign);
  const deactivate = useDesignStore((s) => s.deactivateDesignMode);
  const pinElement = useDesignStore((s) => s.pinElement);

  const dividerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftWidth, setLeftWidth] = useState(35);

  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    if (designSystems.length === 0 && !designSystem) {
      setShowOnboarding(true);
    }
  }, []);

  // Divider drag
  useEffect(() => {
    const divider = dividerRef.current;
    const container = containerRef.current;
    if (!divider || !container) return;

    let dragging = false;
    const onDown = (e: MouseEvent) => {
      dragging = true;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      const rect = container.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.min(60, Math.max(20, pct)));
    };
    const onUp = () => {
      if (dragging) {
        dragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    divider.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      divider.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  // Listen for element-pinned messages from Canvas iframe
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'springo:element-pinned') {
        pinElement(e.data.payload as PinnedElement);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [pinElement]);

  const handleTemplateSelect = useCallback((template: { prompt: string }) => {
    let sessionId = useSessionStore.getState().currentSessionId;
    if (!sessionId) sessionId = useSessionStore.getState().createSession();
    const settings = useSettingsStore.getState().settings;
    const ds = useDesignStore.getState().designSystem;
    useChatStore.getState().sendMessage(sessionId, template.prompt, [], {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId,
      designMode: true,
      designSystem: ds || undefined,
    });
  }, []);

  return (
    <div className="design-mode-layout" ref={containerRef}>
      {/* Top bar */}
      <div className="design-mode-topbar">
        <div className="design-mode-topbar-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span className="design-mode-title">Design Mode</span>
        </div>
        <div className="design-mode-topbar-right">
          <DesignSystemSelector />
          <button className="design-mode-close" onClick={deactivate} title="Exit design mode">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Main split */}
      <div className="design-mode-body">
        {/* Left: Chat */}
        <div className="design-mode-chat" style={{ width: `${leftWidth}%` }}>
          <div className="design-mode-chat-messages">
            <ChatArea />
          </div>
          <PinnedElementTag />
          <MessageInput />
        </div>

        {/* Divider */}
        <div className="design-mode-divider" ref={dividerRef} />

        {/* Right: Canvas */}
        <div className="design-mode-canvas" style={{ width: `${100 - leftWidth}%` }}>
          <div className="design-mode-canvas-area">
            <DesignCanvas design={currentDesign} viewport="desktop" onTemplateSelect={handleTemplateSelect} />
          </div>
          <DesignVersionTimeline />
        </div>
      </div>

      {/* DS Onboarding */}
      {showOnboarding && (
        <DesignSystemOnboarding onComplete={() => setShowOnboarding(false)} />
      )}
    </div>
  );
}
