import { useState, useEffect, useCallback } from 'react';
import { useUIStore } from '@/stores/uiStore';

const BASE_URL = 'http://127.0.0.1:8081';

interface FileEntry {
  name: string;
  type: 'file' | 'directory';
  size?: number;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export default function FileBrowser() {
  const fileBrowserOpen = useUIStore((s) => s.fileBrowserOpen);
  const fileBrowserPath = useUIStore((s) => s.fileBrowserPath);
  const closeFileBrowser = useUIStore((s) => s.closeFileBrowser);

  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Sync path when opened from sidebar
  useEffect(() => {
    if (fileBrowserOpen && fileBrowserPath) {
      setCurrentPath(fileBrowserPath);
    }
  }, [fileBrowserOpen, fileBrowserPath]);

  // Load folder contents when path changes
  useEffect(() => {
    if (!currentPath || !fileBrowserOpen) return;

    let cancelled = false;
    setLoading(true);
    setError('');

    fetch(`${BASE_URL}/v1/tools/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'list_directory',
        input: { path: currentPath, show_hidden: false },
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const result = data.result || data;
        if (result.error) {
          setError(result.error);
          setEntries([]);
        } else {
          setEntries(result.entries || []);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [currentPath, fileBrowserOpen]);

  const navigateTo = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleItemDoubleClick = useCallback(
    (entry: FileEntry) => {
      const fullPath = `${currentPath}/${entry.name}`.replace(/\/+/g, '/');
      if (entry.type === 'directory') {
        navigateTo(fullPath);
      } else {
        window.electronAPI?.openPath(fullPath);
      }
    },
    [currentPath, navigateTo],
  );

  const handleItemDragStart = useCallback(
    (e: React.DragEvent, entry: FileEntry) => {
      const fullPath = `${currentPath}/${entry.name}`.replace(/\/+/g, '/');
      e.dataTransfer.setData('text/plain', fullPath);
      e.dataTransfer.setData('application/x-springo-filepath', fullPath);
      e.dataTransfer.effectAllowed = 'copy';
    },
    [currentPath],
  );

  // Build breadcrumb parts
  const breadcrumbs = (() => {
    if (!currentPath) return [];
    const parts = currentPath.split('/').filter(Boolean);
    return parts.map((part, i) => ({
      name: part,
      path: '/' + parts.slice(0, i + 1).join('/'),
    }));
  })();

  const folderName = currentPath.split('/').pop() || currentPath;
  const itemCount = entries.length;

  if (!fileBrowserOpen) return null;

  return (
    <div className={`file-browser-panel${fileBrowserOpen ? ' open' : ''}`}>
      {/* Header */}
      <div className="file-browser-header">
        <h3>
          <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          {folderName}
          <span className="folder-path-display">{itemCount} items</span>
        </h3>
        <button className="close-btn" onClick={closeFileBrowser}>
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 3l8 8M11 3l-8 8"/>
          </svg>
        </button>
      </div>

      {/* Breadcrumb */}
      <div className="file-browser-breadcrumb">
        <span
          className="breadcrumb-item"
          onClick={() => navigateTo(fileBrowserPath)}
        >
          ~
        </span>
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

      {/* Content */}
      <div className="file-browser-content">
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
        {!loading && !error && entries.length === 0 && (
          <div className="file-browser-empty">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" width="48" height="48">
              <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
            </svg>
            <p>Empty folder</p>
          </div>
        )}
        {!loading && !error && entries.map((entry) => (
          <div
            key={entry.name}
            className="file-browser-item"
            draggable={entry.type === 'file'}
            onDoubleClick={() => handleItemDoubleClick(entry)}
            onDragStart={(e) => handleItemDragStart(e, entry)}
          >
            {entry.type === 'directory' ? (
              <svg className="item-icon folder" width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
              </svg>
            ) : (
              <svg className="item-icon" width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
            )}
            <span className="item-name">{entry.name}</span>
            {entry.type === 'file' && entry.size != null && (
              <span className="item-info">{formatFileSize(entry.size)}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
