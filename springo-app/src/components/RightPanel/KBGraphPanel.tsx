import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useKBStore } from '@/stores/kbStore';
import type { KBGraph, KBNode, KBEdge } from '@/stores/kbStore';
import Markdown from '@/components/common/Markdown';

/**
 * Knowledge Base graph panel — renders ~/.springo/kb/graph.json as an
 * interactive SVG force-directed layout. Click a node to read its wiki
 * page; double-click to prefill chat with "tell me about [[slug]]".
 *
 * No d3 dependency — we run a small Verlet-style simulation in a useEffect
 * so we don't pull in 100+ KB just for layout. Adequate up to a few
 * hundred nodes; if KB grows past that, swap in d3-force without changing
 * the rest of the panel.
 */

const WIDTH = 800;
const HEIGHT = 600;

interface SimNode extends KBNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

function tagColor(tag: string | undefined): string {
  if (!tag) return '#94a3b8';
  // Stable hue from tag string.
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360}, 55%, 55%)`;
}

function radiusFor(claimCount: number): number {
  return Math.max(6, Math.min(28, 6 + Math.sqrt(claimCount) * 4));
}

export default function KBGraphPanel() {
  const graph = useKBStore((s) => s.graph);
  const activePage = useKBStore((s) => s.activePage);
  const loadGraph = useKBStore((s) => s.loadGraph);
  const openPage = useKBStore((s) => s.openPage);
  const closePage = useKBStore((s) => s.closePage);
  const lint = useKBStore((s) => s.lint);
  const [view, setView] = useState<'graph' | 'list'>('graph');
  const [linting, setLinting] = useState(false);
  const [lintReport, setLintReport] = useState<Record<string, number> | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => { void loadGraph(); }, [loadGraph]);

  // Re-poll every 5s so the graph stays fresh while the AI is ingesting.
  useEffect(() => {
    const t = setInterval(() => { void loadGraph(); }, 5000);
    return () => clearInterval(t);
  }, [loadGraph]);

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  if (graph && nodes.length === 0) {
    return (
      <div className="kb-panel">
        <KBHeader graph={graph} onLint={async () => {
          setLinting(true);
          const r = await lint();
          setLinting(false);
          if (r) setLintReport(r.summary);
        }} linting={linting} lintReport={lintReport} />
        <div className="kb-empty">
          <h3>Your knowledge base is empty</h3>
          <p style={{ color: 'var(--text-secondary)', maxWidth: 480, lineHeight: 1.6 }}>
            Ingest a document via the sidebar's <strong>Knowledge → +</strong>{' '}
            button, or ask the AI in chat to <em>"add this to KB"</em>.
            New pages will appear as nodes here, with see-also links rendered as edges.
          </p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 12, maxWidth: 480 }}>
            See <code>~/.springo/kb/CLAUDE.md</code> for the full schema.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="kb-panel">
      <KBHeader graph={graph} onLint={async () => {
        setLinting(true);
        const r = await lint();
        setLinting(false);
        if (r) setLintReport(r.summary);
        await loadGraph();
      }} linting={linting} lintReport={lintReport} view={view} onViewChange={setView} />
      <div className="kb-body">
        {view === 'graph' && (
          <KBGraphSVG
            nodes={nodes}
            edges={edges}
            hovered={hovered}
            onHover={setHovered}
            onNodeClick={openPage}
          />
        )}
        {view === 'list' && (
          <KBPageList nodes={nodes} onOpen={openPage} />
        )}
        {activePage && (
          <KBPageReader page={activePage} onClose={closePage} />
        )}
      </div>
    </div>
  );
}

function KBHeader({
  graph,
  onLint,
  linting,
  lintReport,
  view,
  onViewChange,
}: {
  graph: KBGraph | null;
  onLint: () => void;
  linting: boolean;
  lintReport: Record<string, number> | null;
  view?: 'graph' | 'list';
  onViewChange?: (v: 'graph' | 'list') => void;
}) {
  const stats = graph?.stats;
  return (
    <div className="kb-header">
      <div className="kb-status">
        {stats ? (
          <>
            <strong>{stats.page_count}</strong> pages ·{' '}
            <strong>{stats.raw_count}</strong> sources ·{' '}
            <span className={stats.orphan_count ? 'kb-warn' : ''}>
              {stats.orphan_count} orphan{stats.orphan_count === 1 ? '' : 's'}
            </span>
            {' · '}
            <span className={stats.stale_count ? 'kb-warn' : ''}>
              {stats.stale_count} stale
            </span>
          </>
        ) : (
          <span style={{ color: 'var(--text-tertiary)' }}>Loading…</span>
        )}
        {lintReport && (
          <span style={{ marginLeft: 12, fontSize: 11, color: 'var(--text-tertiary)' }}>
            Lint: {Object.entries(lintReport).filter(([, v]) => v > 0).map(([k, v]) => `${k}:${v}`).join(' · ') || 'all clean'}
          </span>
        )}
      </div>
      <div className="kb-header-actions">
        {onViewChange && (
          <div className="kb-view-toggle">
            <button className={view === 'graph' ? 'active' : ''} onClick={() => onViewChange('graph')}>Graph</button>
            <button className={view === 'list' ? 'active' : ''} onClick={() => onViewChange('list')}>List</button>
          </div>
        )}
        <button onClick={onLint} disabled={linting}>{linting ? 'Linting…' : 'Lint'}</button>
      </div>
    </div>
  );
}

function KBGraphSVG({
  nodes,
  edges,
  hovered,
  onHover,
  onNodeClick,
}: {
  nodes: KBNode[];
  edges: KBEdge[];
  hovered: string | null;
  onHover: (id: string | null) => void;
  onNodeClick: (slug: string) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [, forceRender] = useState(0);
  const simNodesRef = useRef<Map<string, SimNode>>(new Map());

  // Initialize / update simulation nodes when graph changes.
  useEffect(() => {
    const map = simNodesRef.current;
    const seen = new Set<string>();
    nodes.forEach((n, i) => {
      seen.add(n.id);
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
      const r = 200;
      if (!map.has(n.id)) {
        map.set(n.id, {
          ...n,
          x: WIDTH / 2 + Math.cos(angle) * r,
          y: HEIGHT / 2 + Math.sin(angle) * r,
          vx: 0,
          vy: 0,
        });
      } else {
        // Refresh data fields but keep position.
        const cur = map.get(n.id)!;
        Object.assign(cur, n);
      }
    });
    // Drop nodes no longer in graph.
    for (const id of Array.from(map.keys())) {
      if (!seen.has(id)) map.delete(id);
    }
  }, [nodes]);

  // Force-directed simulation tick.
  useEffect(() => {
    let stopped = false;
    let frame = 0;

    const tick = () => {
      if (stopped) return;
      const map = simNodesRef.current;
      const arr = Array.from(map.values());

      // Repulsion (O(n²) — fine up to ~300 nodes).
      const repulse = 1200;
      for (let i = 0; i < arr.length; i++) {
        for (let j = i + 1; j < arr.length; j++) {
          const a = arr[i];
          const b = arr[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist2 = dx * dx + dy * dy + 0.01;
          const dist = Math.sqrt(dist2);
          const f = repulse / dist2;
          const fx = (dx / dist) * f;
          const fy = (dy / dist) * f;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      // Spring along edges.
      const springLen = 110;
      const springK = 0.04;
      for (const e of edges) {
        const a = map.get(e.from);
        const b = map.get(e.to);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy + 0.01);
        const f = (dist - springLen) * springK;
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Center gravity + integrate.
      const cx = WIDTH / 2;
      const cy = HEIGHT / 2;
      for (const n of arr) {
        n.vx += (cx - n.x) * 0.002;
        n.vy += (cy - n.y) * 0.002;
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x += n.vx;
        n.y += n.vy;
        n.x = Math.max(20, Math.min(WIDTH - 20, n.x));
        n.y = Math.max(20, Math.min(HEIGHT - 20, n.y));
      }

      forceRender((t) => t + 1);
      frame++;
      // Slow down once warm — saves CPU when idle.
      const delay = frame > 200 ? 200 : 16;
      setTimeout(tick, delay);
    };

    tick();
    return () => { stopped = true; };
    // We deliberately re-run the loop only when graph topology changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, edges.length]);

  const sim = simNodesRef.current;
  const visibleEdges = edges.filter((e) => sim.has(e.from) && sim.has(e.to));

  return (
    <svg
      ref={svgRef}
      className="kb-graph-svg"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <g className="kb-edges">
        {visibleEdges.map((e, i) => {
          const a = sim.get(e.from)!;
          const b = sim.get(e.to)!;
          const active = hovered === e.from || hovered === e.to;
          return (
            <line
              key={`e-${i}`}
              x1={a.x} y1={a.y}
              x2={b.x} y2={b.y}
              stroke={active ? 'var(--accent)' : 'var(--border-strong, rgba(0,0,0,0.18))'}
              strokeWidth={active ? 2 : 1}
              opacity={active ? 0.9 : 0.45}
            />
          );
        })}
      </g>
      <g className="kb-nodes">
        {Array.from(sim.values()).map((n) => {
          const r = radiusFor(n.claim_count);
          const fill = tagColor(n.tags?.[0]);
          const isHovered = hovered === n.id;
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => onHover(n.id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onNodeClick(n.id)}
            >
              <circle
                r={r}
                fill={fill}
                opacity={n.stale ? 0.45 : 1}
                stroke={n.orphan ? 'var(--error, #ef4444)' : isHovered ? 'var(--accent)' : 'rgba(0,0,0,0.15)'}
                strokeWidth={n.orphan || isHovered ? 2 : 1}
              />
              <text
                y={r + 12}
                textAnchor="middle"
                fontSize={11}
                fill="var(--text-primary)"
                style={{ pointerEvents: 'none', userSelect: 'none' }}
              >
                {n.title.length > 24 ? n.title.slice(0, 22) + '…' : n.title}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function KBPageList({ nodes, onOpen }: { nodes: KBNode[]; onOpen: (slug: string) => void }) {
  const sorted = useMemo(
    () => [...nodes].sort((a, b) => (b.claim_count || 0) - (a.claim_count || 0)),
    [nodes],
  );
  return (
    <div className="kb-list">
      {sorted.map((n) => (
        <button key={n.id} className="kb-list-item" onClick={() => onOpen(n.id)}>
          <div className="kb-list-item-title">
            {n.title}
            {n.orphan && <span className="kb-badge kb-badge-warn">orphan</span>}
            {n.stale && <span className="kb-badge">stale</span>}
          </div>
          <div className="kb-list-item-meta">
            {n.claim_count} claim{n.claim_count === 1 ? '' : 's'} ·{' '}
            {n.source_count} source{n.source_count === 1 ? '' : 's'}
            {n.tags && n.tags.length > 0 && (
              <> · {n.tags.map((t) => `#${t}`).join(' ')}</>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

function KBPageReader({
  page,
  onClose,
}: {
  page: { slug: string; title: string; body: string; raw: string };
  onClose: () => void;
}) {
  const editIngest = useCallback(() => {
    const el = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (!el) return;
    const placeholder = `修改 KB 页 [[${page.slug}]]: `;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(el, placeholder + (el.value || ''));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.focus();
    try { el.setSelectionRange(placeholder.length, placeholder.length); } catch { /* ignore */ }
  }, [page.slug]);

  return (
    <div className="kb-reader">
      <div className="kb-reader-header">
        <span className="kb-reader-title">{page.title}</span>
        <span className="kb-reader-slug">[[{page.slug}]]</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button onClick={editIngest} title="Prefill chat to edit this page">Edit with chat</button>
          <button onClick={onClose} title="Close">✕</button>
        </div>
      </div>
      <div className="kb-reader-body">
        <Markdown content={page.body} />
      </div>
    </div>
  );
}
