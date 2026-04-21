import { useState } from 'react';
import { useDesignStore } from '@/stores/designStore';

export default function DesignVerificationBadge() {
  const errors = useDesignStore((s) => s.errors);
  const status = useDesignStore((s) => s.verificationStatus);
  const clearErrors = useDesignStore((s) => s.clearErrors);
  const [expanded, setExpanded] = useState(false);

  if (status === 'ok' && errors.length === 0) {
    return (
      <div className="design-verification-badge ok" title="No errors">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
    );
  }

  return (
    <div className="design-verification-badge-container">
      <button
        className={`design-verification-badge ${status}`}
        onClick={() => setExpanded(!expanded)}
        title={`${errors.length} error${errors.length !== 1 ? 's' : ''}`}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>{errors.length}</span>
      </button>

      {expanded && (
        <div className="design-verification-dropdown">
          <div className="design-verification-header">
            <span>Errors ({errors.length})</span>
            <button onClick={() => { clearErrors(); setExpanded(false); }}>Clear</button>
          </div>
          <div className="design-verification-list">
            {errors.slice(-10).reverse().map((err, i) => (
              <div key={i} className={`design-verification-item ${err.type}`}>
                <span className="design-verification-type">{err.type}</span>
                <span className="design-verification-msg">{err.message.length > 120 ? err.message.slice(0, 120) + '...' : err.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
