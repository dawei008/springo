/**
 * Springo Plan Mode Store
 *
 * Manages plan generation, review, and execution state.
 */
import { create } from 'zustand';
import type { PlanStructure, PlanSection } from '../types';
import { api } from '../services/api';

interface PlanStoreState {
  // State
  currentPlan: PlanStructure | null;
  isGenerating: boolean;
  isExecuting: boolean;
  activeSection: string | null;
  error: string | null;
  regeneratingSections: Set<string>;

  // Actions
  generatePlan: (taskDescription: string, sessionId?: string, model?: string) => Promise<void>;
  setCurrentPlan: (plan: PlanStructure | null) => void;
  updateSection: (sectionId: string, updates: Partial<PlanSection>) => void;
  approveSection: (sectionId: string) => Promise<void>;
  rejectSection: (sectionId: string, feedback: string) => Promise<void>;
  skipSection: (sectionId: string) => void;
  approveAll: () => Promise<void>;
  executePlan: (sessionId: string) => Promise<void>;
  setActiveSection: (sectionId: string | null) => void;
  clearPlan: () => void;
  clearError: () => void;
}

export const usePlanStore = create<PlanStoreState>((set, get) => ({
  currentPlan: null,
  isGenerating: false,
  isExecuting: false,
  activeSection: null,
  error: null,
  regeneratingSections: new Set(),

  generatePlan: async (taskDescription, sessionId, model) => {
    set({ isGenerating: true, error: null, currentPlan: null });

    try {
      const response = await api.plans.generate({
        task_description: taskDescription,
        session_id: sessionId,
        model: model || undefined,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);

              if (event.type === 'plan_generated' && event.plan) {
                const plan = event.plan as PlanStructure;
                set({
                  currentPlan: plan,
                  activeSection: plan.sections[0]?.id || null,
                });
              } else if (event.type === 'error') {
                set({ error: event.error?.message || 'Plan generation failed' });
              }
            } catch {
              // skip unparseable lines
            }
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    } finally {
      set({ isGenerating: false });
    }
  },

  setCurrentPlan: (plan) => set({ currentPlan: plan, activeSection: plan?.sections[0]?.id || null }),

  updateSection: (sectionId, updates) => {
    const plan = get().currentPlan;
    if (!plan) return;

    const sections = plan.sections.map((s) =>
      s.id === sectionId ? { ...s, ...updates } : s
    );
    set({ currentPlan: { ...plan, sections } });
  },

  approveSection: async (sectionId) => {
    const plan = get().currentPlan;
    if (!plan) return;

    try {
      await api.plans.feedback(plan.id, {
        section_id: sectionId,
        action: 'approve',
      });

      get().updateSection(sectionId, { status: 'approved' });

      // Check if all approved
      const updated = get().currentPlan;
      if (updated && updated.sections.every((s) => s.status === 'approved')) {
        set({ currentPlan: { ...updated, status: 'approved' } });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    }
  },

  rejectSection: async (sectionId, feedback) => {
    const plan = get().currentPlan;
    if (!plan) return;

    // Mark as regenerating
    const regen = new Set(get().regeneratingSections);
    regen.add(sectionId);
    set({ regeneratingSections: regen });
    get().updateSection(sectionId, { status: 'rejected', feedback });

    try {
      // This returns SSE stream with regenerated section
      const response = await api.plans.feedbackStream(plan.id, {
        section_id: sectionId,
        action: 'reject',
        feedback,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      // Check if it's SSE (reject with feedback) or JSON (reject without)
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('text/event-stream')) {
        const reader = response.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim();
              if (data === '[DONE]') continue;

              try {
                const event = JSON.parse(data);
                if (event.type === 'plan_section_update' && event.section) {
                  get().updateSection(sectionId, event.section);
                }
              } catch {
                // skip
              }
            }
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    } finally {
      const done = new Set(get().regeneratingSections);
      done.delete(sectionId);
      set({ regeneratingSections: done });
    }
  },

  skipSection: (sectionId) => {
    get().updateSection(sectionId, { status: 'rejected' });
  },

  approveAll: async () => {
    const plan = get().currentPlan;
    if (!plan) return;

    try {
      const resp = await api.plans.approveAll(plan.id);
      if (resp.data?.plan) {
        set({ currentPlan: resp.data.plan });
      } else {
        // Manually approve all pending
        const sections = plan.sections.map((s) =>
          s.status === 'pending' ? { ...s, status: 'approved' as const } : s
        );
        set({ currentPlan: { ...plan, sections, status: 'approved' } });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    }
  },

  executePlan: async (sessionId) => {
    const plan = get().currentPlan;
    if (!plan) return;

    set({ isExecuting: true, error: null });

    try {
      const response = await api.plans.execute(plan.id, sessionId);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);

              if (event.type === 'plan_section_start') {
                get().updateSection(event.section_id, { status: 'in_progress' });
              } else if (event.type === 'plan_section_complete') {
                get().updateSection(event.section_id, {
                  status: event.success ? 'completed' : 'failed',
                  result: event.error || 'Completed',
                });
              } else if (event.type === 'plan_execution_complete') {
                const updated = get().currentPlan;
                if (updated) {
                  set({
                    currentPlan: { ...updated, status: event.success ? 'completed' : 'failed' },
                  });
                }
              }
            } catch {
              // skip
            }
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    } finally {
      set({ isExecuting: false });
    }
  },

  setActiveSection: (sectionId) => set({ activeSection: sectionId }),
  clearPlan: () => set({ currentPlan: null, isGenerating: false, isExecuting: false, activeSection: null, error: null }),
  clearError: () => set({ error: null }),
}));
