import { useState, useEffect, useRef } from 'react';
import { useDesignStore } from '@/stores/designStore';
import { parseTweaks, type TweakParam } from './tweakParser';

export default function DesignTweaksPanel() {
  const tweaksOpen = useDesignStore((s) => s.tweaksOpen);
  const versions = useDesignStore((s) => s.versions);
  const activeVersionIndex = useDesignStore((s) => s.activeVersionIndex);
  const [tweaks, setTweaks] = useState<TweakParam[]>([]);
  const initialRef = useRef<Map<string, string>>(new Map());

  const currentDesign = activeVersionIndex >= 0 && activeVersionIndex < versions.length
    ? versions[activeVersionIndex] : null;

  useEffect(() => {
    if (!currentDesign) { setTweaks([]); return; }
    const allCss = (currentDesign.files || [])
      .filter(f => f.type === 'css')
      .map(f => f.content)
      .join('\n');

    const html = currentDesign.html || '';
    const styleMatches = html.match(/<style[^>]*>[\s\S]*?<\/style>/gi) || [];
    const inlineCss = styleMatches.map(m => m.replace(/<\/?style[^>]*>/gi, '')).join('\n');

    const parsed = parseTweaks(allCss + '\n' + inlineCss);
    setTweaks(parsed);

    const initial = new Map<string, string>();
    parsed.forEach(t => initial.set(t.id, t.value));
    initialRef.current = initial;
  }, [currentDesign?.id]);

  const applyToIframe = (cssVar: string, value: string) => {
    const iframe = document.querySelector('.design-canvas-iframe') as HTMLIFrameElement | null;
    try {
      iframe?.contentWindow?.postMessage({ type: 'springo:set-css-var', name: cssVar, value }, '*');
    } catch { /* cross-origin */ }
  };

  const handleChange = (id: string, value: string) => {
    setTweaks(prev => prev.map(t => {
      if (t.id !== id) return t;
      const updated = { ...t, value };
      const cssVal = t.type === 'range' ? `${value}${t.unit || 'px'}` : value;
      applyToIframe(t.cssVar, cssVal);
      return updated;
    }));
  };

  const handleReset = () => {
    setTweaks(prev => prev.map(t => {
      const original = initialRef.current.get(t.id) || t.value;
      const cssVal = t.type === 'range' ? `${original}${t.unit || 'px'}` : original;
      applyToIframe(t.cssVar, cssVal);
      return { ...t, value: original };
    }));
  };

  if (!tweaksOpen || tweaks.length === 0) return null;

  return (
    <div className="design-tweaks-panel">
      <div className="design-tweaks-header">
        <span>Tweaks</span>
        <button onClick={handleReset} title="Reset all">Reset</button>
      </div>
      <div className="design-tweaks-list">
        {tweaks.map(t => (
          <div key={t.id} className="design-tweak-item">
            <label className="design-tweak-label">{t.label}</label>
            {t.type === 'color' && (
              <input
                type="color"
                value={t.value}
                onChange={e => handleChange(t.id, e.target.value)}
                className="design-tweak-color"
              />
            )}
            {t.type === 'range' && (
              <div className="design-tweak-range-row">
                <input
                  type="range"
                  min={t.min}
                  max={t.max}
                  value={t.value}
                  onChange={e => handleChange(t.id, e.target.value)}
                  className="design-tweak-range"
                />
                <span className="design-tweak-range-val">{t.value}{t.unit}</span>
              </div>
            )}
            {t.type === 'select' && (
              <select
                value={t.value}
                onChange={e => handleChange(t.id, e.target.value)}
                className="design-tweak-select"
              >
                {(t.options || []).map(o => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
