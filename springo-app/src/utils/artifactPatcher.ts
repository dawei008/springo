import type { ArtifactFile } from '@/stores/unifiedArtifactStore';

type ArtifactFileType = ArtifactFile['type'];

// ── Types ──────────────────────────────────────────────────────

export type FileAction = 'replace' | 'create' | 'delete';
export type ArtifactOp = 'create' | 'patch' | 'action' | 'delete';

export interface FilePatch {
  path: string;
  action: FileAction;
  content: string;
  fileType: ArtifactFileType;
}

export interface CreateOp {
  op: 'create';
  id?: string;
  artifactType: 'app' | 'component' | 'document' | 'template';
  title: string;
  icon?: string;
  files: FilePatch[];
}

export interface PatchOp {
  op: 'patch';
  id: string;
  files: FilePatch[];
}

export interface ActionOp {
  op: 'action';
  id: string;
  payload: Record<string, unknown>;
}

export interface DeleteOp {
  op: 'delete';
  id: string;
}

export type ParsedArtifactOp = CreateOp | PatchOp | ActionOp | DeleteOp;

// ── Helpers ────────────────────────────────────────────────────

function inferFileType(path: string, typeAttr: string = ''): ArtifactFileType {
  if (typeAttr.includes('jsx')) return 'jsx';
  if (typeAttr.includes('css')) return 'css';
  if (typeAttr.includes('html')) return 'html';
  if (typeAttr.includes('json')) return 'json';
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

const VALID_FILE_ACTIONS: FileAction[] = ['replace', 'create', 'delete'];

function isValidFileAction(value: string): value is FileAction {
  return VALID_FILE_ACTIONS.includes(value as FileAction);
}

function getAttr(attrs: string, name: string): string | undefined {
  const m = attrs.match(new RegExp(`${name}="([^"]*)"`));
  return m?.[1];
}

function parseFiles(body: string, defaultAction: FileAction = 'replace'): FilePatch[] {
  const fileRegex = /<springo-file\s+([^>]*)(?:\/>|>([\s\S]*?)<\/springo-file>)/g;
  const files: FilePatch[] = [];
  let m: RegExpExecArray | null;
  while ((m = fileRegex.exec(body)) !== null) {
    const attrs = m[1];
    const inner = m[2] ?? '';
    const path = getAttr(attrs, 'path');
    if (!path) continue;
    const rawAction = getAttr(attrs, 'action') ?? defaultAction;
    const action: FileAction = isValidFileAction(rawAction) ? rawAction : defaultAction;
    const typeAttr = getAttr(attrs, 'type') ?? '';
    const content = inner.replace(/^\n/, '').replace(/\n$/, '');
    files.push({ path, action, content, fileType: inferFileType(path, typeAttr) });
  }
  return files;
}

// ── Public API ─────────────────────────────────────────────────

/**
 * Quick check whether the raw string contains a `<springo-artifact>` block.
 * Matches the new unified tag (`<springo-artifact op="...">`) and the
 * legacy creation tag (`<springo-artifact type="...">`).
 */
export function hasArtifactOp(raw: string): boolean {
  return /<springo-artifact(\s|>)/.test(raw);
}

/**
 * Parse the first `<springo-artifact>` block.
 *
 * New form (single writer, three ops):
 *   <springo-artifact op="create" title="..." type="app" icon="counter">
 *     <springo-file path="App.jsx" type="text/jsx"> ... </springo-file>
 *   </springo-artifact>
 *
 *   <springo-artifact op="patch" id="art-123">
 *     <springo-file path="App.jsx" action="replace" type="text/jsx"> ... </springo-file>
 *     <springo-file path="old.jsx" action="delete" />
 *   </springo-artifact>
 *
 *   <springo-artifact op="action" id="art-123">
 *     { "type": "reset" }
 *   </springo-artifact>
 *
 * Legacy fallback: if `op` is omitted and `type` is present → treat as create.
 */
export function parseArtifactOp(raw: string): ParsedArtifactOp | null {
  const m = raw.match(/<springo-artifact(\s[^>]*)?>([\s\S]*?)<\/springo-artifact>/);
  if (!m) return null;

  const attrs = m[1] || '';
  const body = m[2];

  const opAttr = getAttr(attrs, 'op');
  const idAttr = getAttr(attrs, 'id') ?? getAttr(attrs, 'artifact-id') ?? getAttr(attrs, 'artifact');
  const typeAttr = getAttr(attrs, 'type') ?? 'document';
  const titleAttr = getAttr(attrs, 'title') ?? 'Artifact';
  const iconAttr = getAttr(attrs, 'icon');

  // Resolve op. If not specified, infer: `type=` → create, otherwise skip.
  let op: ArtifactOp;
  if (opAttr === 'create' || opAttr === 'patch' || opAttr === 'action' || opAttr === 'delete') {
    op = opAttr;
  } else if (getAttr(attrs, 'type')) {
    op = 'create';
  } else {
    return null;
  }

  if (op === 'delete') {
    if (!idAttr) return null;
    return { op: 'delete', id: idAttr };
  }

  if (op === 'action') {
    if (!idAttr) return null;
    try {
      const payload = JSON.parse(body.trim());
      return { op: 'action', id: idAttr, payload };
    } catch {
      return null;
    }
  }

  if (op === 'patch') {
    if (!idAttr) return null;
    const files = parseFiles(body, 'replace');
    return { op: 'patch', id: idAttr, files };
  }

  // op === 'create'
  const artifactType = ((): CreateOp['artifactType'] => {
    const t = typeAttr.toLowerCase();
    if (t === 'app' || t === 'component' || t === 'template') return t;
    return 'document';
  })();
  const files = parseFiles(body, 'create');
  return {
    op: 'create',
    id: idAttr,
    artifactType,
    title: titleAttr,
    icon: iconAttr,
    files,
  };
}
