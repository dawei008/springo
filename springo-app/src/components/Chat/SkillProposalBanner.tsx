import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  useSkillProposalsStore,
  selectVisibleProposal,
  startSkillProposalsPolling,
  stopSkillProposalsPolling,
  type SkillProposal,
} from '@/stores/skillProposalsStore';
import { useSettingsStore } from '@/stores/settingsStore';

function SparkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}

function SkillProposalDrawer({ proposal }: { proposal: SkillProposal }) {
  const closeReview = useSkillProposalsStore((s) => s.closeReview);
  const approve = useSkillProposalsStore((s) => s.approve);
  const reject = useSkillProposalsStore((s) => s.reject);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(proposal.skill_md);
  const [busy, setBusy] = useState(false);

  const handleApprove = useCallback(async () => {
    setBusy(true);
    const ok = await approve(proposal.id, editing ? draft : undefined);
    setBusy(false);
    if (!ok) alert('Failed to approve — the target skill directory may already exist.');
  }, [approve, proposal.id, editing, draft]);

  const handleReject = useCallback(async () => {
    setBusy(true);
    await reject(proposal.id);
    setBusy(false);
  }, [reject, proposal.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeReview(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closeReview]);

  return (
    <div className="skill-proposal-drawer" role="dialog" aria-modal="true">
      <div className="skill-proposal-backdrop" onClick={closeReview} />
      <div className="skill-proposal-panel">
        <header className="skill-proposal-panel-header">
          <div className="skill-proposal-panel-title">
            <SparkIcon />
            <span>{proposal.title}</span>
          </div>
          <button className="skill-proposal-close" onClick={closeReview} title="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="skill-proposal-meta">
          <span className="skill-proposal-slug">{proposal.slug}</span>
          <span className="skill-proposal-trigger">{proposal.trigger}</span>
        </div>

        <div className="skill-proposal-body">
          {editing ? (
            <textarea
              className="skill-proposal-editor"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
            />
          ) : (
            <pre className="skill-proposal-preview">{draft}</pre>
          )}
        </div>

        <footer className="skill-proposal-actions">
          <button className="skill-proposal-btn ghost" onClick={handleReject} disabled={busy}>
            Reject
          </button>
          <button
            className="skill-proposal-btn ghost"
            onClick={() => setEditing((v) => !v)}
            disabled={busy}
          >
            {editing ? 'Preview' : 'Edit'}
          </button>
          <button className="skill-proposal-btn primary" onClick={handleApprove} disabled={busy}>
            {editing ? 'Approve edits' : 'Approve'}
          </button>
        </footer>
      </div>
    </div>
  );
}

export default function SkillProposalBanner() {
  const enabled = useSettingsStore(
    (s) => s.settings.skillProposalsEnabled !== false,
  );
  const pending = useSkillProposalsStore((s) => s.pending);
  const dismissedIds = useSkillProposalsStore((s) => s.dismissedIds);
  const selectedId = useSkillProposalsStore((s) => s.selectedId);
  const openReview = useSkillProposalsStore((s) => s.openReview);
  const dismiss = useSkillProposalsStore((s) => s.dismiss);

  useEffect(() => {
    if (enabled) {
      startSkillProposalsPolling();
      return () => stopSkillProposalsPolling();
    }
    stopSkillProposalsPolling();
    return undefined;
  }, [enabled]);

  const visible = useMemo(
    () => selectVisibleProposal({ pending, dismissedIds } as never),
    [pending, dismissedIds],
  );
  const selected = useMemo(
    () => (selectedId ? pending.find((p) => p.id === selectedId) : null) ?? null,
    [selectedId, pending],
  );

  if (!enabled) return null;

  return (
    <>
      {visible && (
        <div className="skill-proposal-banner">
          <div className="skill-proposal-banner-icon"><SparkIcon /></div>
          <div className="skill-proposal-banner-text">
            <div className="skill-proposal-banner-title">Skill proposal: {visible.title}</div>
            <div className="skill-proposal-banner-trigger">{visible.trigger}</div>
          </div>
          <button
            className="skill-proposal-btn primary small"
            onClick={() => openReview(visible.id)}
          >
            Review
          </button>
          <button
            className="skill-proposal-banner-dismiss"
            onClick={() => dismiss(visible.id)}
            title="Dismiss (won't delete the proposal)"
          >
            <CloseIcon />
          </button>
        </div>
      )}
      {selected && <SkillProposalDrawer proposal={selected} />}
    </>
  );
}
