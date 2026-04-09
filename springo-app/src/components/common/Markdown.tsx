import { useCallback, useState, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';
import { useUIStore } from '@/stores/uiStore';
import { useArtifactStore, createArtifactId } from '@/stores/artifactStore';
import type { ArtifactType } from '@/stores/artifactStore';
import type { Components } from 'react-markdown';

/** File extensions that can be previewed in the artifact panel */
const PREVIEW_EXTENSIONS: Record<string, ArtifactType> = {
  '.md': 'markdown', '.markdown': 'markdown', '.mdx': 'markdown',
  '.html': 'html', '.htm': 'html',
  '.svg': 'svg',
  '.txt': 'markdown', '.log': 'markdown',
  '.json': 'markdown', '.yaml': 'markdown', '.yml': 'markdown',
  '.xml': 'markdown', '.csv': 'markdown',
  '.ts': 'markdown', '.tsx': 'markdown', '.js': 'markdown', '.jsx': 'markdown',
  '.py': 'markdown', '.go': 'markdown', '.rs': 'markdown', '.java': 'markdown',
  '.css': 'markdown', '.scss': 'markdown',
  '.sh': 'markdown', '.bash': 'markdown', '.zsh': 'markdown',
  '.toml': 'markdown', '.ini': 'markdown', '.conf': 'markdown',
  '.sql': 'markdown', '.graphql': 'markdown',
};

function getPreviewType(path: string): ArtifactType | null {
  const ext = path.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase();
  return ext ? PREVIEW_EXTENSIONS[ext] ?? null : null;
}

async function openFileInArtifactPanel(filePath: string) {
  const type = getPreviewType(filePath);
  if (!type || !window.electronAPI?.readFileBase64) {
    window.electronAPI?.openPath(filePath);
    return;
  }
  try {
    const result = await window.electronAPI.readFileBase64(filePath);
    if (!result.success || !result.data) {
      window.electronAPI?.openPath(filePath);
      return;
    }
    // Decode base64 → binary → UTF-8 (atob alone mangles multi-byte chars like Chinese)
    const binary = atob(result.data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const content = new TextDecoder('utf-8').decode(bytes);
    const fileName = filePath.split('/').pop() || filePath;
    const ext = filePath.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase() || '';

    // For code/config files, wrap in code fence for syntax highlighting
    let finalContent = content;
    if (type === 'markdown' && ext !== '.md' && ext !== '.markdown' && ext !== '.mdx' && ext !== '.txt') {
      const lang = ext.replace('.', '');
      finalContent = '```' + lang + '\n' + content + '\n```';
    }

    useArtifactStore.getState().openArtifact({
      id: createArtifactId(),
      type,
      title: fileName,
      content: finalContent,
      filePath,
      timestamp: Date.now(),
    });
  } catch {
    window.electronAPI?.openPath(filePath);
  }
}

interface Props {
  content: string;
}

/**
 * Extract plain text from React children tree (used for code copy button).
 */
function extractText(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (!children) return '';
  if (Array.isArray(children)) {
    return children.map(extractText).join('');
  }
  if (isValidElement(children)) {
    const props = children.props as Record<string, unknown>;
    return extractText(props.children as React.ReactNode);
  }
  return '';
}

// ---------------------------------------------------------------------------
// Remark plugin: auto-linkify bare URLs and file paths in text nodes
// ---------------------------------------------------------------------------
const URL_PATTERN = 'https?:\\/\\/[^\\s<>"\'`\\]]+';
const FILEPATH_PATTERN = '(?:\\/[\\w.+@()#-]+){2,}|~\\/[\\w.+@()#\\/-]+';
const COMBINED_RE = new RegExp(`(${URL_PATTERN})|(${FILEPATH_PATTERN})`, 'g');

function cleanTrailingPunctuation(url: string): string {
  let cleaned = url.replace(/[.,;:!?]+$/, '');

  // Strip trailing ) only if parentheses are unbalanced
  while (cleaned.endsWith(')')) {
    const openCount = (cleaned.match(/\(/g) || []).length;
    const closeCount = (cleaned.match(/\)/g) || []).length;

    if (closeCount > openCount) {
      cleaned = cleaned.slice(0, -1);
    } else {
      break;
    }
  }

  return cleaned;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function linkifyTextNode(text: string): any[] {
  const nodes: any[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  COMBINED_RE.lastIndex = 0;

  while ((match = COMBINED_RE.exec(text)) !== null) {
    const rawUrl = match[1];
    const rawPath = match[2];
    const value = rawUrl ? cleanTrailingPunctuation(rawUrl) : rawPath;

    if (match.index > lastIndex) {
      nodes.push({ type: 'text', value: text.slice(lastIndex, match.index) });
    }

    nodes.push({
      type: 'link',
      url: value,
      children: [{ type: 'text', value }],
    });

    const consumed = match.index + value.length;
    lastIndex = consumed;
    COMBINED_RE.lastIndex = consumed;
  }

  if (nodes.length === 0) {
    return [];
  }

  if (lastIndex < text.length) {
    nodes.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return nodes;
}

function remarkLinkifyWalk(node: any): void {
  if (!node.children) return;
  if (node.type === 'link' || node.type === 'code' || node.type === 'inlineCode') return;

  const newChildren: any[] = [];
  let changed = false;

  for (const child of node.children) {
    if (child.type === 'text') {
      const parts = linkifyTextNode(child.value);
      if (parts.length > 0) {
        newChildren.push(...parts);
        changed = true;
        continue;
      }
    } else {
      remarkLinkifyWalk(child);
    }
    newChildren.push(child);
  }

  if (changed) {
    node.children = newChildren;
  }
}

function remarkLinkify() {
  return (tree: any) => remarkLinkifyWalk(tree);
}
/* eslint-enable @typescript-eslint/no-explicit-any */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);

  return (
    <button className="copy-code-btn" onClick={handleCopy}>
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

function CollapsibleImage({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) {
  const [collapsed, setCollapsed] = useState(false);
  const label = alt || (src ? src.split('/').pop()?.split('?')[0] : '') || 'Image';

  return (
    <div className={`tool-visual-content${collapsed ? ' collapsed' : ''}`}>
      <div className="tool-visual-header" onClick={() => setCollapsed((c) => !c)}>
        <span className="tool-visual-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </span>
        <span className="tool-visual-label">{label}</span>
        <svg className="tool-visual-toggle" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      {!collapsed && (
        <div className="tool-visual-image">
          <img
            {...props}
            src={src}
            alt={alt}
            className="chat-image"
            onClick={() => { if (src) useUIStore.getState().setImagePreview(src); }}
            style={{ maxWidth: '100%', cursor: 'pointer', borderRadius: 8 }}
          />
        </div>
      )}
    </div>
  );
}

export default function Markdown({ content }: Props) {
  const components: Components = {
    pre({ children, ...props }) {
      // Extract code text from children for the copy button
      const codeText = extractText(children);

      return (
        <pre {...props}>
          {children}
          {codeText && <CopyButton text={codeText} />}
        </pre>
      );
    },

    a({ href, children, ...props }) {
      const isFilePath = href ? /^(\/|~\/)/.test(href) : false;

      function handleClick(e: React.MouseEvent<HTMLAnchorElement>): void {
        e.preventDefault();
        if (!href) return;

        if (isFilePath) {
          openFileInArtifactPanel(href);
          return;
        }

        if (window.electronAPI?.openExternal) {
          window.electronAPI.openExternal(href);
        } else {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
      }

      return (
        <a
          {...props}
          href={href}
          onClick={handleClick}
          onContextMenu={isFilePath ? (e) => {
            e.preventDefault();
            if (href) window.electronAPI?.openPath(href);
          } : undefined}
          className={isFilePath ? 'clickable-path' : 'clickable-url'}
          title={isFilePath ? `Click: preview | Right-click: open with system app` : href}
        >
          {children}
        </a>
      );
    },

    // Inline code: detect URLs and file paths and make them clickable
    code({ children, className, ...props }) {
      // Only handle inline code (no className from syntax highlighting, and not inside <pre>)
      if (className) {
        return <code className={className} {...props}>{children}</code>;
      }
      const text = extractText(children).trim();
      if (!text) {
        return <code {...props}>{children}</code>;
      }

      // Check if the entire inline code is a URL
      if (/^https?:\/\/\S+$/.test(text)) {
        const cleaned = cleanTrailingPunctuation(text);
        return (
          <code
            {...props}
            className="clickable-url"
            title={cleaned}
            style={{ cursor: 'pointer' }}
            onClick={() => {
              if (window.electronAPI?.openExternal) {
                window.electronAPI.openExternal(cleaned);
              } else {
                window.open(cleaned, '_blank', 'noopener,noreferrer');
              }
            }}
          >
            {children}
          </code>
        );
      }

      // Check if the entire inline code is a file path
      // Backticks give clear boundaries — allow spaces, parens, unicode in filenames.
      // Require 2+ path segments for absolute paths to avoid false positives.
      if (/^((?:\/[^\n\r/]+){2,}|~\/[^\n\r]+)$/.test(text)) {
        return (
          <code
            {...props}
            className="clickable-path"
            title="Click: preview | Right-click: open with system app"
            style={{ cursor: 'pointer' }}
            onClick={() => openFileInArtifactPanel(text)}
            onContextMenu={(e) => { e.preventDefault(); window.electronAPI?.openPath(text) }}
          >
            {children}
          </code>
        );
      }

      return <code {...props}>{children}</code>;
    },

    img({ src, alt, ...props }) {
      return <CollapsibleImage src={src} alt={alt} {...props} />;
    },
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks, remarkLinkify]}
      rehypePlugins={[rehypeHighlight]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
