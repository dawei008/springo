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
  // Strip trailing ) only if unbalanced
  while (cleaned.endsWith(')')) {
    const opens = (cleaned.match(/\(/g) || []).length;
    const closes = (cleaned.match(/\)/g) || []).length;
    if (closes > opens) {
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
    let value: string;

    if (rawUrl) {
      value = cleanTrailingPunctuation(rawUrl);
    } else {
      value = rawPath;
    }

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

  if (nodes.length === 0) return [];

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

      const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        if (!href) return;

        if (isFilePath) {
          if (window.electronAPI?.openPath) {
            window.electronAPI.openPath(href);
          }
        } else {
          if (window.electronAPI?.openExternal) {
            window.electronAPI.openExternal(href);
          } else {
            window.open(href, '_blank', 'noopener,noreferrer');
          }
        }
      };

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

    img({ src, alt, ...props }) {
      const handleClick = () => {
        if (src) {
          useUIStore.getState().setImagePreview(src);
        }
      };

      return (
        <img
          {...props}
          src={src}
          alt={alt}
          className="chat-image"
          onClick={handleClick}
          style={{ maxWidth: '100%', cursor: 'pointer', borderRadius: 8 }}
        />
      );
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
