/**
 * Springo Design Mode Store
 *
 * Manages design versions, viewport, design system config,
 * and per-session state persistence.
 */
import { create } from 'zustand';
import type { DesignVersion, DesignSystemConfig, DesignFile, SelectedElement, DesignError, Message, ContentBlock } from '../types';
import { extractModelArtifacts, parseSpringoFiles } from '../components/Visual/ArtifactRenderer';

export interface DesignComment {
  id: string;
  x: number;
  y: number;
  text: string;
  author: string;
  timestamp: number;
  resolved?: boolean;
}

export type ViewportMode = 'desktop' | 'tablet' | 'mobile';
export type DesignViewMode = 'preview' | 'code';
export type DesignInteractionMode = 'view' | 'comment' | 'edit' | 'draw';

interface SessionDesignSnapshot {
  active: boolean;
  versions: DesignVersion[];
  activeVersionIndex: number;
  designSystem: DesignSystemConfig | null;
  comments: DesignComment[];
}

export type VerificationStatus = 'ok' | 'warning' | 'error' | 'checking';

export interface DesignState {
  active: boolean;
  versions: DesignVersion[];
  activeVersionIndex: number;
  viewport: ViewportMode;
  viewMode: DesignViewMode;
  activeFilePath: string | null;
  designSystem: DesignSystemConfig | null;
  isExtractingDesignSystem: boolean;
  sessionMap: Record<string, SessionDesignSnapshot>;
  currentSessionId: string | null;
  selectedElement: SelectedElement | null;
  errors: DesignError[];
  verificationStatus: VerificationStatus;
  tweaksOpen: boolean;
  comparisonMode: boolean;
  zoom: number;
  interactionMode: DesignInteractionMode;
  presentMode: boolean;
  comments: DesignComment[];

  activateDesignMode: () => void;
  deactivateDesignMode: () => void;
  toggleDesignMode: () => void;
  addVersion: (version: DesignVersion) => void;
  updateVersion: (id: string, updates: Partial<Pick<DesignVersion, 'html' | 'files' | 'title' | 'entryFile'>>) => void;
  selectVersion: (index: number) => void;
  setViewport: (mode: ViewportMode) => void;
  setViewMode: (mode: DesignViewMode) => void;
  selectFile: (path: string) => void;
  setDesignSystem: (config: DesignSystemConfig | null) => void;
  setExtractingDesignSystem: (v: boolean) => void;
  switchSession: (sessionId: string | null) => void;
  currentDesign: () => DesignVersion | null;
  selectElement: (el: SelectedElement | null) => void;
  addError: (err: DesignError) => void;
  clearErrors: () => void;
  setVerificationStatus: (s: VerificationStatus) => void;
  setTweaksOpen: (open: boolean) => void;
  setComparisonMode: (on: boolean) => void;
  setZoom: (zoom: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  setInteractionMode: (mode: DesignInteractionMode) => void;
  setPresentMode: (on: boolean) => void;
  addComment: (comment: DesignComment) => void;
  removeComment: (id: string) => void;
  reloadCanvas: () => void;
  restoreFromMessages: (messages: Message[]) => void;
}

let designIdCounter = 0;

export function createDesignId(): string {
  return `design-${++designIdCounter}-${Date.now()}`;
}

export const useDesignStore = create<DesignState>((set, get) => ({
  active: false,
  versions: [],
  activeVersionIndex: -1,
  viewport: 'desktop',
  viewMode: 'preview',
  activeFilePath: null,
  designSystem: null,
  isExtractingDesignSystem: false,
  sessionMap: {},
  currentSessionId: null,
  selectedElement: null,
  errors: [],
  verificationStatus: 'ok',
  tweaksOpen: false,
  comparisonMode: false,
  zoom: 100,
  interactionMode: 'view',
  presentMode: false,
  comments: [],

  activateDesignMode: () => set({ active: true }),

  deactivateDesignMode: () => set({ active: false }),

  toggleDesignMode: () => set((s) => ({ active: !s.active })),

  addVersion: (version) =>
    set((state) => {
      // Ensure files array exists for backward compat
      const v = { ...version, files: version.files ?? [] };
      const versions = [...state.versions, v];
      // Auto-select entry file for multi-file projects
      const activeFilePath = v.files.length > 0
        ? (v.entryFile || v.files.find(f => f.path === 'index.html')?.path || v.files[0]?.path || null)
        : null;
      return {
        versions,
        activeVersionIndex: versions.length - 1,
        activeFilePath,
        viewMode: 'preview' as DesignViewMode,
      };
    }),

  updateVersion: (id, updates) =>
    set((state) => {
      const idx = state.versions.findIndex((v) => v.id === id);
      if (idx === -1) return state;
      const updated = { ...state.versions[idx], ...updates };
      const versions = [...state.versions];
      versions[idx] = updated;
      return { versions };
    }),

  selectVersion: (index) => {
    const { versions } = get();
    if (index >= 0 && index < versions.length) {
      set({ activeVersionIndex: index });
    }
  },

  setViewport: (mode) => set({ viewport: mode }),

  setViewMode: (mode) => set({ viewMode: mode, ...(mode !== 'preview' ? { interactionMode: 'view' as DesignInteractionMode } : {}) }),

  selectFile: (path) => set({ activeFilePath: path }),

  setDesignSystem: (config) => set({ designSystem: config }),

  setExtractingDesignSystem: (v) => set({ isExtractingDesignSystem: v }),

  switchSession: (sessionId) => {
    const { currentSessionId, active, versions, activeVersionIndex, designSystem, sessionMap, comments } = get();

    const updatedMap = { ...sessionMap };
    if (currentSessionId) {
      updatedMap[currentSessionId] = { active, versions, activeVersionIndex, designSystem, comments };
    }

    const restored = sessionId ? updatedMap[sessionId] : null;

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      active: restored ? restored.active : active,
      versions: restored?.versions ?? [],
      activeVersionIndex: restored?.activeVersionIndex ?? -1,
      designSystem: restored?.designSystem ?? null,
      comments: restored?.comments ?? [],
      interactionMode: 'view',
    });
  },

  currentDesign: () => {
    const { versions, activeVersionIndex } = get();
    if (activeVersionIndex >= 0 && activeVersionIndex < versions.length) {
      return versions[activeVersionIndex];
    }
    return null;
  },

  selectElement: (el) => set({ selectedElement: el }),

  addError: (err) => set((s) => ({
    errors: [...s.errors.slice(-49), err],
    verificationStatus: 'error',
  })),

  clearErrors: () => set({ errors: [], verificationStatus: 'ok' }),

  setVerificationStatus: (status) => set({ verificationStatus: status }),

  setTweaksOpen: (open) => set({ tweaksOpen: open }),

  setComparisonMode: (on) => set({ comparisonMode: on }),

  setZoom: (zoom) => set({ zoom: Math.max(25, Math.min(200, zoom)) }),

  zoomIn: () => set((s) => ({ zoom: Math.min(200, s.zoom + 25) })),

  zoomOut: () => set((s) => ({ zoom: Math.max(25, s.zoom - 25) })),

  resetZoom: () => set({ zoom: 100 }),

  setInteractionMode: (mode) => set({ interactionMode: mode }),

  setPresentMode: (on) => set({ presentMode: on }),

  addComment: (comment) => set((s) => ({ comments: [...s.comments, comment] })),

  removeComment: (id) => set((s) => ({ comments: s.comments.filter((c) => c.id !== id) })),

  reloadCanvas: () => {
    const { versions, activeVersionIndex } = get();
    if (activeVersionIndex < 0 || activeVersionIndex >= versions.length) return;
    const v = versions[activeVersionIndex];
    const cloned = { ...v, id: v.id + '-reload-' + Date.now() };
    const updated = [...versions];
    updated[activeVersionIndex] = cloned;
    set({ versions: updated });
  },

  restoreFromMessages: (messages) => {
    if (get().versions.length > 0) return;

    function extractText(content: string | ContentBlock[] | undefined): string {
      if (!content) return '';
      if (typeof content === 'string') return content;
      if (Array.isArray(content)) {
        return content
          .map((c) => {
            if (typeof c === 'string') return c;
            if (c.type === 'text') return (c as any).text || '';
            return '';
          })
          .filter(Boolean)
          .join('\n');
      }
      return '';
    }

    const versions: DesignVersion[] = [];
    for (const msg of messages) {
      if (msg.role !== 'assistant') continue;
      const text = msg.mergedContent || (msg.displayContent as string | undefined) || extractText(msg.content);
      if (!text) continue;
      const { artifacts } = extractModelArtifacts(text);
      for (let ai = 0; ai < artifacts.length; ai++) {
        const a = artifacts[ai];
        const isProject = (a as any)._isProject === true;
        const isHtml = a.type === 'html' && !isProject;
        if (!isProject && !isHtml) continue;
        const id = `design-restored-${versions.length}`;
        const title = a.title || `Design v${versions.length + 1}`;
        const ts = msg.timestamp || Date.now();
        if (isProject) {
          const files = parseSpringoFiles(a.content);
          versions.push({
            id, html: '', files, title, prompt: '', timestamp: ts,
            entryFile: files.find((f: DesignFile) => f.path === 'index.html')?.path || files[0]?.path,
          });
        } else {
          versions.push({ id, html: a.content, files: [], title, prompt: '', timestamp: ts });
        }
      }
    }

    if (versions.length > 0) {
      const last = versions[versions.length - 1];
      set({
        versions,
        activeVersionIndex: versions.length - 1,
        activeFilePath: last.files.length > 0
          ? (last.entryFile || last.files.find(f => f.path === 'index.html')?.path || last.files[0]?.path || null)
          : null,
      });
    }
  },
}));

/** Selector: returns the active design version or null. Use in components to avoid duplicating bounds checks. */
export function selectCurrentDesign(s: DesignState): DesignVersion | null {
  const { versions, activeVersionIndex } = s;
  if (activeVersionIndex >= 0 && activeVersionIndex < versions.length) {
    return versions[activeVersionIndex];
  }
  return null;
}

// Expose for testing/debugging
if (typeof window !== 'undefined') (window as any).__designStore = useDesignStore;
