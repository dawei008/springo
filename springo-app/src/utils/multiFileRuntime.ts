import type { ArtifactFile } from '@/stores/unifiedArtifactStore';

/**
 * Springo design tokens injected into every Canvas iframe's <head>.
 * Keep in sync with springo-app/src/styles/variables.css — this is a copy
 * because iframes are sandboxed and can't reach the host stylesheet.
 *
 * The `artifacts-design` skill documents the same names so the model
 * knows what's available to reference via var(--*).
 */
const SPRINGO_TOKENS_CSS = `
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f7f7f8;
  --bg-tertiary: #ededef;
  --bg-elevated: #ffffff;
  --bg-hover: rgba(0, 0, 0, 0.04);
  --bg-active: rgba(99, 91, 255, 0.08);
  --text-primary: #1a1a1a;
  --text-secondary: #6b6b6b;
  --text-tertiary: #999999;
  --text-inverse: #ffffff;
  --accent: #6b5bff;
  --accent-hover: #5a4ae6;
  --accent-light: rgba(99, 91, 255, 0.08);
  --accent-soft: #d4d0ff;
  --accent-glow: rgba(99, 91, 255, 0.12);
  --border: rgba(0, 0, 0, 0.06);
  --border-default: rgba(0, 0, 0, 0.10);
  --border-strong: rgba(0, 0, 0, 0.18);
  --success: #34a853;
  --success-bg: rgba(52, 168, 83, 0.10);
  --success-text: #1e7e34;
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.10);
  --warning-text: #b45309;
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.10);
  --error-text: #dc2626;
  --info: #3b82f6;
  --info-bg: rgba(59, 130, 246, 0.10);
  --info-text: #2563eb;
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-display: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Monaco, monospace;
  --font-size-xs: 10px;
  --font-size-sm: 11px;
  --font-size-base: 13px;
  --font-size-md: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 18px;
  --font-size-2xl: 32px;
  --space-1: 2px; --space-2: 4px; --space-3: 6px; --space-4: 8px;
  --space-5: 10px; --space-6: 12px; --space-7: 14px; --space-8: 16px;
  --space-9: 20px; --space-10: 24px; --space-12: 32px; --space-16: 40px;
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 14px; --radius-xl: 20px;
  --radius-full: 50%;
  --transition-fast: 0.12s ease;
  --transition-base: 0.15s ease;
  --transition-slow: 0.3s ease;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 1px 3px rgba(0, 0, 0, 0.06), 0 4px 12px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 2px 4px rgba(0, 0, 0, 0.06), 0 12px 32px rgba(0, 0, 0, 0.08);
  --shadow-xl: 0 4px 8px rgba(0, 0, 0, 0.08), 0 20px 40px rgba(0, 0, 0, 0.12);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #111111;
    --bg-secondary: #1a1a1a;
    --bg-tertiary: #252525;
    --bg-elevated: #1e1e1e;
    --bg-hover: rgba(255, 255, 255, 0.06);
    --bg-active: rgba(99, 91, 255, 0.15);
    --text-primary: #e5e5e5;
    --text-secondary: #a0a0a0;
    --text-tertiary: #666666;
    --text-inverse: #111111;
    --accent-light: rgba(99, 91, 255, 0.15);
    --accent-soft: #3d3580;
    --accent-glow: rgba(99, 91, 255, 0.20);
    --border: rgba(255, 255, 255, 0.08);
    --border-default: rgba(255, 255, 255, 0.12);
    --border-strong: rgba(255, 255, 255, 0.20);
    --success-bg: rgba(52, 168, 83, 0.15);
    --success-text: #6dd58c;
    --warning-bg: rgba(245, 158, 11, 0.15);
    --warning-text: #fbbf24;
    --error-bg: rgba(239, 68, 68, 0.15);
    --error-text: #f87171;
  }
}
/* Iframe host defaults: when artifact content exceeds the Canvas width, scroll
   internally instead of getting clipped by the Canvas panel. Artifacts can
   opt out with their own html/body overflow rules. */
html, body {
  overflow-x: auto;
  overflow-y: auto;
  margin: 0;
}
body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  min-width: min-content;
}
button, input, textarea, select { font-family: inherit; }
`;

/** Ready-to-inject <style> tag wrapping SPRINGO_TOKENS_CSS. */
export const SPRINGO_TOKENS_STYLE_TAG = `<style id="springo-tokens">${SPRINGO_TOKENS_CSS}</style>`;

/**
 * Resolve a vendored runtime asset (React/Babel) to a URL the iframe can load.
 *
 * The renderer ships with `public/runtime/*.js` so artifacts work without
 * network access. We resolve against `document.baseURI` because the iframe
 * uses `srcdoc` and inherits the parent's base URI; in dev mode that's the
 * Vite dev server, in packaged Electron it's `file:///.../renderer/index.html`.
 */
export function getRuntimeAssetUrl(filename: string): string {
  if (typeof document === 'undefined') return `runtime/${filename}`;
  try {
    return new URL(`runtime/${filename}`, document.baseURI).toString();
  } catch {
    return `runtime/${filename}`;
  }
}

interface CdnLib {
  scripts: string[];
  global: string;
  subExports?: Record<string, string>;
}

const CDN_LIBS: Record<string, CdnLib> = {
  'recharts': {
    scripts: [
      'https://unpkg.com/react-is@18/umd/react-is.production.min.js',
      'https://cdnjs.cloudflare.com/ajax/libs/recharts/3.2.1/Recharts.min.js',
    ],
    global: 'Recharts',
  },
  'lucide-react': {
    scripts: ['https://unpkg.com/lucide-react@0.460.0/dist/umd/lucide-react.min.js'],
    global: 'lucideReact',
  },
  'framer-motion': {
    scripts: ['https://unpkg.com/framer-motion@11/dist/framer-motion.js'],
    global: 'Motion',
  },
  'date-fns': {
    scripts: ['https://unpkg.com/date-fns@4/cdn.min.js'],
    global: 'dateFns',
  },
  'chart.js': {
    scripts: ['https://unpkg.com/chart.js@4/dist/chart.umd.js'],
    global: 'Chart',
  },
  'three': {
    scripts: ['https://unpkg.com/three@0.170.0/build/three.min.js'],
    global: 'THREE',
  },
  'd3': {
    scripts: ['https://unpkg.com/d3@7/dist/d3.min.js'],
    global: 'd3',
  },
};

function detectCdnLibs(files: ArtifactFile[]): { scripts: string[]; registrations: string[] } {
  const allCode = files.map(f => f.content).join('\n');
  const scripts: string[] = [];
  const registrations: string[] = [];
  const seen = new Set<string>();

  for (const [pkg, lib] of Object.entries(CDN_LIBS)) {
    const escaped = pkg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`from\\s+['"]${escaped}['"]`, 'm');
    if (re.test(allCode) && !seen.has(pkg)) {
      seen.add(pkg);
      scripts.push(...lib.scripts);
      if (lib.subExports) {
        for (const [name, expr] of Object.entries(lib.subExports)) {
          registrations.push(`if (typeof ${expr} !== 'undefined') window.__c.${name} = ${expr};`);
        }
        registrations.push(`if (typeof ${lib.global} !== 'undefined') { var _k = Object.keys(${lib.global}); for (var _i=0;_i<_k.length;_i++) window.__c[_k[_i]] = ${lib.global}[_k[_i]]; }`);
      } else {
        registrations.push(`if (typeof ${lib.global} !== 'undefined') { var _k = Object.keys(${lib.global}); for (var _i=0;_i<_k.length;_i++) window.__c[_k[_i]] = ${lib.global}[_k[_i]]; }`);
      }
    }
  }
  return { scripts, registrations };
}

/**
 * Build an HTML runtime document that renders multi-file React projects.
 * Loads React 18 + Babel Standalone from CDN, injects CSS as <style> blocks,
 * and JSX as <script type="text/babel"> blocks.
 */
export function buildMultiFileRuntime(files: ArtifactFile[], entryFile?: string): string {
  const cssFiles = files.filter(f => f.type === 'css');
  const jsxFiles = files.filter(f => f.type === 'jsx');
  const htmlFile = files.find(f => f.path === (entryFile || 'index.html'));

  if (jsxFiles.length === 0 && htmlFile) {
    return htmlFile.content;
  }

  const importRe = /import\s+(?:\{[^}]+\}|\w+)\s+from\s+['"](\.\.?\/[^'"]+)['"]/g;

  // Resolve relative-import specifiers to actual file paths.
  // Strategy:
  //   1. Try each (importer dir + specifier) with no/.jsx/.tsx/.js/.ts/.json + /index.{ext}
  //   2. Fall back to a basename-only match (legacy behavior) so older
  //      artifacts that did `from './Button'` from a flat layout still work.
  const filesByPath = new Map<string, ArtifactFile>();
  for (const f of jsxFiles) filesByPath.set(f.path, f);
  const filesByBasename = new Map<string, ArtifactFile[]>();
  for (const f of jsxFiles) {
    const base = f.path.replace(/^.*\//, '').replace(/\.\w+$/, '');
    const list = filesByBasename.get(base) ?? [];
    list.push(f);
    filesByBasename.set(base, list);
  }

  const EXT_CANDIDATES = ['', '.jsx', '.tsx', '.js', '.ts', '.json'];
  const INDEX_CANDIDATES = ['/index.jsx', '/index.tsx', '/index.js', '/index.ts'];

  function dirname(p: string): string {
    const idx = p.lastIndexOf('/');
    return idx === -1 ? '' : p.slice(0, idx);
  }
  function joinPath(base: string, rel: string): string {
    const parts = (base ? base.split('/') : []).concat(rel.split('/'));
    const out: string[] = [];
    for (const seg of parts) {
      if (!seg || seg === '.') continue;
      if (seg === '..') out.pop();
      else out.push(seg);
    }
    return out.join('/');
  }
  function resolveImport(fromFile: string, specifier: string): ArtifactFile | null {
    const base = dirname(fromFile);
    const joined = joinPath(base, specifier);
    for (const ext of EXT_CANDIDATES) {
      const p = joined + ext;
      const f = filesByPath.get(p);
      if (f) return f;
    }
    for (const idx of INDEX_CANDIDATES) {
      const p = joined + idx;
      const f = filesByPath.get(p);
      if (f) return f;
    }
    // Last-resort basename fallback (only if unambiguous).
    const baseName = specifier.replace(/^.*\//, '').replace(/\.\w+$/, '');
    const candidates = filesByBasename.get(baseName);
    if (candidates && candidates.length === 1) return candidates[0];
    return null;
  }

  const deps = new Map<string, Set<string>>();
  for (const f of jsxFiles) {
    const fileDeps = new Set<string>();
    const tmpRe = new RegExp(importRe.source, 'g');
    let m: RegExpExecArray | null;
    while ((m = tmpRe.exec(f.content)) !== null) {
      const target = resolveImport(f.path, m[1]);
      if (target && target.path !== f.path) fileDeps.add(target.path);
    }
    deps.set(f.path, fileDeps);
  }
  const inDegree = new Map<string, number>();
  for (const f of jsxFiles) inDegree.set(f.path, 0);
  for (const [, fileDeps] of deps) {
    for (const dep of fileDeps) {
      inDegree.set(dep, (inDegree.get(dep) || 0) + 1);
    }
  }

  const sorted: ArtifactFile[] = [...jsxFiles].sort((a, b) => {
    const aIsApp = a.path.toLowerCase().replace(/^.*\//, '') === 'app.jsx';
    const bIsApp = b.path.toLowerCase().replace(/^.*\//, '') === 'app.jsx';
    if (aIsApp) return 1;
    if (bIsApp) return -1;
    const aDeps = deps.get(a.path)?.size || 0;
    const bDeps = deps.get(b.path)?.size || 0;
    if (aDeps !== bDeps) return aDeps - bDeps;
    const aIn = inDegree.get(a.path) || 0;
    const bIn = inDegree.get(b.path) || 0;
    if (aIn !== bIn) return bIn - aIn;
    return a.path.localeCompare(b.path);
  });

  // Synthetic per-path export keys so two files with the same basename
  // don't overwrite each other on `window.__c`.
  const pathKey = (p: string) => '__f_' + p.replace(/[^a-zA-Z0-9]/g, '_');

  const processedJsx = sorted.map(f => {
    let code = f.content;
    const fileKey = pathKey(f.path);

    // Default-export markers we'll backfill below — one of these wins per file.
    let defaultIdent: string | null = null;

    // Named imports: still go through the shared __c bag.
    code = code.replace(
      /import\s+\{([^}]+)\}\s+from\s+['"][^'"]+['"]\s*;?/g,
      (_m, names) => `const {${names}} = window.__c;`
    );

    // Default imports: if the specifier resolves to one of our files, alias
    // to that file's synthetic default key. Otherwise fall back to the bag
    // (for CDN libs registered in window.__c).
    code = code.replace(
      /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
      (_m, localName, spec) => {
        if (spec.startsWith('./') || spec.startsWith('../')) {
          const target = resolveImport(f.path, spec);
          if (target) {
            return `const ${localName} = window.__c[${JSON.stringify(pathKey(target.path) + '_default')}];`;
          }
        }
        return `const ${localName} = window.__c.${localName};`;
      }
    );

    const exportedNames: string[] = [];
    code = code.replace(
      /export\s+default\s+function\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); defaultIdent = name; return `function ${name}`; }
    );
    code = code.replace(
      /export\s+default\s+class\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); defaultIdent = name; return `class ${name}`; }
    );
    code = code.replace(
      /export\s+function\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); return `function ${name}`; }
    );
    code = code.replace(
      /export\s+const\s+(\w+)\s*=/g,
      (_m, name) => { exportedNames.push(name); return `var ${name} =`; }
    );
    const baseName = f.path.replace(/^.*\//, '').replace(/\.\w+$/, '');
    code = code.replace(
      /export\s+default\s+(\w+)\s*;/g,
      (_m, ident) => {
        exportedNames.push(ident);
        defaultIdent = ident;
        return `/* exported ${ident} */`;
      }
    );
    code = code.replace(
      /export\s+default\s+/g,
      () => { exportedNames.push(baseName); defaultIdent = baseName; return `var ${baseName} = `; }
    );

    const uniqueNames = [...new Set(exportedNames)];
    const tail: string[] = [];
    if (uniqueNames.length > 0) {
      tail.push(...uniqueNames.map((n) => `window.__c.${n} = ${n}; window.${n} = ${n};`));
    }
    if (defaultIdent) {
      // Per-file synthetic default key — used by import resolver to avoid collisions.
      tail.push(`window.__c[${JSON.stringify(fileKey + '_default')}] = ${defaultIdent};`);
    }
    if (tail.length > 0) code += '\n' + tail.join('\n');

    return { path: f.path, code };
  });

  let htmlBody = '';
  if (htmlFile) {
    const bodyMatch = htmlFile.content.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    htmlBody = bodyMatch?.[1] || '';
  }

  const jsxSources = processedJsx.map(f => ({ path: f.path, code: f.code }));
  const cdnLibs = detectCdnLibs(files);
  const cdnScriptTags = cdnLibs.scripts.map(url => `  <script src="${url}" crossorigin></script>`).join('\n');

  const reactUrl = getRuntimeAssetUrl('react.production.min.js');
  const reactDomUrl = getRuntimeAssetUrl('react-dom.production.min.js');
  const babelUrl = getRuntimeAssetUrl('babel.min.js');

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <script src="${reactUrl}"></script>
  <script src="${reactDomUrl}"></script>
  <script src="${babelUrl}"></script>
${cdnScriptTags}
  <style>* { margin: 0; padding: 0; box-sizing: border-box; }</style>
  <style id="springo-tokens">${SPRINGO_TOKENS_CSS}</style>
${cssFiles.map(f => `  <style>/* ${f.path} */\n${f.content}</style>`).join('\n')}
</head>
<body>
  <div id="root"></div>
  ${htmlBody}
  <script>
    window.__c = new Proxy({}, {
      get: function(target, prop) {
        if (prop in target) return target[prop];
        if (typeof prop === 'string' && /^[A-Z]/.test(prop)) {
          var _ph = new Proxy(
            function _Placeholder(props) {
              return React.createElement('span', {
                style: { opacity: 0.4, fontSize: '12px' },
                title: 'Missing: ' + prop
              }, props && props.children ? props.children : '[' + prop + ']');
            },
            { get: function(_fn, sub) {
                if (sub === '$$typeof' || sub === 'prototype' || sub === 'name' || sub === 'length' || sub === 'caller' || sub === 'arguments' || sub === 'apply' || sub === 'call' || sub === 'bind') return _fn[sub];
                return function(p) { return React.createElement('span', { style:{opacity:0.4,fontSize:'11px'}, title:'Missing: '+prop+'.'+sub }, p&&p.children?p.children:''); };
              }
            }
          );
          return _ph;
        }
        return undefined;
      }
    });
    var _rh = ['useState','useEffect','useRef','useCallback','useMemo','useContext','useReducer','createContext','Fragment','createElement','Children','cloneElement','forwardRef','memo','lazy','Suspense','startTransition','useTransition','useDeferredValue','useId'];
    for (var _hi = 0; _hi < _rh.length; _hi++) {
      if (React[_rh[_hi]]) window.__c[_rh[_hi]] = React[_rh[_hi]];
    }
    window.__c.React = React;
    window.__c.ReactDOM = ReactDOM;
    ${cdnLibs.registrations.join('\n    ')}
    function _showError(msg) {
      var root = document.getElementById('root');
      if (root) root.innerHTML =
        '<div style="padding:20px;color:#e74c3c;font-family:monospace;white-space:pre-wrap;font-size:13px">' +
        '<b>Render Error:</b>\\n' + String(msg) + '</div>';
    }
    window.onerror = function(msg) { _showError(msg); };
    var _sources = ${JSON.stringify(jsxSources)};
    try {
      for (var i = 0; i < _sources.length; i++) {
        var s = _sources[i];
        var code = Babel.transform(s.code, { presets: ['react'] }).code;
        (new Function(code))();
      }
      var _AppComponent = window.App || window.__c.App;
      if (!_AppComponent) {
        var _keys = Object.keys(window.__c).filter(function(k) {
          return typeof window.__c[k] === 'function' && /^[A-Z]/.test(k) && k !== 'React' && k !== 'ReactDOM';
        });
        if (_keys.length > 0) _AppComponent = window.__c[_keys[_keys.length - 1]];
      }
      var root = document.getElementById('root');
      if (root && _AppComponent) {
        var _onError = function(e) { _showError(e.message || e); };
        ReactDOM.createRoot(root, { onRecoverableError: _onError }).render(
          React.createElement(
            (function() {
              class EB extends React.Component {
                constructor(p) { super(p); this.state = { err: null }; }
                static getDerivedStateFromError(e) { return { err: e }; }
                render() {
                  if (this.state.err) {
                    _showError(this.state.err.message || this.state.err);
                    return null;
                  }
                  return this.props.children;
                }
              }
              return EB;
            })(),
            null,
            React.createElement(_AppComponent)
          )
        );
      } else if (root && !_AppComponent) {
        var _registered = Object.keys(window.__c).filter(function(k) { return typeof window.__c[k] === 'function'; });
        _showError('No App component found.\\nRegistered: ' + (_registered.join(', ') || 'none'));
      }
    } catch(e) {
      _showError(e.message || e);
      console.error(e);
    }
  </script>
  <script>
    (function() {
      var _highlight = null;
      function getCssPath(el) {
        var parts = [];
        while (el && el !== document.body && el !== document.documentElement) {
          var tag = el.tagName.toLowerCase();
          if (el.id) { parts.unshift(tag + '#' + el.id); break; }
          var cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
          var idx = 1, sib = el.previousElementSibling;
          while (sib) { if (sib.tagName === el.tagName) idx++; sib = sib.previousElementSibling; }
          parts.unshift(tag + cls + (idx > 1 ? ':nth-of-type(' + idx + ')' : ''));
          el = el.parentElement;
        }
        return parts.join(' > ');
      }
      function removeHighlight() {
        if (_highlight && _highlight.parentNode) _highlight.parentNode.removeChild(_highlight);
        _highlight = null;
      }
      document.addEventListener('click', function(e) {
        if (!e.altKey) return;
        e.preventDefault();
        e.stopPropagation();
        var el = e.target;
        if (!el || el === document.body || el === document.documentElement) return;
        var rect = el.getBoundingClientRect();
        var cs = window.getComputedStyle(el);
        var text = (el.textContent || '').trim().substring(0, 80);
        removeHighlight();
        _highlight = document.createElement('div');
        _highlight.style.cssText = 'position:fixed;pointer-events:none;border:2px solid #6366f1;background:rgba(99,102,241,0.08);border-radius:3px;z-index:999999;transition:all 0.15s;';
        _highlight.style.left = rect.left + 'px';
        _highlight.style.top = rect.top + 'px';
        _highlight.style.width = rect.width + 'px';
        _highlight.style.height = rect.height + 'px';
        document.body.appendChild(_highlight);
        window.parent.postMessage({
          type: 'springo:element-selected',
          payload: {
            tagName: el.tagName.toLowerCase(),
            id: el.id || undefined,
            className: (typeof el.className === 'string' ? el.className : '') || undefined,
            textPreview: text || undefined,
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
            cssPath: getCssPath(el),
            computedStyles: {
              color: cs.color, backgroundColor: cs.backgroundColor,
              fontSize: cs.fontSize, fontWeight: cs.fontWeight, fontFamily: cs.fontFamily,
              padding: cs.padding, margin: cs.margin, borderRadius: cs.borderRadius,
              display: cs.display, position: cs.position
            }
          }
        }, '*');
      }, true);
      document.addEventListener('click', function(e) {
        if (!e.altKey && _highlight) removeHighlight();
      });
      document.addEventListener('click', function(e) {
        if (e.altKey) return;
        var el = e.target;
        if (!el || el === document.body || el === document.documentElement || el === document.getElementById('root')) return;
        var compName = el.tagName.toLowerCase();
        var walkEl = el;
        while (walkEl && walkEl !== document.body) {
          var dn = walkEl.getAttribute && walkEl.getAttribute('data-component');
          if (dn) { compName = dn; break; }
          if (walkEl.className && typeof walkEl.className === 'string') {
            var classes = walkEl.className.trim().split(/\\s+/);
            var meaningful = classes.find(function(c) { return c.length > 2 && !/^(p|m|d|w|h|flex|grid|text|bg|border|rounded|shadow|overflow|relative|absolute|block|inline)/.test(c); });
            if (meaningful) { compName = meaningful; break; }
          }
          walkEl = walkEl.parentElement;
        }
        window.parent.postMessage({
          type: 'springo:element-pinned',
          payload: {
            componentName: compName,
            cssPath: getCssPath(el),
            tagName: el.tagName.toLowerCase(),
            className: (typeof el.className === 'string' ? el.className : '') || undefined,
            id: el.id || undefined
          }
        }, '*');
      });
      var _origError = window.onerror;
      window.onerror = function(msg, src, line) {
        window.parent.postMessage({ type: 'springo:error', payload: { type: 'runtime', message: String(msg), source: src, line: line, timestamp: Date.now() } }, '*');
        if (_origError) return _origError.apply(this, arguments);
      };
      var _origConsoleError = console.error;
      console.error = function() {
        var msg = Array.prototype.slice.call(arguments).map(function(a) { return typeof a === 'object' ? JSON.stringify(a) : String(a); }).join(' ');
        window.parent.postMessage({ type: 'springo:error', payload: { type: 'console', message: msg, timestamp: Date.now() } }, '*');
        _origConsoleError.apply(console, arguments);
      };
      window.addEventListener('unhandledrejection', function(e) {
        window.parent.postMessage({ type: 'springo:error', payload: { type: 'runtime', message: 'Unhandled rejection: ' + (e.reason && e.reason.message || e.reason || 'unknown'), timestamp: Date.now() } }, '*');
      });
      window.addEventListener('message', function(e) {
        if (e.data && e.data.type === 'springo:set-css-var') {
          document.documentElement.style.setProperty(e.data.name, e.data.value);
        }
      });
      setTimeout(function() {
        var root = document.getElementById('root');
        if (root && root.innerHTML.trim() === '') {
          window.parent.postMessage({ type: 'springo:error', payload: { type: 'render', message: 'Blank screen — no content rendered after 3 seconds', timestamp: Date.now() } }, '*');
        }
      }, 3000);
    })();
  </script>
</body>
</html>`;
}
