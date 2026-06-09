/**
 * Build an HTML document that wraps raw file content so Canvas's raw-HTML
 * iframe path can render it. Markdown → marked.js + highlight.js on CDN,
 * code → highlight.js with language class, SVG → inline, plain text → <pre>.
 *
 * ArtifactIframe renders files as React only when `type === 'jsx'` exists;
 * otherwise it looks for `index.html` and passes it through. So writing a
 * single-file artifact as `{ path: 'index.html', type: 'html' }` is the
 * reliable way to display non-executable file previews.
 */

import { escapeHtml } from './escapeHtml';

export type PreviewKind = 'markdown' | 'html' | 'image' | 'svg' | 'excalidraw' | 'drawio';

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

export function getPreviewKind(path: string): PreviewKind | null {
  const ext = path.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase();
  return ext ? PREVIEW_EXTENSIONS[ext] ?? null : null;
}

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

export function buildFilePreviewHtml(filePath: string, content: string, kind: PreviewKind): string {
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
