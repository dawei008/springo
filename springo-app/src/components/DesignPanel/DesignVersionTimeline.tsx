/**
 * DesignVersionTimeline - horizontal version strip at the bottom
 */
import { useDesignStore } from '@/stores/designStore';

export default function DesignVersionTimeline() {
  const versions = useDesignStore((s) => s.versions);
  const activeVersionIndex = useDesignStore((s) => s.activeVersionIndex);
  const selectVersion = useDesignStore((s) => s.selectVersion);

  if (versions.length <= 1) return null;

  return (
    <div className="design-version-timeline">
      {versions.map((v, i) => (
        <button
          key={v.id}
          className={`design-version-item${i === activeVersionIndex ? ' active' : ''}`}
          onClick={() => selectVersion(i)}
          title={v.prompt || v.title}
        >
          <span className="design-version-num">v{i + 1}</span>
          <span className="design-version-title">{v.title}</span>
        </button>
      ))}
    </div>
  );
}
