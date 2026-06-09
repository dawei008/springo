import React from 'react';
import { escapeHtml } from './escapeHtml';

const FILE_PATH_RE = /((?:\/[\w.+@-]+){2,}(?:\.[\w]+)?|~\/[\w.+@/-]+)/g;

/**
 * Render plain text into ReactNodes where any detected absolute or `~/` path
 * becomes a clickable span that opens the file via `electronAPI.openPath`.
 * Output is HTML-escaped.
 */
export function renderWithClickablePaths(text: string): React.ReactNode[] {
  const escaped = escapeHtml(text);
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  FILE_PATH_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = FILE_PATH_RE.exec(escaped)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={`t-${lastIndex}`} dangerouslySetInnerHTML={{ __html: escaped.slice(lastIndex, match.index) }} />,
      );
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
