import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useKBStore } from '@/stores/kbStore';
import type { KBGraph, KBNode, KBEdge, KBNodeType, KBNodeSource } from '@/stores/kbStore';
import Markdown from '@/components/common/Markdown';
import { prefillMessageInput } from '@/utils/prefillMessageInput';

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

/** Quick-aligned palette: stable color per entity type. */
const TYPE_COLOR: Record<KBNodeType, string> = {
  person:        '#ef4444', // red
  organization:  '#10b981', // emerald
  place:         '#0ea5e9', // sky
  event:         '#22c55e', // green
  product:       '#a78bfa', // violet
  service:       '#06b6d4', // cyan
  project:       '#14b8a6', // teal
  dataset:       '#eab308', // yellow
  creative_work: '#7dd3fc', // light sky
  defined_term:  '#f59e0b', // amber
  instruction:   '#fb923c', // orange
  action:        '#dc2626', // dark red
  channel:       '#67e8f9', // lighter cyan
  observation:   '#86efac', // light green
  decision:      '#b91c1c', // crimson
  occupation:    '#f97316', // orange-500
  dashboard:     '#8b5cf6', // purple
  message:       '#9ca3af', // gray
  visual:        '#5eead4', // light teal
};

const TYPE_LABEL: Record<KBNodeType, string> = {
  person: 'Person',
  organization: 'Organization',
  place: 'Place',
  event: 'Event',
  product: 'Product',
  service: 'Service',
  project: 'Project',
  dataset: 'Dataset',
  creative_work: 'Creative Work',
  defined_term: 'Defined Term',
  instruction: 'Instruction',
  action: 'Action',
  channel: 'Channel',
  observation: 'Observation',
  decision: 'Decision',
  occupation: 'Occupation',
  dashboard: 'Dashboard',
  message: 'Message',
  visual: 'Visual',
};

const TYPE_ORDER: KBNodeType[] = [
  'defined_term', 'product', 'service', 'creative_work', 'person',
  'event', 'organization', 'instruction', 'project', 'action',
  'channel', 'observation', 'decision', 'place', 'occupation',
  'dashboard', 'message', 'visual', 'dataset',
];

function nodeColor(node: KBNode): string {
  return TYPE_COLOR[node.node_type] ?? '#94a3b8';
}

function radiusForDegree(degree: number): number {
  // Quick-style constellation: tiny dots, hubs only mildly larger. Floor
  // at 2 so even orphans show; cap at 7 so hubs don't dominate.
  return Math.max(2, Math.min(7, 2 + Math.sqrt(degree) * 0.9));
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
  // Quick-style filter state. Empty selectedTypes set = "all types".
  const [selectedTypes, setSelectedTypes] = useState<Set<KBNodeType>>(new Set());
  const [selectedSources, setSelectedSources] = useState<Set<KBNodeSource>>(new Set());
  const [search, setSearch] = useState('');

  useEffect(() => { void loadGraph(); }, [loadGraph]);

  // Re-poll every 5s so the graph stays fresh while the AI is ingesting.
  useEffect(() => {
    const t = setInterval(() => { void loadGraph(); }, 5000);
    return () => clearInterval(t);
  }, [loadGraph]);

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  // Connection degree per node — drives node radius and is reused by sort.
  const degreeById = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of edges) {
      m.set(e.from, (m.get(e.from) ?? 0) + 1);
      m.set(e.to, (m.get(e.to) ?? 0) + 1);
    }
    return m;
  }, [edges]);

  // Type counts feed the sidebar. Always include all 19 categories so the
  // user sees the full vocabulary even when most are zero. Counts respect
  // the active source filter so type counts reflect what's actually visible.
  const typeCounts = useMemo(() => {
    const c: Record<KBNodeType, number> = Object.fromEntries(
      TYPE_ORDER.map((t) => [t, 0]),
    ) as Record<KBNodeType, number>;
    for (const n of nodes) {
      if (selectedSources.size > 0 && !selectedSources.has(n.source)) continue;
      c[n.node_type] = (c[n.node_type] ?? 0) + 1;
    }
    return c;
  }, [nodes, selectedSources]);

  // Source counts (for the chips). Always over the full node set.
  const sourceCounts = useMemo(() => {
    const c: Record<KBNodeSource, number> = { kb: 0, chat: 0, memory: 0 };
    for (const n of nodes) c[n.source] = (c[n.source] ?? 0) + 1;
    return c;
  }, [nodes]);

  // Filter: source ∩ type ∩ search prefix. Empty selection sets = no filter.
  const visibleNodes = useMemo(() => {
    const q = search.trim().toLowerCase();
    return nodes.filter((n) => {
      if (selectedSources.size > 0 && !selectedSources.has(n.source)) return false;
      if (selectedTypes.size > 0 && !selectedTypes.has(n.node_type)) return false;
      if (q && !n.title.toLowerCase().includes(q) && !n.id.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [nodes, selectedSources, selectedTypes, search]);

  const visibleNodeIds = useMemo(
    () => new Set(visibleNodes.map((n) => n.id)),
    [visibleNodes],
  );
  const visibleEdges = useMemo(
    () => edges.filter((e) => visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)),
    [edges, visibleNodeIds],
  );

  const toggleType = useCallback((t: KBNodeType) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  }, []);

  const toggleSource = useCallback((s: KBNodeSource) => {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s); else next.add(s);
      return next;
    });
  }, []);

  const clearFilters = useCallback(() => {
    setSelectedSources(new Set());
    setSelectedTypes(new Set());
    setSearch('');
  }, []);

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
            Ingest a document via the header's <strong>Knowledge → +</strong>{' '}
            button (top right), or ask the AI in chat to <em>"add this to KB"</em>.
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
        <KBEntitySidebar
          search={search}
          onSearchChange={setSearch}
          typeCounts={typeCounts}
          selectedTypes={selectedTypes}
          onToggleType={toggleType}
          sourceCounts={sourceCounts}
          selectedSources={selectedSources}
          onToggleSource={toggleSource}
          onClear={clearFilters}
          totalCount={nodes.length}
          visibleCount={visibleNodes.length}
        />
        <div className="kb-body-canvas">
          {view === 'graph' && (
            <KBGraphSVG
              nodes={nodes}
              edges={edges}
              visibleNodeIds={visibleNodeIds}
              degreeById={degreeById}
              hovered={hovered}
              onHover={setHovered}
              onNodeClick={openPage}
            />
          )}
          {view === 'list' && (
            <KBPageList nodes={visibleNodes} onOpen={openPage} />
          )}
        </div>
        {activePage && (
          <KBPageReader page={activePage} onClose={closePage} />
        )}
      </div>
    </div>
  );
}

const SOURCE_LABEL: Record<KBNodeSource, string> = {
  kb: 'KB', chat: 'Chat', memory: 'Memory',
};

function KBEntitySidebar({
  search,
  onSearchChange,
  typeCounts,
  selectedTypes,
  onToggleType,
  sourceCounts,
  selectedSources,
  onToggleSource,
  onClear,
  totalCount,
  visibleCount,
}: {
  search: string;
  onSearchChange: (v: string) => void;
  typeCounts: Record<KBNodeType, number>;
  selectedTypes: Set<KBNodeType>;
  onToggleType: (t: KBNodeType) => void;
  sourceCounts: Record<KBNodeSource, number>;
  selectedSources: Set<KBNodeSource>;
  onToggleSource: (s: KBNodeSource) => void;
  onClear: () => void;
  totalCount: number;
  visibleCount: number;
}) {
  const filtering =
    selectedSources.size > 0 || selectedTypes.size > 0 || search.trim() !== '';
  return (
    <aside className="kb-entity-sidebar">
      <div className="kb-entity-search">
        <input
          type="text"
          placeholder="Search entities..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>

      {/* Source chips — Quick-style row above the type list. Always show
          all three so the user knows what dimensions exist; chips with
          zero count appear dim and are uninteractive. */}
      <div className="kb-entity-chips">
        {(['kb', 'chat', 'memory'] as KBNodeSource[]).map((s) => {
          const count = sourceCounts[s] || 0;
          const visuallyActive = selectedSources.has(s);
          const filterActive = selectedSources.size > 0;
          // Dim when filter is active and this chip isn't selected, OR the
          // count is zero so the chip is informational only.
          const dimmed = count === 0 || (filterActive && !visuallyActive);
          return (
            <button
              key={s}
              className={`kb-entity-chip${visuallyActive ? ' active' : ''}`}
              onClick={() => count > 0 && onToggleSource(s)}
              title={count > 0 ? `Filter to ${SOURCE_LABEL[s]} only` : `${SOURCE_LABEL[s]} (no entries yet)`}
              disabled={count === 0}
              style={{ opacity: dimmed ? 0.45 : 1 }}
            >
              {SOURCE_LABEL[s]} <span className="kb-chip-count">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="kb-entity-toolbar">
        <span className="kb-entity-section-label">Entities</span>
        <span className="kb-entity-counts">
          {filtering ? `${visibleCount} / ${totalCount}` : totalCount}
        </span>
        {filtering && (
          <button className="kb-entity-clear" onClick={onClear} title="Clear filters">×</button>
        )}
      </div>
      <ul className="kb-entity-list">
        {TYPE_ORDER.map((t) => {
          const count = typeCounts[t] || 0;
          if (count === 0) return null;
          const active = selectedTypes.has(t);
          return (
            <li
              key={t}
              className={`kb-entity-row${active ? ' active' : ''}`}
              onClick={() => onToggleType(t)}
            >
              <span className="kb-entity-dot" style={{ background: TYPE_COLOR[t] }} />
              <span className="kb-entity-label">{TYPE_LABEL[t]}</span>
              <span className="kb-entity-count">{count}</span>
            </li>
          );
        })}
      </ul>
    </aside>
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
  visibleNodeIds,
  degreeById,
  hovered,
  onHover,
  onNodeClick,
}: {
  nodes: KBNode[];
  edges: KBEdge[];
  /** Subset to render. Layout always runs over all nodes so positions stay
   * stable when the user toggles filters. */
  visibleNodeIds: Set<string>;
  degreeById: Map<string, number>;
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
    // Stable pseudo-random per id so re-mounts get the same start positions.
    // The previous `i / N * 2π` ring scatter pinned topology — orphans on
    // the ring would never move because every neighbour repelled them
    // outward into the boundary clamp. A jittered start lets gravity
    // + repulsion actually find a relaxed layout.
    const seedFor = (id: string): number => {
      let h = 0;
      for (let k = 0; k < id.length; k++) h = (h * 131 + id.charCodeAt(k)) >>> 0;
      return h;
    };
    nodes.forEach((n) => {
      seen.add(n.id);
      if (!map.has(n.id)) {
        const s = seedFor(n.id);
        // Sample a disc around the centre with radius ≤ 180.
        const a = ((s & 0xffff) / 0xffff) * Math.PI * 2;
        const r = (((s >>> 16) & 0xffff) / 0xffff) * 180 + 20;
        map.set(n.id, {
          ...n,
          x: WIDTH / 2 + Math.cos(a) * r,
          y: HEIGHT / 2 + Math.sin(a) * r,
          vx: 0,
          vy: 0,
        });
      } else {
        const cur = map.get(n.id)!;
        Object.assign(cur, n);
      }
    });
    // Drop nodes no longer in graph.
    for (const id of Array.from(map.keys())) {
      if (!seen.has(id)) map.delete(id);
    }
  }, [nodes]);

  // Static-layout strategy: settle the simulation OFFSCREEN before any
  // render, then commit final positions in one paint. The user never sees
  // the graph "fly into place" — it just appears, like Quick's static
  // screenshot. Layouts are cached in localStorage by topology hash so
  // reopening the panel is instant.
  const [layoutReady, setLayoutReady] = useState(false);
  useEffect(() => {
    setLayoutReady(false);
    if (nodes.length === 0) {
      setLayoutReady(true);
      return;
    }

    // Topology key: sorted node ids + edge count. If it changes, we
    // recompute. Adding a single node won't reuse old positions.
    const topoKey = nodes.map((n) => n.id).sort().join('|') + `|${edges.length}`;
    const cacheKey = 'springo-kb-graph-layout-v2';
    let cache: Record<string, Record<string, { x: number; y: number }>> = {};
    try {
      cache = JSON.parse(localStorage.getItem(cacheKey) || '{}');
    } catch { /* ignore */ }

    const cached = cache[topoKey];
    if (cached) {
      // Hydrate sim map directly with cached coords — no simulation.
      const map = simNodesRef.current;
      for (const n of nodes) {
        const pos = cached[n.id];
        if (!pos) continue;
        const cur = map.get(n.id);
        if (cur) {
          cur.x = pos.x; cur.y = pos.y; cur.vx = 0; cur.vy = 0;
          Object.assign(cur, n);
        }
      }
      setLayoutReady(true);
      return;
    }

    // No cache: run the simulation in a tight loop until cool, THEN show.
    // Yield to the event loop occasionally so we don't block the UI thread
    // for the whole settle (large graphs can take ~50ms).
    let cancelled = false;
    const settle = async () => {
      const map = simNodesRef.current;
      const arr = Array.from(map.values());
      let alpha = 1;
      const ALPHA_DECAY = 0.022;
      const ALPHA_MIN = 0.01;
      const cx = WIDTH / 2;
      const cy = HEIGHT / 2;
      let iter = 0;

      while (alpha > ALPHA_MIN && iter < 400) {
        if (cancelled) return;

        const repulse = 2200 * alpha;
        for (let i = 0; i < arr.length; i++) {
          for (let j = i + 1; j < arr.length; j++) {
            const a = arr[i]; const b = arr[j];
            const dx = b.x - a.x; const dy = b.y - a.y;
            const dist2 = dx * dx + dy * dy + 0.01;
            const dist = Math.sqrt(dist2);
            const f = repulse / dist2;
            const fx = (dx / dist) * f;
            const fy = (dy / dist) * f;
            a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
          }
        }
        const springLen = 55;
        const springK = 0.05 * alpha;
        for (const e of edges) {
          const a = map.get(e.from); const b = map.get(e.to);
          if (!a || !b) continue;
          const dx = b.x - a.x; const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy + 0.01);
          const f = (dist - springLen) * springK;
          const fx = (dx / dist) * f;
          const fy = (dy / dist) * f;
          a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
        }
        const gravity = 0.0008 * alpha;
        for (const n of arr) {
          n.vx += (cx - n.x) * gravity;
          n.vy += (cy - n.y) * gravity;
          n.vx *= 0.85; n.vy *= 0.85;
          n.x += n.vx; n.y += n.vy;
          // Soft margin: nudge inward when within 40px of the edge instead
          // of hard-clamping. Hard clamp made orphans stick to the wall;
          // a spring-style nudge lets them rest a little inside the frame.
          const MARGIN = 40;
          if (n.x < MARGIN) n.x += (MARGIN - n.x) * 0.1;
          else if (n.x > WIDTH - MARGIN) n.x -= (n.x - (WIDTH - MARGIN)) * 0.1;
          if (n.y < MARGIN) n.y += (MARGIN - n.y) * 0.1;
          else if (n.y > HEIGHT - MARGIN) n.y -= (n.y - (HEIGHT - MARGIN)) * 0.1;
        }
        alpha -= ALPHA_DECAY;
        iter++;
        // Yield every 30 iterations so the input thread stays responsive.
        if (iter % 30 === 0) await new Promise((r) => setTimeout(r, 0));
      }

      if (cancelled) return;

      // Persist final positions.
      const positions: Record<string, { x: number; y: number }> = {};
      for (const n of arr) positions[n.id] = { x: n.x, y: n.y };
      try {
        cache[topoKey] = positions;
        // Cap cache to last 10 layouts to bound localStorage usage.
        const keys = Object.keys(cache);
        if (keys.length > 10) {
          for (const k of keys.slice(0, keys.length - 10)) delete cache[k];
        }
        localStorage.setItem(cacheKey, JSON.stringify(cache));
      } catch { /* quota — ignore */ }

      setLayoutReady(true);
    };
    void settle();
    return () => { cancelled = true; };
    // We re-run only when graph topology changes; filter changes don't.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, edges.length]);

  const sim = simNodesRef.current;
  // Edges drawn must satisfy: both endpoints in sim AND both in visible set.
  // Nodes drawn must be both in sim and in visible set.
  const showEdge = (e: KBEdge) =>
    sim.has(e.from) && sim.has(e.to) &&
    visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to);
  const visibleEdges = edges.filter(showEdge);

  // Only the top-N most-connected nodes get a permanent label. Everything
  // else stays a bare dot, and the user can hover to see its title. Quick
  // does the same — a constellation of dots with a few headline anchors.
  const HUB_LABEL_LIMIT = 25;
  const labeledIds = useMemo(() => {
    const ranked = [...nodes].sort(
      (a, b) => (degreeById.get(b.id) ?? 0) - (degreeById.get(a.id) ?? 0),
    );
    return new Set(ranked.slice(0, HUB_LABEL_LIMIT).map((n) => n.id));
  }, [nodes, degreeById]);

  // 1-hop neighbours of the hovered node — they get labels too so the user
  // can read the local context without us drowning everything else.
  const hoveredNeighbours = useMemo(() => {
    if (!hovered) return new Set<string>();
    const s = new Set<string>([hovered]);
    for (const e of edges) {
      if (e.from === hovered) s.add(e.to);
      if (e.to === hovered) s.add(e.from);
    }
    return s;
  }, [hovered, edges]);

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
          // Hard-dim every edge that's not in the hovered subgraph; this
          // is the single biggest legibility win on a dense graph.
          const dim = hovered && !active;
          return (
            <line
              key={`e-${i}`}
              x1={a.x} y1={a.y}
              x2={b.x} y2={b.y}
              stroke={active ? 'var(--accent)' : 'rgba(0,0,0,0.12)'}
              strokeWidth={active ? 1.5 : 0.5}
              opacity={dim ? 0.05 : (active ? 0.9 : 0.35)}
            />
          );
        })}
      </g>
      <g className="kb-nodes">
        {Array.from(sim.values()).filter((n) => visibleNodeIds.has(n.id)).map((n) => {
          const r = radiusForDegree(degreeById.get(n.id) ?? 0);
          const fill = nodeColor(n);
          const isHovered = hovered === n.id;
          const isHub = labeledIds.has(n.id);
          const showLabel = isHub || isHovered || hoveredNeighbours.has(n.id);
          // Dim non-related nodes when the user is hovering something so
          // the local context pops.
          const dim = hovered && !hoveredNeighbours.has(n.id);
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              style={{ cursor: 'pointer', opacity: dim ? 0.2 : 1 }}
              onMouseEnter={() => onHover(n.id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onNodeClick(n.id)}
            >
              <circle
                r={r}
                fill={fill}
                opacity={n.stale ? 0.45 : 1}
                stroke={n.orphan ? 'var(--error, #ef4444)' : isHovered ? 'var(--accent)' : 'rgba(0,0,0,0.15)'}
                strokeWidth={n.orphan || isHovered ? 2 : 0.5}
              />
              {showLabel && (
                <text
                  y={r + 10}
                  textAnchor="middle"
                  fontSize={isHovered ? 11 : 9}
                  fill="var(--text-primary)"
                  style={{ pointerEvents: 'none', userSelect: 'none' }}
                >
                  {n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title}
                </text>
              )}
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
    const placeholder = `修改 KB 页 [[${page.slug}]]: `;
    prefillMessageInput(placeholder, { prepend: true, caret: placeholder.length });
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
