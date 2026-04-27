/**
 * Cleanup suggestions modal.
 *
 * Replaces the old auto-collapsed "empty chats" fold. Chats stay fully
 * visible in the sidebar; a background pass flags the abandoned ones and
 * surfaces them here for batch deletion. The user is always in the loop.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CleanupSuggestion, SuggestionConfidence } from '@/utils/cleanupSuggestions';

interface Props {
  suggestions: CleanupSuggestion[];
  onDelete: (ids: string[]) => Promise<void> | void;
  /** Called when the user dismisses an id without deleting, so the banner
   * doesn't nag until something new qualifies. */
  onDismissIds: (ids: string[]) => void;
  onClose: () => void;
}

const CONFIDENCE_ORDER: Record<SuggestionConfidence, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

const CONFIDENCE_LABEL: Record<SuggestionConfidence, string> = {
  high: 'Safe to delete',
  medium: 'Probably OK',
  low: 'Check first',
};

export default function CleanupModal({ suggestions, onDelete, onDismissIds, onClose }: Props) {
  const sorted = useMemo(
    () => [...suggestions].sort(
      (a, b) => CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence],
    ),
    [suggestions],
  );

  // Default-select only high-confidence items. Medium/low require an opt-in.
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(sorted.filter((s) => s.confidence === 'high').map((s) => s.session.id)),
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const toggleOne = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(sorted.map((s) => s.session.id)));
  }, [sorted]);

  const clearAll = useCallback(() => setSelected(new Set()), []);

  const handleApply = useCallback(async () => {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    setBusy(true);
    try {
      await onDelete(ids);
      onClose();
    } finally {
      setBusy(false);
    }
  }, [selected, onDelete, onClose]);

  const handleSkipAll = useCallback(() => {
    // Dismiss every id currently shown so the banner stops suggesting them
    // until something new qualifies.
    onDismissIds(sorted.map((s) => s.session.id));
    onClose();
  }, [sorted, onDismissIds, onClose]);

  return (
    <div className="cleanup-modal-backdrop" onClick={onClose}>
      <div className="cleanup-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="cleanup-modal-header">
          <div>
            <h2>Clean up disposable chats</h2>
            <p className="cleanup-modal-subtitle">
              {sorted.length} chat{sorted.length === 1 ? '' : 's'} look unused.
              Pin or rename a chat to keep it off this list.
            </p>
          </div>
          <button className="cleanup-modal-close" onClick={onClose} aria-label="Close" title="Close (Esc)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="cleanup-modal-toolbar">
          <span className="cleanup-modal-count">
            {selected.size} of {sorted.length} selected
          </span>
          <div className="cleanup-modal-spacer" />
          <button className="cleanup-link-btn" onClick={selectAll}>Select all</button>
          <button className="cleanup-link-btn" onClick={clearAll}>Clear</button>
        </div>

        <ul className="cleanup-modal-list">
          {sorted.map(({ session, reason, confidence, messageCount, ageDays }) => {
            const checked = selected.has(session.id);
            return (
              <li key={session.id} className={`cleanup-item conf-${confidence}${checked ? ' selected' : ''}`}>
                <label className="cleanup-item-row">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleOne(session.id)}
                  />
                  <div className="cleanup-item-body">
                    <div className="cleanup-item-title" title={session.title}>
                      {session.title || '(untitled)'}
                    </div>
                    <div className="cleanup-item-meta">
                      <span className={`cleanup-badge conf-${confidence}`}>{CONFIDENCE_LABEL[confidence]}</span>
                      <span className="cleanup-item-reason">{reason}</span>
                      <span className="cleanup-item-stats">· {messageCount} msg · {ageDays}d old</span>
                    </div>
                  </div>
                </label>
              </li>
            );
          })}
        </ul>

        <footer className="cleanup-modal-footer">
          <button className="cleanup-btn ghost" onClick={handleSkipAll} disabled={busy}>
            Skip all for now
          </button>
          <div className="cleanup-modal-spacer" />
          <button className="cleanup-btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            className="cleanup-btn primary danger"
            onClick={handleApply}
            disabled={busy || selected.size === 0}
          >
            {busy ? 'Deleting…' : `Delete ${selected.size} chat${selected.size === 1 ? '' : 's'}`}
          </button>
        </footer>
      </div>
    </div>
  );
}
