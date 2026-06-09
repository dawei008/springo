/**
 * Local Knowledge Base store.
 *
 * Thin client over /v1/kb/*. Truth lives on disk in ~/.springo/kb/wiki/;
 * the store mirrors graph.json + page list for fast UI reads. Writes go
 * straight to the backend; we don't keep a second source of truth.
 *
 * Inspired by Karpathy's "LLM Wiki" gist: markdown is canonical, the
 * graph is a derived view, no DB.
 */
import { create } from 'zustand';

const BASE_URL = 'http://127.0.0.1:8081';

export interface KBPage {
  slug: string;
  title: string;
  tags: string[];
  last_updated: string | null;
  size_bytes: number;
  modified: number;
}

/** 19 entity categories aligned with Quick Knowledge Graph. The backend
 * normalizes any frontmatter ``node_type`` value into this list (or
 * 'creative_work' as fallback). */
export type KBNodeType =
  | 'person' | 'organization' | 'place' | 'event'
  | 'product' | 'service' | 'project' | 'dataset'
  | 'creative_work' | 'defined_term' | 'instruction'
  | 'action' | 'channel' | 'observation' | 'decision'
  | 'occupation' | 'dashboard' | 'message' | 'visual';

/** Where this entity originates — drives the source filter chips. */
export type KBNodeSource = 'kb' | 'chat' | 'memory';

export interface KBNode {
  id: string;
  title: string;
  tags: string[];
  /** Quick-style entity category. Defaults to 'creative_work' for legacy pages. */
  node_type: KBNodeType;
  /** Origin store — KB wiki page, derived from chat history, or a memory file. */
  source: KBNodeSource;
  claim_count: number;
  source_count: number;
  last_updated: string | null;
  stale: boolean;
  orphan: boolean;
}

export interface KBEdge {
  from: string;
  to: string;
  kind: string;
}

export interface KBGraphStats {
  page_count: number;
  edge_count: number;
  orphan_count: number;
  stale_count: number;
  raw_count: number;
  raw_total_bytes: number;
}

export interface KBGraph {
  generated_at: string;
  nodes: KBNode[];
  edges: KBEdge[];
  raw_index: Array<{ path: string; size_bytes: number }>;
  stats: KBGraphStats;
}

export interface KBPageDetail {
  slug: string;
  title: string;
  frontmatter: Record<string, unknown>;
  body: string;
  raw: string;
}

interface KBState {
  pages: KBPage[];
  graph: KBGraph | null;
  activePage: KBPageDetail | null;
  loading: boolean;
  error: string | null;

  loadPages: () => Promise<void>;
  loadGraph: () => Promise<void>;
  openPage: (slug: string) => Promise<void>;
  closePage: () => void;
  ingestText: (input: { title: string; content: string; source_url?: string }) => Promise<{ raw_path: string } | null>;
  writePage: (slug: string, content: string) => Promise<boolean>;
  lint: () => Promise<{ findings: Record<string, unknown>; summary: Record<string, number> } | null>;
}

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export const useKBStore = create<KBState>((set) => ({
  pages: [],
  graph: null,
  activePage: null,
  loading: false,
  error: null,

  loadPages: async () => {
    set({ loading: true, error: null });
    try {
      const r = await api<{ pages: KBPage[] }>('GET', '/v1/kb/pages');
      set({ pages: r.pages ?? [], loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  loadGraph: async () => {
    try {
      const g = await api<KBGraph>('GET', '/v1/kb/graph');
      set({ graph: g });
    } catch (e) {
      console.warn('[kb] loadGraph failed', (e as Error).message);
    }
  },

  openPage: async (slug) => {
    try {
      const detail = await api<KBPageDetail>('GET', `/v1/kb/pages/${encodeURIComponent(slug)}`);
      set({ activePage: detail });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  closePage: () => set({ activePage: null }),

  ingestText: async ({ title, content, source_url }) => {
    try {
      const r = await api<{ raw_path: string }>('POST', '/v1/kb/ingest/text', {
        title,
        content,
        source_url: source_url ?? null,
      });
      // Don't reload pages — text ingestion only writes to raw/, not wiki/.
      // The user (or AI) is expected to follow up by writing wiki pages.
      return r;
    } catch (e) {
      console.warn('[kb] ingestText failed', (e as Error).message);
      return null;
    }
  },

  writePage: async (slug, content) => {
    try {
      await api('PUT', `/v1/kb/pages/${encodeURIComponent(slug)}`, { slug, content });
      // Refresh the page list + graph so the UI stays consistent.
      const [pages, graph] = await Promise.all([
        api<{ pages: KBPage[] }>('GET', '/v1/kb/pages'),
        api<KBGraph>('GET', '/v1/kb/graph'),
      ]);
      set({ pages: pages.pages ?? [], graph });
      return true;
    } catch (e) {
      console.warn('[kb] writePage failed', (e as Error).message);
      return false;
    }
  },

  lint: async () => {
    try {
      return await api('POST', '/v1/kb/lint');
    } catch (e) {
      console.warn('[kb] lint failed', (e as Error).message);
      return null;
    }
  },
}));
