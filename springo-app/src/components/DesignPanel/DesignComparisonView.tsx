import { useState } from 'react';
import { useDesignStore } from '@/stores/designStore';
import DesignCanvas from './DesignCanvas';

export default function DesignComparisonView() {
  const versions = useDesignStore((s) => s.versions);
  const viewport = useDesignStore((s) => s.viewport);
  const [leftIdx, setLeftIdx] = useState(Math.max(0, versions.length - 2));
  const [rightIdx, setRightIdx] = useState(versions.length - 1);

  if (versions.length < 2) {
    return (
      <div className="design-comparison-empty">
        Need at least 2 versions to compare. Ask for variations!
      </div>
    );
  }

  return (
    <div className="design-comparison-view">
      <div className="design-comparison-pane">
        <div className="design-comparison-pane-header">
          <select
            value={leftIdx}
            onChange={e => setLeftIdx(Number(e.target.value))}
            className="design-comparison-select"
          >
            {versions.map((v, i) => (
              <option key={v.id} value={i}>v{i + 1} — {v.title}</option>
            ))}
          </select>
        </div>
        <div className="design-comparison-pane-body">
          <DesignCanvas design={versions[leftIdx]} viewport={viewport} />
        </div>
      </div>
      <div className="design-comparison-divider" />
      <div className="design-comparison-pane">
        <div className="design-comparison-pane-header">
          <select
            value={rightIdx}
            onChange={e => setRightIdx(Number(e.target.value))}
            className="design-comparison-select"
          >
            {versions.map((v, i) => (
              <option key={v.id} value={i}>v{i + 1} — {v.title}</option>
            ))}
          </select>
        </div>
        <div className="design-comparison-pane-body">
          <DesignCanvas design={versions[rightIdx]} viewport={viewport} />
        </div>
      </div>
    </div>
  );
}
