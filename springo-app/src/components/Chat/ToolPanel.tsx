import React from 'react';
import { useUIStore } from '@/stores/uiStore';

const FILE_PATH_RE = /((?:\/[\w.+@-]+){2,}(?:\.[\w]+)?|~\/[\w.+@/-]+)/g;

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderWithClickablePaths(text: string): React.ReactNode[] {
  const escaped = escapeHtml(text);
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  FILE_PATH_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = FILE_PATH_RE.exec(escaped)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`t-${lastIndex}`} dangerouslySetInnerHTML={{ __html: escaped.slice(lastIndex, match.index) }} />);
    }
    const path = match[1];
    parts.push(
      <span
        key={`p-${match.index}`}
        className="clickable-path"
        title={`Open ${path}`}
        onClick={() => window.electronAPI?.openPath(path)}
      >
        {path}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (parts.length === 0) {
    return [<span key="all" dangerouslySetInnerHTML={{ __html: escaped }} />];
  }
  if (lastIndex < escaped.length) {
    parts.push(<span key={`t-${lastIndex}`} dangerouslySetInnerHTML={{ __html: escaped.slice(lastIndex) }} />);
  }
  return parts;
}

export default function ToolPanel() {
  const currentToolPanel = useUIStore((s) => s.currentToolPanel);
  const setToolPanelOpen = useUIStore((s) => s.setToolPanelOpen);

  if (!currentToolPanel) return null;

  const { toolName, input, status, result } = currentToolPanel;
  const isRunning = status === 'running';
  const isComplete = status === 'complete';
  const isError = status === 'error';

  const inputStr = JSON.stringify(input, null, 2);
  const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2);

  return (
    <div className={`tool-panel ${isRunning ? 'running' : ''}`}>
      <div className="tool-panel-header">
        <div className="tool-panel-title">
          <span className={`tool-status-dot ${status}`} />
          <span className="tool-name">{toolName}</span>
        </div>
        <button
          className="tool-panel-close"
          onClick={() => setToolPanelOpen(false)}
          title="Close"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>

      <div className="tool-panel-body">
        <div className="tool-section">
          <div className="tool-section-label">Input</div>
          <pre className="tool-input">
            {renderWithClickablePaths(inputStr)}
          </pre>
        </div>

        {isRunning && (
          <div className="tool-progress">
            <div className="tool-progress-bar" />
          </div>
        )}

        {(isComplete || isError) && result && (
          <div className="tool-section">
            <div className="tool-section-label">
              {isError ? 'Error' : 'Result'}
            </div>
            <pre className={`tool-output ${isError ? 'error' : ''}`}>
              {renderWithClickablePaths(resultStr)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
