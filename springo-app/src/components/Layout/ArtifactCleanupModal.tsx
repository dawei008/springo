/**
 * Disposable-apps cleanup modal. Mirrors `CleanupModal` (chats) but operates
 * on artifacts: empty shells, untouched templates, stale orphans.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ArtifactCleanupSuggestion, ArtifactSuggestionConfidence } from '@/utils/artifactCleanup';

interface Props {
  suggestions: ArtifactCleanupSuggestion[];
  onDelete: (ids: string[]) => Promise<void> | void;
  onDismissIds: (ids: string[]) => void;
  onClose: () => void;
}

const CONFIDENCE_ORDER: Record<ArtifactSuggestionConfidence, number> = {
  high: 0, medium: 1, low: 2,
};

const CONFIDENCE_LABEL: Record<ArtifactSuggestionConfidence, string> = {
  high: 'Safe to delete',
  medium: 'Probably OK',
  low: 'Check first',
};

export default function ArtifactCleanupModal({ suggestions, onDelete, onDismissIds, onClose }: Props) {
  const sorted = useMemo(
    () => [...suggestions].sort(
      (a, b) => CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence],
    ),
    [suggestions],
  );

  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(sorted.filter((s) => s.confidence === 'high').map((s) => s.artifact.id)),
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
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(sorted.map((s) => s.artifact.id)));
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
    onDismissIds(sorted.map((s) => s.artifact.id));
    onClose();
  }, [sorted, onDismissIds, onClose]);

  return (
    <div className="cleanup-modal-backdrop" onClick={onClose}>
      <div className="cleanup-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="cleanup-modal-header">
          <div>
            <h2>Clean up disposable apps</h2>
            <p className="cleanup-modal-subtitle">
              {sorted.length} app{sorted.length === 1 ? '' : 's'} look unused.
              Pin or rename an app to keep it off this list.
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
          {sorted.map(({ artifact, reason, confidence, fileCount, ageDays }) => {
            const checked = selected.has(artifact.id);
            return (
              <li key={artifact.id} className={`cleanup-item conf-${confidence}${checked ? ' selected' : ''}`}>
                <label className="cleanup-item-row">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleOne(artifact.id)}
                  />
                  <div className="cleanup-item-body">
                    <div className="cleanup-item-title" title={artifact.name}>
                      {artifact.name || '(untitled)'}
                    </div>
                    <div className="cleanup-item-meta">
                      <span className={`cleanup-badge conf-${confidence}`}>{CONFIDENCE_LABEL[confidence]}</span>
                      <span className="cleanup-item-reason">{reason}</span>
                      <span className="cleanup-item-stats">· {fileCount} file{fileCount === 1 ? '' : 's'} · {ageDays}d old</span>
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
            {busy ? 'Deleting…' : `Delete ${selected.size} app${selected.size === 1 ? '' : 's'}`}
          </button>
        </footer>
      </div>
    </div>
  );
}
