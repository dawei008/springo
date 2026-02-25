import { useCallback, useState, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';
import { useUIStore } from '@/stores/uiStore';
import type { Components } from 'react-markdown';

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
const FILEPATH_PATTERN = '(?:\\/[\\w.+@-]+){2,}|~\\/[\\w.+@\\/-]+';
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
          window.electronAPI?.openPath(href);
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
          className={isFilePath ? 'clickable-path' : 'clickable-url'}
          title={href}
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
      if (/^(\/[\w.+@-][\w.+@/ -]*|~\/[\w.+@/ -][\w.+@/ -]*)$/.test(text)) {
        return (
          <code
            {...props}
            className="clickable-path"
            title={`Open ${text}`}
            style={{ cursor: 'pointer' }}
            onClick={() => window.electronAPI?.openPath(text)}
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
