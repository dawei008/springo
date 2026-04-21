import { useDesignStore } from '@/stores/designStore';

export default function DesignElementPopover() {
  const selectedElement = useDesignStore((s) => s.selectedElement);
  const clearSelection = () => useDesignStore.getState().selectElement(null);

  if (!selectedElement) return null;

  const { tagName, id, className, textPreview, computedStyles, cssPath } = selectedElement;

  const label = [
    tagName,
    id ? `#${id}` : '',
    className ? `.${className.split(/\s+/).slice(0, 2).join('.')}` : '',
  ].filter(Boolean).join('');

  return (
    <div className="design-element-popover">
      <div className="design-element-popover-header">
        <code className="design-element-tag">{label}</code>
        <button className="design-element-popover-close" onClick={clearSelection}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {textPreview && (
        <div className="design-element-text">"{textPreview.length > 50 ? textPreview.slice(0, 50) + '...' : textPreview}"</div>
      )}

      {computedStyles && (
        <div className="design-element-styles">
          {Object.entries(computedStyles).filter(([, v]) => v && v !== 'normal' && v !== 'none' && v !== '0px').map(([k, v]) => (
            <div key={k} className="design-element-style-row">
              <span className="design-element-style-key">{k}</span>
              <span className="design-element-style-val">{v}</span>
            </div>
          ))}
        </div>
      )}

      <div className="design-element-path">
        <code>{cssPath}</code>
      </div>

      <div className="design-element-hint">
        Type a message to edit this element
      </div>
    </div>
  );
}
