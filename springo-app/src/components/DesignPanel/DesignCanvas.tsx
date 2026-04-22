/**
 * DesignCanvas - iframe renderer with viewport simulation and React/Babel runtime
 */
import { useRef, useEffect, useCallback } from 'react';
import type { DesignVersion, DesignFile } from '@/types';
import type { ViewportMode } from '@/stores/designStore';
import { useDesignStore } from '@/stores/designStore';
import DesignTemplateLibrary from './DesignTemplateLibrary';
import type { DesignTemplate } from '@/data/designTemplates';

const VIEWPORT_WIDTHS: Record<ViewportMode, number | null> = {
  desktop: null,
  tablet: 768,
  mobile: 375,
};

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

function detectCdnLibs(files: DesignFile[]): { scripts: string[]; registrations: string[] } {
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
function buildMultiFileRuntime(files: DesignFile[], entryFile?: string): string {
  const cssFiles = files.filter(f => f.type === 'css');
  const jsxFiles = files.filter(f => f.type === 'jsx');
  const htmlFile = files.find(f => f.path === (entryFile || 'index.html'));

  // If there's only an HTML file with no JSX, use it directly
  if (jsxFiles.length === 0 && htmlFile) {
    return htmlFile.content;
  }

  // Topological sort: files that are imported by others come first
  // Build dependency graph from import statements
  const importRe = /import\s+(?:\{[^}]+\}|\w+)\s+from\s+['"]\.\/([^'"]+)['"]/g;
  const fileBaseNames = new Map<string, DesignFile>();
  for (const f of jsxFiles) {
    const base = f.path.replace(/^.*\//, '').replace(/\.\w+$/, '');
    fileBaseNames.set(base, f);
  }
  // deps[filePath] = set of filePaths it imports
  const deps = new Map<string, Set<string>>();
  for (const f of jsxFiles) {
    const fileDeps = new Set<string>();
    let m: RegExpExecArray | null;
    importRe.lastIndex = 0;
    const tmpRe = new RegExp(importRe.source, 'g');
    while ((m = tmpRe.exec(f.content)) !== null) {
      const importedName = m[1].replace(/\.\w+$/, '').replace(/^.*\//, '');
      const target = fileBaseNames.get(importedName);
      if (target) fileDeps.add(target.path);
    }
    deps.set(f.path, fileDeps);
  }
  // Topological sort via Kahn's algorithm
  const inDegree = new Map<string, number>();
  for (const f of jsxFiles) inDegree.set(f.path, 0);
  for (const [, fileDeps] of deps) {
    for (const dep of fileDeps) {
      inDegree.set(dep, (inDegree.get(dep) || 0) + 1);
    }
  }
  const queue: string[] = [];
  for (const [path, deg] of inDegree) {
    if (deg === 0) queue.push(path);
  }
  // Files with 0 in-degree go last (they import others, are not imported)
  // Files with high in-degree go first (they are imported by many = leaf/utility)
  const sorted: DesignFile[] = [];
  const visited = new Set<string>();
  // Start with files that have highest in-degree (most depended-upon)
  const byInDegree = [...jsxFiles].sort((a, b) => {
    const aIsApp = a.path.toLowerCase().replace(/^.*\//, '') === 'app.jsx';
    const bIsApp = b.path.toLowerCase().replace(/^.*\//, '') === 'app.jsx';
    if (aIsApp) return 1;
    if (bIsApp) return -1;
    const aDeps = deps.get(a.path)?.size || 0;
    const bDeps = deps.get(b.path)?.size || 0;
    // Files with fewer imports (dependencies) first = they're leaf/utility
    if (aDeps !== bDeps) return aDeps - bDeps;
    // Tie-break: files imported by more others first
    const aIn = inDegree.get(a.path) || 0;
    const bIn = inDegree.get(b.path) || 0;
    if (aIn !== bIn) return bIn - aIn;
    return a.path.localeCompare(b.path);
  });
  sorted.push(...byInDegree);

  // Pre-process JSX: rewrite imports/exports for window.__c global registry
  const processedJsx = sorted.map(f => {
    let code = f.content;
    // Rewrite: import { X, Y } from './path' → const { X, Y } = window.__c;
    code = code.replace(
      /import\s+\{([^}]+)\}\s+from\s+['"][^'"]+['"]\s*;?/g,
      (_m, names) => `const {${names}} = window.__c;`
    );
    // Rewrite: import X from './path' → const X = window.__c.X;
    code = code.replace(
      /import\s+(\w+)\s+from\s+['"][^'"]+['"]\s*;?/g,
      (_m, name) => `const ${name} = window.__c.${name};`
    );

    // Collect names to register on window.__c after eval
    const exportedNames: string[] = [];

    // export default function X(...) → function X(...) + register
    code = code.replace(
      /export\s+default\s+function\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); return `function ${name}`; }
    );
    // export default class X → class X + register
    code = code.replace(
      /export\s+default\s+class\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); return `class ${name}`; }
    );
    // export function X → function X + register
    code = code.replace(
      /export\s+function\s+(\w+)/g,
      (_m, name) => { exportedNames.push(name); return `function ${name}`; }
    );
    // export const X = → const X = + register (but const is block-scoped, use var)
    code = code.replace(
      /export\s+const\s+(\w+)\s*=/g,
      (_m, name) => { exportedNames.push(name); return `var ${name} =`; }
    );
    // Catch remaining: export default <expression>
    const baseName = f.path.replace(/^.*\//, '').replace(/\.\w+$/, '');
    code = code.replace(
      /export\s+default\s+(\w+)\s*;/g,
      (_m, ident) => {
        // "export default SomeVar;" — just register the existing variable, don't redeclare
        exportedNames.push(ident);
        return `/* exported ${ident} */`;
      }
    );
    // export default <anonymous expression> (object literal, arrow fn, etc.)
    code = code.replace(
      /export\s+default\s+/g,
      () => { exportedNames.push(baseName); return `var ${baseName} = `; }
    );

    // Append registration: window.__c.X = X; window.X = X;
    // (window.X for App so the mount code can find it)
    const uniqueNames = [...new Set(exportedNames)];
    if (uniqueNames.length > 0) {
      code += '\n' + uniqueNames.map(n =>
        `window.__c.${n} = ${n}; window.${n} = ${n};`
      ).join('\n');
    }

    return { path: f.path, code };
  });

  // Extract <body> content from HTML entry if it exists
  let htmlBody = '';
  if (htmlFile) {
    const bodyMatch = htmlFile.content.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    htmlBody = bodyMatch?.[1] || '';
  }

  // Embed JSX source as JSON array for manual transpilation
  const jsxSources = processedJsx.map(f => ({ path: f.path, code: f.code }));

  // Auto-detect third-party libraries used in source and load their CDN builds
  const cdnLibs = detectCdnLibs(files);
  const cdnScriptTags = cdnLibs.scripts.map(url => `  <script src="${url}" crossorigin></script>`).join('\n');

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
${cdnScriptTags}
  <style>* { margin: 0; padding: 0; box-sizing: border-box; } body { font-family: system-ui, -apple-system, 'SF Pro Display', sans-serif; }</style>
${cssFiles.map(f => `  <style>/* ${f.path} */\n${f.content}</style>`).join('\n')}
</head>
<body>
  <div id="root"></div>
  ${htmlBody}
  <script>
    // Seed global component registry with React hooks & utilities
    // Use a Proxy so any unresolved import returns a placeholder component
    // instead of undefined (prevents blank screen when LLM omits a file)
    window.__c = new Proxy({}, {
      get: function(target, prop) {
        if (prop in target) return target[prop];
        if (typeof prop === 'string' && /^[A-Z]/.test(prop)) {
          // Return a placeholder component that renders its children
          // and also acts as a namespace (e.g. Icon.Chat)
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
    // Expose React hooks so "const { useState } = window.__c" works
    var _rh = ['useState','useEffect','useRef','useCallback','useMemo','useContext','useReducer','createContext','Fragment','createElement','Children','cloneElement','forwardRef','memo','lazy','Suspense','startTransition','useTransition','useDeferredValue','useId'];
    for (var _hi = 0; _hi < _rh.length; _hi++) {
      if (React[_rh[_hi]]) window.__c[_rh[_hi]] = React[_rh[_hi]];
    }
    window.__c.React = React;
    window.__c.ReactDOM = ReactDOM;
    // Register CDN library exports on window.__c
    ${cdnLibs.registrations.join('\n    ')}
    function _showError(msg) {
      var root = document.getElementById('root');
      if (root) root.innerHTML =
        '<div style="padding:20px;color:#e74c3c;font-family:monospace;white-space:pre-wrap;font-size:13px">' +
        '<b>Render Error:</b>\\n' + String(msg) + '</div>';
    }
    window.onerror = function(msg) { _showError(msg); };
    // Manual transpile + eval for correct ordering
    var _sources = ${JSON.stringify(jsxSources)};
    try {
      for (var i = 0; i < _sources.length; i++) {
        var s = _sources[i];
        var code = Babel.transform(s.code, { presets: ['react'] }).code;
        (new Function(code))();
      }
      // Mount App with error boundary
      // Try window.App first, then window.__c.App, then any component registered last
      var _AppComponent = window.App || window.__c.App;
      if (!_AppComponent) {
        // Fallback: use the last registered component (App.jsx is sorted last)
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
            // Inline ErrorBoundary
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
    // === Springo: element click handler + error capture ===
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

      // Pin element on regular click (for design-mode-layout)
      document.addEventListener('click', function(e) {
        if (e.altKey) return;
        var el = e.target;
        if (!el || el === document.body || el === document.documentElement || el === document.getElementById('root')) return;
        // Walk up to find the nearest "component-like" ancestor (capitalized data attr or meaningful class)
        var compName = el.tagName.toLowerCase();
        var walkEl = el;
        while (walkEl && walkEl !== document.body) {
          // Check if this was a registered component via window.__c
          var dn = walkEl.getAttribute && walkEl.getAttribute('data-component');
          if (dn) { compName = dn; break; }
          // Use className as a hint
          if (walkEl.className && typeof walkEl.className === 'string') {
            var classes = walkEl.className.trim().split(/\s+/);
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

      // Error capture
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

      // Listen for tweak CSS variable updates from parent
      window.addEventListener('message', function(e) {
        if (e.data && e.data.type === 'springo:set-css-var') {
          document.documentElement.style.setProperty(e.data.name, e.data.value);
        }
      });

      // Blank screen detection: if #root is empty after 3s
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

export default function DesignCanvas({
  design,
  viewport,
  onTemplateSelect,
}: {
  design: DesignVersion | null;
  viewport: ViewportMode;
  onTemplateSelect?: (template: DesignTemplate) => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const lastSrcdocRef = useRef<string>('');
  const zoom = useDesignStore((s) => s.zoom);
  const interactionMode = useDesignStore((s) => s.interactionMode);

  const handleMessage = useCallback((e: MessageEvent) => {
    if (!e.data || typeof e.data.type !== 'string') return;
    if (e.data.type === 'springo:element-selected') {
      useDesignStore.getState().selectElement(e.data.payload);
    } else if (e.data.type === 'springo:element-pinned') {
      useDesignStore.getState().pinElement(e.data.payload);
    } else if (e.data.type === 'springo:error') {
      useDesignStore.getState().addError(e.data.payload);
    }
  }, []);

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  useEffect(() => {
    useDesignStore.getState().clearErrors();
    useDesignStore.getState().selectElement(null);
  }, [design?.id]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !design) return;
    let srcdoc: string;
    if (design.files && design.files.length > 0) {
      srcdoc = buildMultiFileRuntime(design.files, design.entryFile);
    } else {
      srcdoc = design.html;
    }
    // Skip identical reloads (streaming sends many updates with same content)
    if (srcdoc === lastSrcdocRef.current) return;
    lastSrcdocRef.current = srcdoc;
    iframe.srcdoc = srcdoc;
  }, [design?.html, design?.files, design?.entryFile]);

  if (!design) {
    return (
      <div className="design-canvas-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.3">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
        <p>Send a message to generate a design</p>
        <p className="design-canvas-empty-hint">or pick a template below</p>
        <DesignTemplateLibrary onSelect={(t) => onTemplateSelect?.(t)} />
      </div>
    );
  }

  const fixedWidth = VIEWPORT_WIDTHS[viewport];

  const zoomStyle = zoom !== 100 ? {
    transform: `scale(${zoom / 100})`,
    transformOrigin: 'top left',
    width: `${10000 / zoom}%`,
    height: `${10000 / zoom}%`,
  } : undefined;

  return (
    <div className={`design-canvas${interactionMode === 'comment' ? ' cursor-comment' : interactionMode === 'draw' ? ' cursor-draw' : ''}`}>
      <div
        className={`design-canvas-viewport design-canvas-viewport-${viewport}`}
        style={fixedWidth ? { width: fixedWidth, margin: '0 auto' } : undefined}
      >
        <iframe
          ref={iframeRef}
          className="design-canvas-iframe"
          style={zoomStyle}
          sandbox="allow-scripts allow-same-origin"
        />
      </div>
    </div>
  );
}
