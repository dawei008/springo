import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useUIStore } from '@/stores/uiStore';

const BASE_URL = 'http://127.0.0.1:8081';

interface FileEntry {
  name: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: number;
}

type SortKey = 'name' | 'size' | 'type' | 'modified';
type SortDir = 'asc' | 'desc';

// ─── Helpers ───

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

/** Human-readable file type description */
function getFileTypeLabel(name: string, type: 'file' | 'directory'): string {
  if (type === 'directory') return 'Folder';
  const ext = getFileExtension(name);
  if (!ext) return 'File';
  const map: Record<string, string> = {
    ts: 'TypeScript', tsx: 'TSX', js: 'JavaScript', jsx: 'JSX',
    mjs: 'ES Module', cjs: 'CommonJS',
    py: 'Python', pyw: 'Python',
    rs: 'Rust', go: 'Go', java: 'Java', c: 'C', cpp: 'C++',
    h: 'C Header', hpp: 'C++ Header', cs: 'C#', rb: 'Ruby',
    php: 'PHP', swift: 'Swift', kt: 'Kotlin',
    json: 'JSON', yaml: 'YAML', yml: 'YAML', toml: 'TOML',
    xml: 'XML', ini: 'INI', env: 'Env',
    md: 'Markdown', mdx: 'MDX', txt: 'Text', rst: 'RST', log: 'Log',
    css: 'CSS', scss: 'SCSS', less: 'LESS', html: 'HTML', svg: 'SVG',
    png: 'PNG Image', jpg: 'JPEG Image', jpeg: 'JPEG Image',
    gif: 'GIF Image', webp: 'WebP Image', bmp: 'Bitmap', ico: 'Icon',
    pdf: 'PDF', doc: 'Word', docx: 'Word', xls: 'Excel',
    xlsx: 'Excel', pptx: 'PowerPoint', csv: 'CSV',
    sh: 'Shell', bash: 'Bash', zsh: 'Zsh', fish: 'Fish',
    bat: 'Batch', ps1: 'PowerShell',
    zip: 'ZIP', tar: 'TAR', gz: 'GZip', bz2: 'BZip2',
    xz: 'XZ', '7z': '7-Zip', rar: 'RAR',
    dmg: 'Disk Image', iso: 'ISO Image',
    mp3: 'Audio', wav: 'Audio', mp4: 'Video', mkv: 'Video', avi: 'Video',
    woff: 'Font', woff2: 'Font', ttf: 'Font', otf: 'Font',
    lock: 'Lock', map: 'Source Map',
  };
  return map[ext] || ext.toUpperCase();
}

/** Format mtime to relative or short date */
function formatDate(mtime: number): string {
  const now = Date.now();
  const d = new Date(mtime * 1000); // mtime is in seconds
  const diffMs = now - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;

  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;

  // Show short date
  const month = d.toLocaleString(undefined, { month: 'short' });
  const day = d.getDate();
  const year = d.getFullYear();
  const thisYear = new Date().getFullYear();
  return year === thisYear ? `${month} ${day}` : `${month} ${day}, ${year}`;
}

/** Classify extension into a category for icon coloring. */
function getFileCategory(ext: string): string {
  if (['ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs'].includes(ext)) return 'code-js';
  if (['py', 'pyw'].includes(ext)) return 'code-py';
  if (['rs', 'go', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'rb', 'php', 'swift', 'kt'].includes(ext)) return 'code';
  if (['json', 'yaml', 'yml', 'toml', 'xml', 'ini', 'env'].includes(ext)) return 'config';
  if (['md', 'mdx', 'txt', 'rst', 'log'].includes(ext)) return 'text';
  if (['css', 'scss', 'less', 'html', 'svg'].includes(ext)) return 'style';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'].includes(ext)) return 'image';
  if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'pptx', 'csv'].includes(ext)) return 'document';
  if (['sh', 'bash', 'zsh', 'fish', 'bat', 'ps1'].includes(ext)) return 'shell';
  if (['zip', 'tar', 'gz', 'bz2', 'xz', '7z', 'rar'].includes(ext)) return 'archive';
  return '';
}

// ─── File type icon ───

function FileIcon({ name, type }: { name: string; type: 'file' | 'directory' }) {
  if (type === 'directory') {
    return (
      <svg className="item-icon folder" width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
      </svg>
    );
  }

  const ext = getFileExtension(name);
  const cat = getFileCategory(ext);

  return (
    <svg className={`item-icon file ${cat}`} width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    </svg>
  );
}

// ─── Context Menu ───

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  entry: FileEntry | null;
  fullPath: string;
}

function FileContextMenu({
  menu,
  onClose,
  onOpen,
  onCopyPath,
  onRename,
  onDelete,
  onRevealInFinder,
  onNewFolder,
  onNewFile,
}: {
  menu: ContextMenuState;
  onClose: () => void;
  onOpen: () => void;
  onCopyPath: () => void;
  onRename: () => void;
  onDelete: () => void;
  onRevealInFinder: () => void;
  onNewFolder: () => void;
  onNewFile: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu.visible) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [menu.visible, onClose]);

  if (!menu.visible) return null;

  // Background click (no entry) — show create actions only
  if (!menu.entry) {
    return (
      <div
        ref={ref}
        className="file-context-menu show"
        style={{ position: 'fixed', top: menu.y, left: menu.x, zIndex: 1000 }}
      >
        <div className="file-context-menu-item" onClick={() => { onNewFolder(); onClose(); }}>
          <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          New Folder
        </div>
        <div className="file-context-menu-item" onClick={() => { onNewFile(); onClose(); }}>
          <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="12" y1="18" x2="12" y2="12"/>
            <line x1="9" y1="15" x2="15" y2="15"/>
          </svg>
          New File
        </div>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="file-context-menu show"
      style={{ position: 'fixed', top: menu.y, left: menu.x, zIndex: 1000 }}
    >
      <div className="file-context-menu-header">{menu.entry.name}</div>
      <div className="file-context-menu-item" onClick={() => { onOpen(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
        Open
      </div>
      <div className="file-context-menu-item" onClick={() => { onRevealInFinder(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        Reveal in Finder
      </div>
      <div className="file-context-menu-item" onClick={() => { onCopyPath(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>
        Copy Path
      </div>
      <div className="file-context-menu-divider" />
      <div className="file-context-menu-item" onClick={() => { onNewFolder(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        New Folder
      </div>
      <div className="file-context-menu-item" onClick={() => { onNewFile(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        New File
      </div>
      <div className="file-context-menu-divider" />
      <div className="file-context-menu-item" onClick={() => { onRename(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
        Rename
      </div>
      <div className="file-context-menu-item" style={{ color: 'var(--error)' }} onClick={() => { onDelete(); onClose(); }}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
        </svg>
        Delete
      </div>
    </div>
  );
}

// ─── Inline rename ───

function InlineRenameInput({
  initialValue,
  onConfirm,
  onCancel,
}: {
  initialValue: string;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.focus();
      const dot = initialValue.lastIndexOf('.');
      ref.current.setSelectionRange(0, dot > 0 ? dot : initialValue.length);
    }
  }, [initialValue]);

  return (
    <input
      ref={ref}
      className="file-rename-input"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); if (value.trim()) onConfirm(value.trim()); }
        if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
      }}
      onBlur={() => { if (value.trim() && value.trim() !== initialValue) onConfirm(value.trim()); else onCancel(); }}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
    />
  );
}

// ─── Main Component ───

export default function FileBrowser() {
  const fileBrowserOpen = useUIStore((s) => s.fileBrowserOpen);
  const fileBrowserPath = useUIStore((s) => s.fileBrowserPath);
  const closeFileBrowser = useUIStore((s) => s.closeFileBrowser);

  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showHidden, setShowHidden] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [renamingName, setRenamingName] = useState<string | null>(null);
  /** 'folder' | 'file' when inline-creating, null otherwise */
  const [creatingType, setCreatingType] = useState<'folder' | 'file' | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false, x: 0, y: 0, entry: null, fullPath: '',
  });

  const searchRef = useRef<HTMLInputElement>(null);

  // Sync path when opened from sidebar
  useEffect(() => {
    if (fileBrowserOpen && fileBrowserPath) {
      setCurrentPath(fileBrowserPath);
      setSearchQuery('');
      setSelectedName(null);
    }
  }, [fileBrowserOpen, fileBrowserPath]);

  // ─── API calls ───

  const execTool = useCallback(async (name: string, input: Record<string, unknown>) => {
    const res = await fetch(`${BASE_URL}/v1/tools/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, input }),
    });
    const data = await res.json();
    return data.result || data;
  }, []);

  const loadDirectory = useCallback(async (path: string) => {
    if (!path) return;
    setLoading(true);
    setError('');
    try {
      const result = await execTool('list_directory', { path, show_hidden: showHidden });
      if (result.error) {
        setError(result.error);
        setEntries([]);
      } else {
        setEntries(result.entries || []);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [execTool, showHidden]);

  useEffect(() => {
    if (currentPath && fileBrowserOpen) {
      loadDirectory(currentPath);
    }
  }, [currentPath, fileBrowserOpen, loadDirectory]);

  // ─── Sorted & filtered entries ───

  const displayEntries = useMemo(() => {
    let list = [...entries];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter((e) => e.name.toLowerCase().includes(q));
    }

    list.sort((a, b) => {
      // Directories always first
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;

      const dir = sortDir === 'asc' ? 1 : -1;
      if (sortKey === 'name') {
        return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) * dir;
      }
      if (sortKey === 'size') {
        return ((a.size || 0) - (b.size || 0)) * dir;
      }
      if (sortKey === 'type') {
        const extA = getFileExtension(a.name);
        const extB = getFileExtension(b.name);
        return extA.localeCompare(extB) * dir || a.name.localeCompare(b.name) * dir;
      }
      if (sortKey === 'modified') {
        return ((a.modified || 0) - (b.modified || 0)) * dir;
      }
      return 0;
    });

    return list;
  }, [entries, searchQuery, sortKey, sortDir]);

  // ─── Navigation ───

  const navigateTo = useCallback((path: string) => {
    setCurrentPath(path);
    setSearchQuery('');
    setSelectedName(null);
    setRenamingName(null);
  }, []);

  const navigateUp = useCallback(() => {
    if (!currentPath || currentPath === '/') return;
    const parent = currentPath.replace(/\/[^/]+\/?$/, '') || '/';
    navigateTo(parent);
  }, [currentPath, navigateTo]);

  const handleRefresh = useCallback(() => {
    if (currentPath) loadDirectory(currentPath);
  }, [currentPath, loadDirectory]);

  // ─── Item actions ───

  const fullPathOf = useCallback((entry: FileEntry) => {
    return `${currentPath}/${entry.name}`.replace(/\/+/g, '/');
  }, [currentPath]);

  const handleItemClick = useCallback((entry: FileEntry) => {
    setSelectedName(entry.name);
  }, []);

  const handleItemDoubleClick = useCallback((entry: FileEntry) => {
    const fp = fullPathOf(entry);
    if (entry.type === 'directory') {
      navigateTo(fp);
    } else {
      window.electronAPI?.openPath(fp);
    }
  }, [fullPathOf, navigateTo]);

  const handleItemDragStart = useCallback((e: React.DragEvent, entry: FileEntry) => {
    const fp = fullPathOf(entry);
    e.dataTransfer.setData('text/plain', fp);
    e.dataTransfer.setData('application/x-springo-filepath', fp);
    e.dataTransfer.effectAllowed = 'copy';
  }, [fullPathOf]);

  const handleContextMenu = useCallback((e: React.MouseEvent, entry: FileEntry) => {
    e.preventDefault();
    e.stopPropagation();
    setSelectedName(entry.name);
    setContextMenu({
      visible: true, x: e.clientX, y: e.clientY, entry, fullPath: fullPathOf(entry),
    });
  }, [fullPathOf]);

  const closeCtxMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, []);

  // ─── File operations ───

  const handleOpen = useCallback(() => {
    if (contextMenu.entry) {
      const fp = contextMenu.fullPath;
      if (contextMenu.entry.type === 'directory') navigateTo(fp);
      else window.electronAPI?.openPath(fp);
    }
  }, [contextMenu, navigateTo]);

  const handleCopyPath = useCallback(() => {
    navigator.clipboard.writeText(contextMenu.fullPath).catch(() => {});
  }, [contextMenu]);

  const handleRevealInFinder = useCallback(() => {
    if (contextMenu.entry) {
      const reveal = contextMenu.entry.type === 'directory' ? contextMenu.fullPath : currentPath;
      window.electronAPI?.openFolder?.(reveal) || window.electronAPI?.openPath(reveal);
    }
  }, [contextMenu, currentPath]);

  const handleStartRename = useCallback(() => {
    if (contextMenu.entry) setRenamingName(contextMenu.entry.name);
  }, [contextMenu]);

  const handleConfirmRename = useCallback(async (newName: string) => {
    if (!renamingName || newName === renamingName) {
      setRenamingName(null);
      return;
    }
    const src = `${currentPath}/${renamingName}`.replace(/\/+/g, '/');
    const dst = `${currentPath}/${newName}`.replace(/\/+/g, '/');
    try {
      await execTool('move_file', { source: src, destination: dst });
      setRenamingName(null);
      loadDirectory(currentPath);
    } catch {
      setRenamingName(null);
    }
  }, [renamingName, currentPath, execTool, loadDirectory]);

  const [pendingDelete, setPendingDelete] = useState<{ name: string; path: string } | null>(null);

  const handleDelete = useCallback(() => {
    if (!contextMenu.entry) return;
    setPendingDelete({ name: contextMenu.entry.name, path: contextMenu.fullPath });
  }, [contextMenu]);

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    try {
      await execTool('delete_file', { path: pendingDelete.path });
      loadDirectory(currentPath);
    } catch { /* ignore */ }
    setPendingDelete(null);
  }, [pendingDelete, execTool, loadDirectory, currentPath]);

  const handleNewFolder = useCallback(() => {
    setCreatingType('folder');
    setSelectedName(null);
  }, []);

  const handleNewFile = useCallback(() => {
    setCreatingType('file');
    setSelectedName(null);
  }, []);

  const handleConfirmCreate = useCallback(async (name: string) => {
    if (!name || !creatingType) { setCreatingType(null); return; }
    const fp = `${currentPath}/${name}`.replace(/\/+/g, '/');
    try {
      if (creatingType === 'folder') {
        await execTool('create_directory', { path: fp });
      } else {
        await execTool('write_file', { path: fp, content: '' });
      }
      setCreatingType(null);
      loadDirectory(currentPath);
    } catch {
      setCreatingType(null);
    }
  }, [creatingType, currentPath, execTool, loadDirectory]);

  /** Right-click on empty area in the content panel */
  const handleBgContextMenu = useCallback((e: React.MouseEvent) => {
    // Only trigger if clicking the background, not a row
    if ((e.target as HTMLElement).closest('.fb-row')) return;
    e.preventDefault();
    setContextMenu({
      visible: true, x: e.clientX, y: e.clientY, entry: null, fullPath: '',
    });
  }, []);

  // ─── Keyboard shortcuts ───

  useEffect(() => {
    if (!fileBrowserOpen) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === 'Backspace' && !(e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        navigateUp();
      }
    };
    const panel = document.querySelector('.file-browser-panel');
    panel?.addEventListener('keydown', handler as EventListener);
    return () => panel?.removeEventListener('keydown', handler as EventListener);
  }, [fileBrowserOpen, navigateUp]);

  // ─── Column resize ───

  const [colWidths, setColWidths] = useState({ name: 180, size: 64, type: 72, date: 76 });
  const [isColResizing, setIsColResizing] = useState(false);
  type ColKey = 'name' | 'size' | 'type' | 'date';
  const resizingColRef = useRef<{ col: ColKey; startX: number; startW: number } | null>(null);

  const handleColResizeStart = useCallback((e: React.MouseEvent, col: ColKey) => {
    e.preventDefault();
    e.stopPropagation();
    const cur = colWidths[col];
    resizingColRef.current = { col, startX: e.clientX, startW: cur };
    setIsColResizing(true);

    const onMove = (ev: MouseEvent) => {
      if (!resizingColRef.current) return;
      const delta = ev.clientX - resizingColRef.current.startX;
      const minW = col === 'name' ? 80 : 40;
      const newW = Math.max(minW, resizingColRef.current.startW + delta);
      setColWidths((prev) => ({ ...prev, [resizingColRef.current!.col]: newW }));
    };
    const onUp = () => {
      resizingColRef.current = null;
      setIsColResizing(false);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [colWidths]);

  // ─── Toggle sort ───

  const toggleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'modified' ? 'desc' : 'asc');
    }
  }, [sortKey]);

  // ─── Breadcrumbs ───

  const breadcrumbs = useMemo(() => {
    if (!currentPath) return [];
    const parts = currentPath.split('/').filter(Boolean);
    return parts.map((part, i) => ({
      name: part,
      path: '/' + parts.slice(0, i + 1).join('/'),
    }));
  }, [currentPath]);

  const folderName = currentPath.split('/').pop() || currentPath;

  if (!fileBrowserOpen) return null;

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u2191' : ' \u2193') : '';

  return (
    <div
      className={`file-browser-panel${fileBrowserOpen ? ' open' : ''}${isColResizing ? ' resizing' : ''}`}
      tabIndex={-1}
      style={fileBrowserOpen ? { width: colWidths.name + colWidths.size + colWidths.type + colWidths.date + 40 } : undefined}
    >
      {/* Header */}
      <div className="file-browser-header">
        <h3>
          <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          {folderName}
          <span className="folder-path-display">{displayEntries.length} items</span>
        </h3>
        <div className="file-browser-header-actions">
          <button className="refresh-btn" onClick={navigateUp} title="Go up (Backspace)">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7"/>
            </svg>
          </button>
          <button className="refresh-btn" onClick={handleRefresh} title="Refresh">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5"/>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.49 9A9 9 0 005.64 5.64L4 9m16 6l-1.64 3.36A9 9 0 014.51 15"/>
            </svg>
          </button>
          <button className="close-btn" onClick={closeFileBrowser}>
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3l8 8M11 3l-8 8"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Breadcrumb */}
      <div className="file-browser-breadcrumb">
        <span className="breadcrumb-item" onClick={() => navigateTo(fileBrowserPath)}>~</span>
        {breadcrumbs.map((bc, i) => (
          <span key={bc.path}>
            <span className="breadcrumb-separator">/</span>
            <span
              className={`breadcrumb-item${i === breadcrumbs.length - 1 ? ' current' : ''}`}
              onClick={() => navigateTo(bc.path)}
            >
              {bc.name}
            </span>
          </span>
        ))}
      </div>

      {/* Search + controls */}
      <div className="file-browser-controls">
        <div className="file-browser-search">
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            ref={searchRef}
            type="text"
            placeholder="Filter..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="search-clear" onClick={() => setSearchQuery('')}>
              <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M2 2l6 6M8 2l-6 6"/>
              </svg>
            </button>
          )}
        </div>
        <button
          className={`fb-toggle${showHidden ? ' active' : ''}`}
          onClick={() => setShowHidden((h) => !h)}
          title={showHidden ? 'Hide hidden files' : 'Show hidden files'}
        >
          .*
        </button>
      </div>

      {/* Column header row */}
      <div className="fb-col-header">
        <div className="fb-col fb-col-name" style={{ width: colWidths.name, flex: 'none' }} onClick={() => toggleSort('name')}>
          Name{sortArrow('name')}
          <span className="fb-col-grip" onMouseDown={(e) => handleColResizeStart(e, 'name')} />
        </div>
        <div className="fb-col fb-col-size" style={{ width: colWidths.size }} onClick={() => toggleSort('size')}>
          Size{sortArrow('size')}
          <span className="fb-col-grip" onMouseDown={(e) => handleColResizeStart(e, 'size')} />
        </div>
        <div className="fb-col fb-col-type" style={{ width: colWidths.type }} onClick={() => toggleSort('type')}>
          Type{sortArrow('type')}
          <span className="fb-col-grip" onMouseDown={(e) => handleColResizeStart(e, 'type')} />
        </div>
        <div className="fb-col fb-col-date" style={{ width: colWidths.date }} onClick={() => toggleSort('modified')}>
          Modified{sortArrow('modified')}
        </div>
      </div>

      {/* Content */}
      <div className="file-browser-content" onContextMenu={handleBgContextMenu}>
        {loading && (
          <div className="file-browser-empty"><p>Loading...</p></div>
        )}
        {error && (
          <div className="file-browser-empty">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" width="48" height="48">
              <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <p>{error}</p>
          </div>
        )}
        {!loading && !error && displayEntries.length === 0 && !creatingType && (
          <div className="file-browser-empty">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" width="48" height="48">
              <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
            </svg>
            <p>{searchQuery ? 'No matches' : 'Empty folder'}</p>
          </div>
        )}
        {/* Inline create row */}
        {creatingType && (
          <div className="fb-row creating">
            <div className="fb-col fb-col-name" style={{ width: colWidths.name, flex: 'none' }}>
              <FileIcon name={creatingType === 'folder' ? '.' : 'untitled'} type={creatingType === 'folder' ? 'directory' : 'file'} />
              <InlineRenameInput
                initialValue={creatingType === 'folder' ? 'New Folder' : 'untitled.txt'}
                onConfirm={handleConfirmCreate}
                onCancel={() => setCreatingType(null)}
              />
            </div>
            <div className="fb-col fb-col-size" style={{ width: colWidths.size }}>--</div>
            <div className="fb-col fb-col-type" style={{ width: colWidths.type }}>{creatingType === 'folder' ? 'Folder' : 'File'}</div>
            <div className="fb-col fb-col-date" style={{ width: colWidths.date }}>--</div>
          </div>
        )}
        {!loading && !error && displayEntries.map((entry) => {
          const isSelected = selectedName === entry.name;
          const isRenaming = renamingName === entry.name;

          return (
            <div
              key={entry.name}
              className={`fb-row${isSelected ? ' selected' : ''}${entry.type === 'directory' ? ' is-directory' : ''}`}
              draggable={entry.type === 'file'}
              onClick={() => handleItemClick(entry)}
              onDoubleClick={() => handleItemDoubleClick(entry)}
              onDragStart={(e) => handleItemDragStart(e, entry)}
              onContextMenu={(e) => handleContextMenu(e, entry)}
            >
              <div className="fb-col fb-col-name" style={{ width: colWidths.name, flex: 'none' }}>
                <FileIcon name={entry.name} type={entry.type} />
                {isRenaming ? (
                  <InlineRenameInput
                    initialValue={entry.name}
                    onConfirm={handleConfirmRename}
                    onCancel={() => setRenamingName(null)}
                  />
                ) : (
                  <span className="item-name" title={entry.name}>{entry.name}</span>
                )}
              </div>
              <div className="fb-col fb-col-size" style={{ width: colWidths.size }}>
                {entry.type === 'file' && entry.size != null ? formatFileSize(entry.size) : '--'}
              </div>
              <div className="fb-col fb-col-type" style={{ width: colWidths.type }}>
                {getFileTypeLabel(entry.name, entry.type)}
              </div>
              <div className="fb-col fb-col-date" style={{ width: colWidths.date }}>
                {entry.modified ? formatDate(entry.modified) : '--'}
              </div>
            </div>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="file-browser-toolbar">
        <span className="item-count">{currentPath}</span>
        <button onClick={handleNewFolder} title="New Folder">
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          +
        </button>
        <button onClick={handleNewFile} title="New File">
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="12" y1="18" x2="12" y2="12"/>
            <line x1="9" y1="15" x2="15" y2="15"/>
          </svg>
          +
        </button>
      </div>

      {/* Context Menu */}
      <FileContextMenu
        menu={contextMenu}
        onClose={closeCtxMenu}
        onOpen={handleOpen}
        onCopyPath={handleCopyPath}
        onRename={handleStartRename}
        onDelete={handleDelete}
        onRevealInFinder={handleRevealInFinder}
        onNewFolder={handleNewFolder}
        onNewFile={handleNewFile}
      />

      {/* Delete confirmation */}
      {pendingDelete && (
        <div className="fb-confirm-overlay">
          <div className="fb-confirm-dialog">
            <p>Delete &ldquo;{pendingDelete.name}&rdquo;?</p>
            <div className="fb-confirm-actions">
              <button onClick={() => setPendingDelete(null)}>Cancel</button>
              <button className="danger" onClick={confirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
