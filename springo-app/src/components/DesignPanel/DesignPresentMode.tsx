import { useEffect, useRef } from 'react';
import { useDesignStore, selectCurrentDesign } from '@/stores/designStore';
import DesignCanvas from './DesignCanvas';

export default function DesignPresentMode() {
  const presentMode = useDesignStore((s) => s.presentMode);
  const setPresentMode = useDesignStore((s) => s.setPresentMode);
  const currentDesign = useDesignStore(selectCurrentDesign);
  const viewport = useDesignStore((s) => s.viewport);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!presentMode) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setPresentMode(false);
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [presentMode, setPresentMode]);

  if (!presentMode || !currentDesign) return null;

  return (
    <div className="design-present-overlay" ref={overlayRef}>
      <div className="design-present-canvas">
        <DesignCanvas design={currentDesign} viewport={viewport} />
      </div>
      <button
        className="design-present-exit"
        onClick={() => setPresentMode(false)}
        title="Exit presentation (Esc)"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/>
        </svg>
        <span>Exit</span>
      </button>
    </div>
  );
}
