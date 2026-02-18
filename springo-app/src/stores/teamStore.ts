import { create } from 'zustand';
import type { TeamAgent, TeamTask } from '@/types';

// ==================== Role Configuration ====================

export const TEAM_ROLE_CONFIG: Record<string, { label: string; color: string }> = {
  orchestrator: { label: 'Orchestrator', color: '#7c3aed' },
  explorer: { label: 'Explorer', color: '#2563eb' },
  researcher: { label: 'Researcher', color: '#059669' },
  implementer: { label: 'Implementer', color: '#d97706' },
  reviewer: { label: 'Reviewer', color: '#dc2626' },
  custom: { label: 'Agent', color: '#6366f1' },
};

export function getRoleConfig(role: string): { label: string; color: string } {
  return TEAM_ROLE_CONFIG[role] || TEAM_ROLE_CONFIG.custom;
}

// ==================== Store Agent / Task Types ====================

export type AgentStatus =
  | 'idle'
  | 'working'
  | 'tool_calling'
  | 'complete'
  | 'error';

export interface StoreAgent {
  name: string;
  role: string;
  status: AgentStatus;
  purpose: string;
  findings: string;
  output: string;
  currentTool?: string;
  toolStatus?: string;
  error?: string;
}

export interface StoreTask {
  id: string;
  title: string;
  owner?: string;
  status: string;
  blockedBy?: string[];
}

export type TeamStatus =
  | 'idle'
  | 'planning'
  | 'executing'
  | 'synthesizing'
  | 'complete'
  | 'error';

// ==================== Store Interface ====================

interface TeamState {
  activeTeamId: string | null;
  agents: Record<string, StoreAgent>;
  tasks: Record<string, StoreTask>;
  teamStatus: TeamStatus;
  userRequest: string;

  // Lifecycle
  setTeamSpawned: (teamId: string, agents: TeamAgent[], userRequest: string) => void;
  setTeamPlanning: (teamId: string) => void;
  setTeamSynthesizing: (teamId: string) => void;
  setTeamComplete: (teamId: string, result?: string) => void;
  setTeamError: (teamId: string, error: string) => void;
  resetTeam: () => void;

  // Agent updates
  updateAgentStart: (teamId: string, agentId: string, role: string, taskTitle: string) => void;
  updateAgentProgress: (teamId: string, agentId: string, status: string, preview?: string) => void;
  appendAgentDelta: (teamId: string, agentId: string, delta: string) => void;
  updateAgentTool: (teamId: string, agentId: string, toolName: string, status: string) => void;
  updateAgentComplete: (teamId: string, agentId: string, role: string, findings: string) => void;
  updateAgentError: (teamId: string, agentId: string, error: string) => void;

  // Task board
  updateTaskBoard: (teamId: string, tasks: TeamTask[]) => void;
  updateTaskCreated: (teamId: string, taskId: string, title: string, owner?: string) => void;
  updateTaskUpdated: (teamId: string, taskId: string, status: string, owner?: string, title?: string) => void;
  updateTaskUnblocked: (teamId: string, taskId: string, owner?: string, title?: string) => void;
}

// ==================== Helpers ====================

function guardTeam(activeTeamId: string | null, teamId: string): boolean {
  return activeTeamId === teamId;
}

function ensureAgent(agents: Record<string, StoreAgent>, agentId: string, role?: string): StoreAgent {
  if (agents[agentId]) return agents[agentId];
  return {
    name: agentId,
    role: role || 'custom',
    status: 'idle',
    purpose: '',
    findings: '',
    output: '',
  };
}

// ==================== Store ====================

export const useTeamStore = create<TeamState>((set, get) => ({
  activeTeamId: null,
  agents: {},
  tasks: {},
  teamStatus: 'idle',
  userRequest: '',

  // ─── Lifecycle ───

  setTeamSpawned: (teamId, agents, userRequest) => {
    const agentMap: Record<string, StoreAgent> = {};
    for (const a of agents) {
      agentMap[a.name] = {
        name: a.name,
        role: a.role,
        status: 'idle',
        purpose: '',
        findings: '',
        output: '',
      };
    }
    set({
      activeTeamId: teamId,
      agents: agentMap,
      tasks: {},
      teamStatus: 'executing',
      userRequest,
    });
  },

  setTeamPlanning: (teamId) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set({ teamStatus: 'planning' });
  },

  setTeamSynthesizing: (teamId) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set({ teamStatus: 'synthesizing' });
  },

  setTeamComplete: (teamId, _result?) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set({ teamStatus: 'complete' });
  },

  setTeamError: (teamId, _error) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set({ teamStatus: 'error' });
  },

  resetTeam: () => {
    set({
      activeTeamId: null,
      agents: {},
      tasks: {},
      teamStatus: 'idle',
      userRequest: '',
    });
  },

  // ─── Agent Updates ───

  updateAgentStart: (teamId, agentId, role, taskTitle) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId, role);
      return {
        agents: {
          ...state.agents,
          [agentId]: { ...agent, role, status: 'working', purpose: taskTitle, output: '' },
        },
      };
    });
  },

  updateAgentProgress: (teamId, agentId, status, preview?) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId);
      const newAgent = { ...agent, status: 'working' as AgentStatus };
      if (preview) newAgent.output = preview;
      if (status) newAgent.purpose = status;
      return { agents: { ...state.agents, [agentId]: newAgent } };
    });
  },

  appendAgentDelta: (teamId, agentId, delta) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId);
      return {
        agents: {
          ...state.agents,
          [agentId]: { ...agent, output: agent.output + delta },
        },
      };
    });
  },

  updateAgentTool: (teamId, agentId, toolName, status) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId);
      return {
        agents: {
          ...state.agents,
          [agentId]: {
            ...agent,
            status: 'tool_calling',
            currentTool: toolName,
            toolStatus: status,
          },
        },
      };
    });
  },

  updateAgentComplete: (teamId, agentId, role, findings) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId, role);
      return {
        agents: {
          ...state.agents,
          [agentId]: { ...agent, role, status: 'complete', findings },
        },
      };
    });
  },

  updateAgentError: (teamId, agentId, error) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const agent = ensureAgent(state.agents, agentId);
      return {
        agents: {
          ...state.agents,
          [agentId]: { ...agent, status: 'error', error },
        },
      };
    });
  },

  // ─── Task Board ───

  updateTaskBoard: (teamId, tasks) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    const taskMap: Record<string, StoreTask> = {};
    for (const t of tasks) {
      taskMap[t.id] = {
        id: t.id,
        title: t.title,
        owner: t.owner,
        status: t.status,
        blockedBy: t.blockedBy,
      };
    }
    set({ tasks: taskMap });
  },

  updateTaskCreated: (teamId, taskId, title, owner?) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: { id: taskId, title, owner, status: 'pending' },
      },
    }));
  },

  updateTaskUpdated: (teamId, taskId, status, owner?, title?) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const existing = state.tasks[taskId] || { id: taskId, title: title || taskId, status: 'pending' };
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...existing,
            status,
            ...(owner !== undefined && { owner }),
            ...(title !== undefined && { title }),
          },
        },
      };
    });
  },

  updateTaskUnblocked: (teamId, taskId, owner?, title?) => {
    if (!guardTeam(get().activeTeamId, teamId)) return;
    set((state) => {
      const existing = state.tasks[taskId] || { id: taskId, title: title || taskId, status: 'pending' };
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...existing,
            status: 'unblocked',
            blockedBy: [],
            ...(owner !== undefined && { owner }),
            ...(title !== undefined && { title }),
          },
        },
      };
    });
  },
}));
