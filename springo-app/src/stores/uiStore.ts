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

interface UIState {
  sidebarOpen: boolean;
  settingsOpen: boolean;
  toolPanelOpen: boolean;
  currentToolPanel: ToolPanelState | null;
  toast: Toast | null;
  imagePreview: string | null;
  teamModeEnabled: boolean;
  activeTeamId: string | null;
  activeSkill: ActiveSkill | null;

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
  setActiveTeamId: (teamId: string | null) => void;
  setActiveSkill: (skill: ActiveSkill | null) => void;
  clearActiveSkill: () => void;
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
  activeTeamId: null,
  activeSkill: null,

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

  setActiveTeamId: (teamId) => set({ activeTeamId: teamId }),

  setActiveSkill: (skill) => set({ activeSkill: skill }),

  clearActiveSkill: () => set({ activeSkill: null }),
}));
