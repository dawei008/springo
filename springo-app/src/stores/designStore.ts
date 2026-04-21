/**
 * Springo Design Mode Store
 *
 * Manages design versions, viewport, design system config,
 * and per-session state persistence.
 */
import { create } from 'zustand';
import type { DesignVersion, DesignSystemConfig, DesignFile, SelectedElement, DesignError } from '../types';

export type ViewportMode = 'desktop' | 'tablet' | 'mobile';
export type DesignViewMode = 'preview' | 'code';

interface SessionDesignSnapshot {
  active: boolean;
  versions: DesignVersion[];
  activeVersionIndex: number;
  designSystem: DesignSystemConfig | null;
}

export type VerificationStatus = 'ok' | 'warning' | 'error' | 'checking';

interface DesignState {
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

  setViewMode: (mode) => set({ viewMode: mode }),

  selectFile: (path) => set({ activeFilePath: path }),

  setDesignSystem: (config) => set({ designSystem: config }),

  setExtractingDesignSystem: (v) => set({ isExtractingDesignSystem: v }),

  switchSession: (sessionId) => {
    const { currentSessionId, active, versions, activeVersionIndex, designSystem, sessionMap } = get();

    const updatedMap = { ...sessionMap };
    if (currentSessionId) {
      updatedMap[currentSessionId] = { active, versions, activeVersionIndex, designSystem };
    }

    const restored = sessionId ? updatedMap[sessionId] : null;

    set({
      sessionMap: updatedMap,
      currentSessionId: sessionId,
      // Preserve current active state for new sessions (no snapshot yet)
      // This handles the race where /design activates design mode before
      // switchSession runs via useEffect
      active: restored ? restored.active : active,
      versions: restored?.versions ?? [],
      activeVersionIndex: restored?.activeVersionIndex ?? -1,
      designSystem: restored?.designSystem ?? null,
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
}));

// Expose for testing/debugging
if (typeof window !== 'undefined') (window as any).__designStore = useDesignStore;
