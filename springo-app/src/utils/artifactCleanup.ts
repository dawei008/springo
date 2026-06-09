/**
 * "Disposable apps" heuristic, mirroring `cleanupSuggestions.ts` for chats.
 *
 * Surfaces artifacts (apps) that look abandoned — orphaned (no parent
 * session), still on a template default name, or a long-stale empty shell —
 * so the user can batch-delete them without losing recent work.
 *
 * Rules (conservative — false positives are worse than false negatives):
 *   - Never flag a pinned, internal-component, or live (currently being
 *     built) artifact, or one created in the last GRACE_MS.
 *   - "empty_shell":   no files at all, older than GRACE_MS
 *   - "untouched_template": orphan (no current session), default template
 *     name, older than 3d
 *   - "stale_orphan":  orphan, older than 14d
 *
 * Confidence: 'high' is safe to delete; 'medium' usually fine; 'low' shown
 * but unchecked by default in the modal.
 */

import type { Artifact } from '@/stores/unifiedArtifactStore';

export type ArtifactSuggestionConfidence = 'high' | 'medium' | 'low';

export interface ArtifactCleanupSuggestion {
  artifact: Artifact;
  reason: string;
  confidence: ArtifactSuggestionConfidence;
  ageDays: number;
  fileCount: number;
}

const GRACE_MS = 5 * 60 * 1000;             // 5 minutes — just-created
const RECENT_MS = 60 * 60 * 1000;            // 1 hour — touched recently
const ABANDONED_MS = 24 * 3600 * 1000;       // 1 day
const STALE_MS = 7 * 24 * 3600 * 1000;       // 7 days

/** Names baked into ARTIFACT_TEMPLATES — used to detect "user never renamed". */
export const DEFAULT_ARTIFACT_NAMES: ReadonlySet<string> = new Set([
  'Counter App', 'Dashboard', 'Todo App', 'Landing Page', 'Form Builder',
]);

function daysAgo(ts: number, now: number): number {
  return Math.floor((now - ts) / (24 * 3600 * 1000));
}

export function getArtifactCleanupSuggestions(
  artifacts: Record<string, Artifact>,
  sessionArtifactIds: ReadonlyArray<string>,
  now: number = Date.now(),
): ArtifactCleanupSuggestion[] {
  const sessionSet = new Set(sessionArtifactIds);
  const out: ArtifactCleanupSuggestion[] = [];

  // Build a name → [artifact ids] index so we can flag duplicates. Skip
  // pinned / internal / live ones from the count so a kept-around artifact
  // doesn't get its sibling auto-flagged.
  const byName = new Map<string, Artifact[]>();
  for (const a of Object.values(artifacts)) {
    if (!a || a.pinned || a.internalComponent || a.live) continue;
    const list = byName.get(a.name) ?? [];
    list.push(a);
    byName.set(a.name, list);
  }
  // Within each duplicate group, keep the most-recently-updated one (assume
  // it's the "live" copy) and flag the older ones.
  const dupOlderIds = new Set<string>();
  for (const list of byName.values()) {
    if (list.length < 2) continue;
    const sorted = [...list].sort((x, y) => (y.updatedAt || 0) - (x.updatedAt || 0));
    for (const a of sorted.slice(1)) dupOlderIds.add(a.id);
  }

  for (const a of Object.values(artifacts)) {
    if (!a) continue;
    if (a.pinned) continue;
    if (a.internalComponent) continue;
    if (a.live) continue;
    const created = a.createdAt || 0;
    if (now - created < GRACE_MS) continue;

    const updated = a.updatedAt || created || 0;
    const ageMs = now - updated;
    const age = daysAgo(updated, now);
    const fileCount = a.files?.length ?? 0;
    const isOrphan = !sessionSet.has(a.id);
    const nameLooksDefault = DEFAULT_ARTIFACT_NAMES.has(a.name);
    const isOlderDup = dupOlderIds.has(a.id);

    const add = (reason: string, confidence: ArtifactSuggestionConfidence) => {
      out.push({ artifact: a, reason, confidence, ageDays: age, fileCount });
    };
    // Skip anything still being actively edited (orphan or not). Anything
    // older than that is fair game.
    if (ageMs < RECENT_MS) continue;

    if (fileCount === 0) {
      add('Empty shell — no files', 'high');
    } else if (isOlderDup) {
      // Older copy of a duplicate-named artifact — almost certainly leftover
      // from earlier iterations of the same prompt.
      add(`Older duplicate of "${a.name}"`, 'high');
    } else if (isOrphan && nameLooksDefault) {
      // Orphan still on a template default name → user never customized it.
      add(`Untouched template — still named "${a.name}"`, 'high');
    } else if (isOrphan && ageMs >= STALE_MS) {
      add(`Old orphan — ${age}d since last edit`, 'high');
    } else if (isOrphan && ageMs >= ABANDONED_MS) {
      add(`Orphan — ${age}d since last edit`, 'medium');
    } else if (isOrphan) {
      add(`Orphan from earlier session`, 'low');
    }
  }

  out.sort((a, b) => (a.artifact.updatedAt || 0) - (b.artifact.updatedAt || 0));
  return out;
}

export function countActionableArtifactSuggestions(
  suggestions: ArtifactCleanupSuggestion[],
  dismissedIds: ReadonlySet<string>,
): number {
  return suggestions.filter(
    (x) => x.confidence !== 'low' && !dismissedIds.has(x.artifact.id),
  ).length;
}
