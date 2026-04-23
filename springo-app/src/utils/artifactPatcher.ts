import type { ArtifactFile } from '@/stores/unifiedArtifactStore';

type ArtifactFileType = ArtifactFile['type'];

// ── Types ──────────────────────────────────────────────────────

export type PatchAction = 'replace' | 'create' | 'delete';

export interface FilePatch {
  path: string;
  action: PatchAction;
  content: string;
  fileType: ArtifactFileType;
}

export interface DesignPatch {
  files: FilePatch[];
  artifactId?: string;
}

// ── Helpers ────────────────────────────────────────────────────

function inferFileType(path: string): ArtifactFileType {
  const ext = path.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'jsx':
    case 'tsx':
      return 'jsx';
    case 'css':
      return 'css';
    case 'html':
      return 'html';
    case 'json':
      return 'json';
    default:
      return 'text';
  }
}

const VALID_ACTIONS: PatchAction[] = ['replace', 'create', 'delete'];

function isValidAction(value: string): value is PatchAction {
  return VALID_ACTIONS.includes(value as PatchAction);
}

// ── Public API ─────────────────────────────────────────────────

/**
 * Quick check whether the raw string contains a `<springo-patch>` block.
 */
export function hasPatch(raw: string): boolean {
  return raw.includes('<springo-patch>');
}

/**
 * Parse `<springo-patch>` XML from a raw AI response string.
 * Returns `null` when no patch block is found.
 */
export function parsePatch(raw: string): DesignPatch | null {
  const patchMatch = raw.match(/<springo-patch(\s[^>]*)?>(([\s\S]*?))<\/springo-patch>/);
  if (!patchMatch) return null;

  const attrsStr = patchMatch[1] || '';
  const artifactIdMatch = attrsStr.match(/artifact="([^"]*)"/);
  const artifactId = artifactIdMatch?.[1] || undefined;

  const patchBody = patchMatch[2];

  const fileRegex =
    /<springo-file\s+([^>]*)>([\s\S]*?)<\/springo-file>/g;

  const files: FilePatch[] = [];
  let m: RegExpExecArray | null;

  while ((m = fileRegex.exec(patchBody)) !== null) {
    const attrsStr = m[1];
    const innerContent = m[2];

    // Extract path attribute
    const pathMatch = attrsStr.match(/path="([^"]*)"/);
    if (!pathMatch) continue; // path is required
    const path = pathMatch[1];

    // Extract action attribute (default: 'replace')
    const actionMatch = attrsStr.match(/action="([^"]*)"/);
    const actionRaw = actionMatch ? actionMatch[1] : 'replace';
    const action: PatchAction = isValidAction(actionRaw) ? actionRaw : 'replace';

    // Trim leading/trailing newline from content (preserve internal whitespace)
    const content = innerContent.replace(/^\n/, '').replace(/\n$/, '');

    files.push({
      path,
      action,
      content,
      fileType: inferFileType(path),
    });
  }

  return { files, artifactId };
}

export interface ArtifactAction {
  artifactId?: string;
  payload: Record<string, unknown>;
}

export function hasAction(raw: string): boolean {
  return raw.includes('<springo-action');
}

export function parseAction(raw: string): ArtifactAction | null {
  const match = raw.match(/<springo-action(\s[^>]*)?>(([\s\S]*?))<\/springo-action>/);
  if (!match) return null;

  const attrsStr = match[1] || '';
  const artifactIdMatch = attrsStr.match(/artifact="([^"]*)"/);
  const artifactId = artifactIdMatch?.[1] || undefined;

  const body = match[2].trim();
  try {
    const payload = JSON.parse(body);
    return { artifactId, payload };
  } catch {
    return null;
  }
}

