import { create } from 'zustand';

export interface ToolPanelState {
  toolName: string;
  input: Record<string, unknown>;
  status: 'running' | 'complete' | 'error';
  result?: Record<string, unknown> | null;
}

export interface Toast {
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  duration: number;
}

export interface ActiveSkill {
  name: string;
  description: string;
}

export type RightPanelTab = 'tasks' | 'team' | 'schedules' | 'news';

export interface AskUserOption {
  label: string;
  description?: string;
}

export interface AskUserData {
  question: string;
  options: AskUserOption[];
  allowCustom: boolean;
  resolve: (answer: string) => void;
}

export interface PlanData {
  summary: string;
  steps: string[];
  files: string[];
}

export interface TodoItem {
  id: string;
  subject: string;
  status: 'pending' | 'in_progress' | 'completed';
  description?: string;
}

interface UIState {
  sidebarOpen: boolean;
  settingsOpen: boolean;
  toolPanelOpen: boolean;
  currentToolPanel: ToolPanelState | null;
  toast: Toast | null;
  imagePreview: string | null;
  teamModeEnabled: boolean;
  teamCollaborativeMode: boolean;
  activeTeamId: string | null;
  activeSkill: ActiveSkill | null;
  rightPanelOpen: boolean;
  rightPanelTab: RightPanelTab;
  askUserData: AskUserData | null;
  planModeActive: boolean;
  planApprovalData: PlanData | null;
  todos: TodoItem[];

  // Actions
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSettings: () => void;
  setSettingsOpen: (open: boolean) => void;
  toggleToolPanel: () => void;
  setToolPanelOpen: (open: boolean) => void;
  setCurrentToolPanel: (panel: ToolPanelState | null) => void;
  showToast: (message: string, type?: Toast['type'], duration?: number) => void;
  dismissToast: () => void;
  setImagePreview: (url: string | null) => void;
  setTeamModeEnabled: (enabled: boolean) => void;
  setTeamCollaborativeMode: (enabled: boolean) => void;
  cycleTeamMode: () => void;
  setActiveTeamId: (teamId: string | null) => void;
  setActiveSkill: (skill: ActiveSkill | null) => void;
  clearActiveSkill: () => void;
  toggleRightPanel: () => void;
  setRightPanelOpen: (open: boolean) => void;
  setRightPanelTab: (tab: RightPanelTab) => void;
  showAskUser: (data: AskUserData) => void;
  hideAskUser: () => void;
  setPlanModeActive: (active: boolean) => void;
  showPlanApproval: (plan: PlanData) => void;
  hidePlanApproval: () => void;
  setTodos: (todos: TodoItem[]) => void;
}

let toastTimer: ReturnType<typeof setTimeout> | null = null;

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  settingsOpen: false,
  toolPanelOpen: false,
  currentToolPanel: null,
  toast: null,
  imagePreview: null,
  teamModeEnabled: false,
  teamCollaborativeMode: false,
  activeTeamId: null,
  activeSkill: null,
  rightPanelOpen: false,
  rightPanelTab: 'tasks' as RightPanelTab,
  askUserData: null,
  planModeActive: false,
  planApprovalData: null,
  todos: [],

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  toggleSettings: () => set((state) => ({ settingsOpen: !state.settingsOpen })),
  setSettingsOpen: (open) => set({ settingsOpen: open }),

  toggleToolPanel: () =>
    set((state) => ({ toolPanelOpen: !state.toolPanelOpen })),
  setToolPanelOpen: (open) => set({ toolPanelOpen: open }),

  setCurrentToolPanel: (panel) =>
    set({ currentToolPanel: panel, toolPanelOpen: panel !== null }),

  showToast: (message, type = 'info', duration = 5000) => {
    if (toastTimer) {
      clearTimeout(toastTimer);
      toastTimer = null;
    }
    set({ toast: { message, type, duration } });
    toastTimer = setTimeout(() => {
      set({ toast: null });
      toastTimer = null;
    }, duration);
  },

  dismissToast: () => {
    if (toastTimer) {
      clearTimeout(toastTimer);
      toastTimer = null;
    }
    set({ toast: null });
  },

  setImagePreview: (url) => set({ imagePreview: url }),

  setTeamModeEnabled: (enabled) => set({ teamModeEnabled: enabled }),

  setTeamCollaborativeMode: (enabled) => set({ teamCollaborativeMode: enabled }),

  cycleTeamMode: () =>
    set((state) => {
      if (!state.teamModeEnabled) {
        // off -> classic (active, not collab)
        return { teamModeEnabled: true, teamCollaborativeMode: false };
      } else if (!state.teamCollaborativeMode) {
        // classic -> collaborative (active + collab)
        return { teamModeEnabled: true, teamCollaborativeMode: true };
      } else {
        // collaborative -> off
        return { teamModeEnabled: false, teamCollaborativeMode: false };
      }
    }),

  setActiveTeamId: (teamId) => set({ activeTeamId: teamId }),

  setActiveSkill: (skill) => set({ activeSkill: skill }),

  clearActiveSkill: () => set({ activeSkill: null }),

  toggleRightPanel: () =>
    set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),

  showAskUser: (data) => set({ askUserData: data }),
  hideAskUser: () => set({ askUserData: null }),
  setPlanModeActive: (active) => set({ planModeActive: active }),
  showPlanApproval: (plan) => set({ planApprovalData: plan }),
  hidePlanApproval: () => set({ planApprovalData: null, planModeActive: false }),
  setTodos: (todos) => set({ todos }),
}));
