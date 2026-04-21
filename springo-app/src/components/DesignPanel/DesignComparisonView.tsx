import { useState, useEffect } from 'react';
import { useDesignStore } from '@/stores/designStore';
import type { DesignVersion, } from '@/types';
import type { ViewportMode } from '@/stores/designStore';
import DesignCanvas from './DesignCanvas';

function ComparisonPane({
  idx, setIdx, versions, viewport,
}: {
  idx: number;
  setIdx: (i: number) => void;
  versions: DesignVersion[];
  viewport: ViewportMode;
}) {
  return (
    <div className="design-comparison-pane">
      <div className="design-comparison-pane-header">
        <select
          value={idx}
          onChange={e => setIdx(Number(e.target.value))}
          className="design-comparison-select"
        >
          {versions.map((v, i) => (
            <option key={v.id} value={i}>v{i + 1} — {v.title}</option>
          ))}
        </select>
      </div>
      <div className="design-comparison-pane-body">
        <DesignCanvas design={versions[idx]} viewport={viewport} />
      </div>
    </div>
  );
}

export default function DesignComparisonView() {
  const versions = useDesignStore((s) => s.versions);
  const viewport = useDesignStore((s) => s.viewport);
  const [leftIdx, setLeftIdx] = useState(Math.max(0, versions.length - 2));
  const [rightIdx, setRightIdx] = useState(versions.length - 1);

  useEffect(() => {
    const max = versions.length - 1;
    if (leftIdx > max) setLeftIdx(Math.max(0, max));
    if (rightIdx > max) setRightIdx(max);
  }, [versions.length]);

  if (versions.length < 2) {
    return (
      <div className="design-comparison-empty">
        Need at least 2 versions to compare. Ask for variations!
      </div>
    );
  }

  return (
    <div className="design-comparison-view">
      <ComparisonPane idx={leftIdx} setIdx={setLeftIdx} versions={versions} viewport={viewport} />
      <div className="design-comparison-divider" />
      <ComparisonPane idx={rightIdx} setIdx={setRightIdx} versions={versions} viewport={viewport} />
    </div>
  );
}
