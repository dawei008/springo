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

export type RightPanelTab = 'tasks' | 'team' | 'schedules' | 'meeting';

export interface QueueItem {
  id: string;
  content: string;
  attachments: Array<{ type: string; data?: string; name?: string; path?: string }>;
  addedAt: number;
}

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
  /** Maps sessionId → todos for restoring when switching sessions */
  sessionTodosMap: Record<string, TodoItem[]>;
  themeMode: 'light' | 'dark' | 'system';
  fileBrowserOpen: boolean;
  fileBrowserPath: string;
  /** Maps sessionId → teamId for sessions that had team executions */
  sessionTeamMap: Record<string, string>;

  // Queue state (per-session)
  queueEnabled: boolean;
  queueItems: QueueItem[];
  sessionQueueMap: Record<string, QueueItem[]>;

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
  saveSessionTodos: (sessionId: string, todos: TodoItem[]) => void;
  getSessionTodos: (sessionId: string) => TodoItem[];
  setThemeMode: (mode: 'light' | 'dark' | 'system') => void;
  openFileBrowser: (path: string) => void;
  closeFileBrowser: () => void;
  setSessionTeam: (sessionId: string, teamId: string) => void;
  getSessionTeam: (sessionId: string) => string | null;

  // Queue actions (per-session)
  toggleQueue: () => void;
  setQueueEnabled: (enabled: boolean) => void;
  enqueueItem: (sessionId: string, content: string, attachments?: QueueItem['attachments']) => void;
  dequeueItem: (sessionId: string) => QueueItem | undefined;
  removeQueueItem: (sessionId: string, id: string) => void;
  clearQueue: (sessionId: string) => void;
  switchSessionQueue: (sessionId: string | null) => void;
}

let toastTimer: ReturnType<typeof setTimeout> | null = null;

export const useUIStore = create<UIState>((set, get) => ({
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
  sessionTodosMap: {},
  themeMode: (localStorage.getItem('springo-theme') as 'light' | 'dark' | 'system') || 'system',
  fileBrowserOpen: false,
  fileBrowserPath: '',
  sessionTeamMap: (() => {
    try {
      return JSON.parse(localStorage.getItem('springo-session-teams') || '{}');
    } catch {
      return {};
    }
  })(),
  queueEnabled: false,
  queueItems: [],
  sessionQueueMap: {},

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
  saveSessionTodos: (sessionId, todos) =>
    set((state) => ({
      sessionTodosMap: { ...state.sessionTodosMap, [sessionId]: todos },
    })),
  getSessionTodos: (sessionId) => get().sessionTodosMap[sessionId] || [],
  setThemeMode: (mode) => {
    localStorage.setItem('springo-theme', mode);
    set({ themeMode: mode });
  },
  openFileBrowser: (path) => set({ fileBrowserOpen: true, fileBrowserPath: path }),
  closeFileBrowser: () => set({ fileBrowserOpen: false, fileBrowserPath: '' }),
  setSessionTeam: (sessionId, teamId) => {
    set((state) => {
      const updated = { ...state.sessionTeamMap, [sessionId]: teamId };
      try { localStorage.setItem('springo-session-teams', JSON.stringify(updated)); } catch { /* noop */ }
      return { sessionTeamMap: updated };
    });
  },
  getSessionTeam: (sessionId) => {
    return get().sessionTeamMap[sessionId] || null;
  },

  // Queue actions (per-session)
  toggleQueue: () => set((state) => ({ queueEnabled: !state.queueEnabled })),
  setQueueEnabled: (enabled) => set({ queueEnabled: enabled }),
  enqueueItem: (sessionId, content, attachments = []) => {
    const item: QueueItem = { id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, content, attachments, addedAt: Date.now() };
    set((state) => {
      const map = { ...state.sessionQueueMap };
      map[sessionId] = [...(map[sessionId] || []), item];
      return { sessionQueueMap: map, queueItems: map[sessionId] };
    });
  },
  dequeueItem: (sessionId) => {
    const items = get().sessionQueueMap[sessionId] || [];
    if (items.length === 0) return undefined;
    const [first, ...rest] = items;
    set((state) => {
      const map = { ...state.sessionQueueMap };
      map[sessionId] = rest;
      return { sessionQueueMap: map, queueItems: rest };
    });
    return first;
  },
  removeQueueItem: (sessionId, id) =>
    set((state) => {
      const map = { ...state.sessionQueueMap };
      map[sessionId] = (map[sessionId] || []).filter((item) => item.id !== id);
      return { sessionQueueMap: map, queueItems: map[sessionId] };
    }),
  clearQueue: (sessionId) =>
    set((state) => {
      const map = { ...state.sessionQueueMap };
      map[sessionId] = [];
      return { sessionQueueMap: map, queueItems: [] };
    }),
  switchSessionQueue: (sessionId) => {
    set({ queueItems: sessionId ? (get().sessionQueueMap[sessionId] || []) : [] });
  },
}));
