import type { DesignFile, DesignFileType } from '@/types';

// ── Types ──────────────────────────────────────────────────────

export type PatchAction = 'replace' | 'create' | 'delete';

export interface FilePatch {
  path: string;
  action: PatchAction;
  content: string;
  fileType: DesignFileType;
}

export interface DesignPatch {
  files: FilePatch[];
}

// ── Helpers ────────────────────────────────────────────────────

function inferFileType(path: string): DesignFileType {
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
  const patchMatch = raw.match(/<springo-patch>([\s\S]*?)<\/springo-patch>/);
  if (!patchMatch) return null;

  const patchBody = patchMatch[1];

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

  return { files };
}

/**
 * Apply a `DesignPatch` to an existing array of `DesignFile`s and return
 * a new array reflecting the patch operations.
 */
export function applyPatchToFiles(
  currentFiles: DesignFile[],
  patch: DesignPatch,
): DesignFile[] {
  const result = currentFiles.map((f) => ({ ...f }));

  for (const fp of patch.files) {
    switch (fp.action) {
      case 'replace': {
        const idx = result.findIndex((f) => f.path === fp.path);
        if (idx !== -1) {
          result[idx] = { path: fp.path, type: fp.fileType, content: fp.content };
        } else {
          // Not found — treat as create
          result.push({ path: fp.path, type: fp.fileType, content: fp.content });
        }
        break;
      }
      case 'create': {
        result.push({ path: fp.path, type: fp.fileType, content: fp.content });
        break;
      }
      case 'delete': {
        const idx = result.findIndex((f) => f.path === fp.path);
        if (idx !== -1) {
          result.splice(idx, 1);
        }
        break;
      }
    }
  }

  return result;
}
