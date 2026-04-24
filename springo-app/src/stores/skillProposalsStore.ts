import { create } from 'zustand';

const BASE_URL = 'http://127.0.0.1:8081';

export interface SkillProposal {
  id: string;
  slug: string;
  title: string;
  trigger: string;
  skill_md: string;
  source_session_id: string;
  created_at: string;
  status: 'pending' | 'approved' | 'rejected';
  approved_skill_dir?: string;
}

interface State {
  pending: SkillProposal[];
  dismissedIds: Set<string>;
  selectedId: string | null;
  loading: boolean;
  lastFetchedAt: number;

  fetchPending: () => Promise<void>;
  openReview: (id: string) => void;
  closeReview: () => void;
  dismiss: (id: string) => void;
  approve: (id: string, editedSkillMd?: string) => Promise<boolean>;
  reject: (id: string) => Promise<boolean>;
}

const DISMISSED_KEY = 'springo-proposal-dismissed';
const POLL_INTERVAL_MS = 60_000;

function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>): void {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // ignore quota errors
  }
}

export const useSkillProposalsStore = create<State>((set, get) => ({
  pending: [],
  dismissedIds: loadDismissed(),
  selectedId: null,
  loading: false,
  lastFetchedAt: 0,

  fetchPending: async () => {
    if (get().loading) return;
    set({ loading: true });
    try {
      const res = await fetch(`${BASE_URL}/v1/skill-proposals?status=pending`);
      if (!res.ok) return;
      const data = await res.json();
      const proposals = (data.proposals || []) as SkillProposal[];
      set({ pending: proposals, lastFetchedAt: Date.now() });
    } catch {
      // network failure — keep previous state
    } finally {
      set({ loading: false });
    }
  },

  openReview: (id) => set({ selectedId: id }),
  closeReview: () => set({ selectedId: null }),

  dismiss: (id) => {
    const next = new Set(get().dismissedIds);
    next.add(id);
    saveDismissed(next);
    set({ dismissedIds: next });
  },

  approve: async (id, editedSkillMd) => {
    try {
      const res = await fetch(`${BASE_URL}/v1/skill-proposals/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedSkillMd !== undefined ? { skill_md: editedSkillMd } : {}),
      });
      if (!res.ok) return false;
      set((s) => ({
        pending: s.pending.filter((p) => p.id !== id),
        selectedId: s.selectedId === id ? null : s.selectedId,
      }));
      return true;
    } catch {
      return false;
    }
  },

  reject: async (id) => {
    try {
      const res = await fetch(`${BASE_URL}/v1/skill-proposals/${id}/reject`, {
        method: 'POST',
      });
      if (!res.ok) return false;
      set((s) => ({
        pending: s.pending.filter((p) => p.id !== id),
        selectedId: s.selectedId === id ? null : s.selectedId,
      }));
      return true;
    } catch {
      return false;
    }
  },
}));

// Poll on an interval when the app is mounted.
let _pollTimer: ReturnType<typeof setInterval> | null = null;
export function startSkillProposalsPolling(): void {
  if (_pollTimer) return;
  useSkillProposalsStore.getState().fetchPending();
  _pollTimer = setInterval(() => {
    useSkillProposalsStore.getState().fetchPending();
  }, POLL_INTERVAL_MS);
}

export function stopSkillProposalsPolling(): void {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

/** Returns the first proposal the user hasn't dismissed yet, or null. */
export function selectVisibleProposal(state: State): SkillProposal | null {
  return state.pending.find((p) => !state.dismissedIds.has(p.id)) || null;
}
