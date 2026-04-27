/**
 * "Disposable chats" heuristic.
 *
 * Given the current session list + running runtimes, return the sessions that
 * look abandoned or never-used. Used by the sidebar cleanup banner and the
 * review modal to let users batch-delete without losing recent work.
 *
 * Rules (tuned conservative — false negatives are fine, false positives are not):
 *   - Never flag a session that is pinned, currently streaming, or created in
 *     the last GRACE_MS. These are the two classes of false positives the
 *     user reported: active session during first-message stream, and a blank
 *     one the user just opened.
 *   - "never_used":      no messages at all, older than GRACE_MS
 *   - "abandoned_new":   ≤ 1 real message, title still a default, older than 3d
 *   - "short_stale":     ≤ 2 messages, older than 14d
 *
 * Confidence scale: 'high' items are safe to delete without thinking;
 * 'medium' items usually fine; 'low' shown for review but unchecked by default.
 */

import type { Conversation, ConvRuntime } from '@/types';

export type SuggestionConfidence = 'high' | 'medium' | 'low';

export interface CleanupSuggestion {
  session: Conversation;
  reason: string;
  confidence: SuggestionConfidence;
  ageDays: number;
  messageCount: number;
}

const GRACE_MS = 5 * 60 * 1000;      // 5 minutes — newly created sessions are off-limits
const ABANDONED_MS = 3 * 24 * 3600 * 1000;  // 3 days
const STALE_MS = 14 * 24 * 3600 * 1000;     // 14 days

const DEFAULT_TITLES = new Set([
  'New Chat', 'New Design', 'New Plan', 'Team Chat',
  'Meeting Notes', 'Screen Recording', 'Untitled',
]);

function daysAgo(ts: number, now: number): number {
  return Math.floor((now - ts) / (24 * 3600 * 1000));
}

function messageCountFor(s: Conversation, runtimes: Record<string, ConvRuntime>): number {
  // Prefer runtime count if loaded (more authoritative — accounts for the
  // session the user is looking at right now). Fall back to backend count
  // loaded with the session list. Final fallback: 0 (trust nothing older).
  const runtime = runtimes[s.id];
  if (runtime && runtime.messages.length > 0) return runtime.messages.length;
  if (typeof s.messageCount === 'number') return s.messageCount;
  return 0;
}

export function getCleanupSuggestions(
  sessions: Conversation[],
  runtimes: Record<string, ConvRuntime>,
  now: number = Date.now(),
): CleanupSuggestion[] {
  const out: CleanupSuggestion[] = [];

  for (const s of sessions) {
    // Never touch pinned, currently streaming, or brand-new sessions.
    if (s.pinned) continue;
    if (runtimes[s.id]?.isStreaming) continue;
    const created = s.createdAt || 0;
    if (now - created < GRACE_MS) continue;

    const updated = s.updatedAt || created || 0;
    const ageMs = now - updated;
    const age = daysAgo(updated, now);
    const count = messageCountFor(s, runtimes);
    const titleLooksDefault = DEFAULT_TITLES.has(s.title) || !s.isCustomTitle;

    if (count === 0) {
      out.push({
        session: s,
        reason: 'Never used — no messages sent',
        confidence: 'high',
        ageDays: age,
        messageCount: 0,
      });
    } else if (count <= 2 && ageMs >= ABANDONED_MS && titleLooksDefault) {
      out.push({
        session: s,
        reason: `Abandoned — only ${count} message${count === 1 ? '' : 's'} and still titled "${s.title}"`,
        confidence: 'high',
        ageDays: age,
        messageCount: count,
      });
    } else if (count <= 2 && ageMs >= STALE_MS) {
      out.push({
        session: s,
        reason: `Short and stale — ${count} message${count === 1 ? '' : 's'}, ${age}d old`,
        confidence: 'medium',
        ageDays: age,
        messageCount: count,
      });
    } else if (count <= 4 && ageMs >= STALE_MS && titleLooksDefault) {
      out.push({
        session: s,
        reason: `Old default-titled chat — ${count} messages, ${age}d old`,
        confidence: 'low',
        ageDays: age,
        messageCount: count,
      });
    }
  }

  // Oldest first so the clearly-dead ones float to the top of the modal.
  out.sort((a, b) => (a.session.updatedAt || 0) - (b.session.updatedAt || 0));
  return out;
}

/**
 * Quick check used by the banner: how many high-confidence suggestions exist
 * that the user hasn't already dismissed.
 */
export function countActionableSuggestions(
  suggestions: CleanupSuggestion[],
  dismissedIds: ReadonlySet<string>,
): number {
  return suggestions.filter(
    (x) => x.confidence !== 'low' && !dismissedIds.has(x.session.id),
  ).length;
}
