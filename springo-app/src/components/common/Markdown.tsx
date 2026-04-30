import { useCallback, useState, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';
import { useUIStore } from '@/stores/uiStore';
import { useUnifiedArtifactStore, type ArtifactFile, type UnifiedArtifactType } from '@/stores/unifiedArtifactStore';

type PreviewKind = 'markdown' | 'html' | 'image' | 'svg' | 'excalidraw' | 'drawio';
import type { Components } from 'react-markdown';

/** File extensions that can be previewed in the Canvas panel */
const PREVIEW_EXTENSIONS: Record<string, PreviewKind> = {
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

function getPreviewType(path: string): PreviewKind | null {
  const ext = path.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase();
  return ext ? PREVIEW_EXTENSIONS[ext] ?? null : null;
}

// Languages highlight.js recognizes by extension (pass through to className).
const HLJS_LANG_BY_EXT: Record<string, string> = {
  '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
  '.xml': 'xml', '.csv': 'plaintext',
  '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.jsx': 'javascript',
  '.py': 'python', '.go': 'go', '.rs': 'rust', '.java': 'java',
  '.css': 'css', '.scss': 'scss',
  '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
  '.toml': 'ini', '.ini': 'ini', '.conf': 'plaintext',
  '.sql': 'sql', '.graphql': 'graphql',
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Build an HTML document that renders the file content inside Canvas's
 * raw-HTML iframe path. Markdown → marked.js on CDN, code → highlight.js,
 * SVG → inline, plain text → <pre>.
 */
function buildPreviewHtml(filePath: string, content: string, kind: PreviewKind): string {
  const ext = filePath.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase() || '';
  const isMarkdown = ext === '.md' || ext === '.markdown' || ext === '.mdx';
  const isPlainText = ext === '.txt' || ext === '.log';

  if (kind === 'svg') {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
svg{max-width:100%;max-height:90vh}
</style></head><body>${content}</body></html>`;
  }

  if (isMarkdown) {
    const safe = escapeHtml(content);
    return `<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/marked@12/marked.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css" media="(prefers-color-scheme: light)">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<style>
body{padding:24px 28px;max-width:860px;margin:0 auto;line-height:1.7;font-size:15px}
h1,h2,h3,h4{margin:1.4em 0 .6em;line-height:1.3}
h1{font-size:1.8em;border-bottom:1px solid var(--border-default);padding-bottom:.3em}
h2{font-size:1.4em;border-bottom:1px solid var(--border);padding-bottom:.25em}
h3{font-size:1.2em} h4{font-size:1.05em}
p{margin:.6em 0;text-wrap:pretty}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code{font-family:var(--font-mono);font-size:.88em;background:var(--bg-secondary);padding:.15em .4em;border-radius:4px}
pre{background:var(--bg-secondary);padding:14px 16px;border-radius:8px;overflow-x:auto;margin:.8em 0}
pre code{background:transparent;padding:0;font-size:.85em;line-height:1.55}
blockquote{border-left:3px solid var(--border-strong);margin:.8em 0;padding:.2em 0 .2em 1em;color:var(--text-secondary)}
ul,ol{margin:.6em 0;padding-left:1.6em}
li{margin:.25em 0}
table{border-collapse:collapse;margin:.8em 0;width:100%}
th,td{border:1px solid var(--border-default);padding:.4em .7em;text-align:left}
th{background:var(--bg-secondary);font-weight:600}
img{max-width:100%;height:auto;border-radius:6px}
hr{border:0;border-top:1px solid var(--border);margin:1.5em 0}
</style>
</head>
<body>
<div id="content"></div>
<pre id="raw" style="display:none">${safe}</pre>
<script>
(function(){
  var src = document.getElementById('raw').textContent;
  if (window.marked) {
    marked.setOptions({ gfm: true, breaks: true });
    document.getElementById('content').innerHTML = marked.parse(src);
    if (window.hljs) document.querySelectorAll('pre code').forEach(function(b){ hljs.highlightElement(b); });
  } else {
    document.getElementById('content').innerHTML = '<pre>'+src+'</pre>';
  }
})();
</script>
</body></html>`;
  }

  if (isPlainText) {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{padding:20px;font-family:var(--font-mono);font-size:13px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
</style></head><body>${escapeHtml(content)}</body></html>`;
  }

  // Code / structured data file — highlight.js
  const lang = HLJS_LANG_BY_EXT[ext] || 'plaintext';
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css" media="(prefers-color-scheme: light)">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<style>
body{padding:0;margin:0}
pre{margin:0;padding:20px;font-family:var(--font-mono);font-size:13px;line-height:1.55;overflow-x:auto}
code{background:transparent!important}
</style>
</head><body>
<pre><code class="language-${lang}">${escapeHtml(content)}</code></pre>
<script>if(window.hljs)hljs.highlightAll();</script>
</body></html>`;
}

async function openFileInCanvas(filePath: string) {
  const kind = getPreviewType(filePath);
  if (!kind || !window.electronAPI?.readFileBase64) {
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

    // For HTML files, pass through raw; everything else gets wrapped into an
    // HTML shell so Canvas's raw-HTML path renders it (marked for markdown,
    // highlight.js for code, inline SVG, <pre> for plain text).
    const htmlContent = kind === 'html' ? content : buildPreviewHtml(filePath, content, kind);

    // Stable id per path so re-opening the same file reuses the existing
    // Canvas artifact (and its version history) instead of duplicating.
    const stableId = 'file-' + filePath.replace(/[^a-zA-Z0-9]+/g, '-').slice(-48);
    const store = useUnifiedArtifactStore.getState();
    const file: ArtifactFile = { path: 'index.html', type: 'html', content: htmlContent };

    const existing = store.artifacts[stableId];
    if (existing) {
      store.openArtifact(stableId);
      store.applyPatch(stableId, [
        { path: 'index.html', action: 'replace', fileType: 'html', content: htmlContent },
      ]);
      return;
    }

    const artifactType: UnifiedArtifactType = 'app';
    store.createArtifact({
      id: stableId,
      name: fileName,
      type: artifactType,
      icon: kind === 'html' ? 'web' : kind === 'svg' ? 'image' : 'document',
      files: [file],
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
          openFileInCanvas(href);
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
            onClick={() => openFileInCanvas(text)}
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
