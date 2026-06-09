import { create } from 'zustand';
import type { TeamAgent, TeamTask } from '@/types';
import { genId } from '@/utils/genId';

// ==================== Role Configuration ====================

export const TEAM_ROLE_CONFIG: Record<string, { label: string; color: string }> = {
  orchestrator: { label: 'Orchestrator', color: '#7c3aed' },
  explorer: { label: 'Explorer', color: '#2563eb' },
  researcher: { label: 'Researcher', color: '#059669' },
  implementer: { label: 'Implementer', color: '#d97706' },
  reviewer: { label: 'Reviewer', color: '#dc2626' },
  worker: { label: 'Worker', color: '#0891b2' },
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
  /** Display name — agent_name (collaborative) or agent_id (classic) */
  name: string;
  /** Agent ID from backend (agent_id field in SSE events) */
  agentId?: string;
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

export interface StoreMessage {
  id: string;
  sender: string;
  recipient: string;
  content: string;
  summary?: string;
  isBroadcast: boolean;
  timestamp: number;
}

export type TeamStatus =
  | 'idle'
  | 'planning'
  | 'executing'
  | 'synthesizing'
  | 'complete'
  | 'error';

// ==================== Store Interface ====================

export interface AskUserData {
  agentName: string;
  question: string;
  options: Array<{ label: string; description?: string }>;
}

interface PerTeamState {
  agents: Record<string, StoreAgent>;
  tasks: Record<string, StoreTask>;
  messages: StoreMessage[];
  teamStatus: TeamStatus;
  userRequest: string;
  askUser: AskUserData | null;
}

interface TeamState {
  activeTeamId: string | null;
  agents: Record<string, StoreAgent>;
  tasks: Record<string, StoreTask>;
  messages: StoreMessage[];
  teamStatus: TeamStatus;
  userRequest: string;
  askUser: AskUserData | null;
  /** Per-team state preserved across session switches */
  sessionMap: Record<string, PerTeamState>;

  // Lifecycle
  setTeamSpawned: (teamId: string, agents: TeamAgent[], userRequest: string) => void;
  setTeamPlanning: (teamId: string) => void;
  setTeamSynthesizing: (teamId: string) => void;
  setTeamComplete: (teamId: string) => void;
  setTeamError: (teamId: string) => void;
  resetTeam: () => void;

  // Agent updates
  updateAgentStart: (teamId: string, agentId: string, role: string, taskTitle: string, agentName?: string) => void;
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

  // Messages
  appendMessage: (teamId: string, sender: string, recipient: string, content: string, summary?: string, isBroadcast?: boolean) => void;
  updateAgentIdle: (teamId: string, agentId: string) => void;

  // Ask user
  setAskUser: (teamId: string, agentName: string, question: string, options: Array<{ label: string; description?: string }>) => void;
  clearAskUser: () => void;

  // Historical team loading from API
  loadTeamFromAPI: (teamId: string) => Promise<boolean>;
}

// ==================== Helpers ====================

function guardTeam(state: TeamState, teamId: string): boolean {
  // Accept events for active team OR any team in sessionMap (background teams)
  return state.activeTeamId === teamId || teamId in state.sessionMap;
}

function getTeamState(state: TeamState, teamId: string): PerTeamState | null {
  if (state.activeTeamId === teamId) {
    return { agents: state.agents, tasks: state.tasks, messages: state.messages, teamStatus: state.teamStatus, userRequest: state.userRequest, askUser: state.askUser };
  }
  return state.sessionMap[teamId] || null;
}

function setTeamState(state: TeamState, teamId: string, partial: Partial<PerTeamState>): Partial<TeamState> {
  if (state.activeTeamId === teamId) {
    return partial;
  }
  // Update background team in sessionMap
  const existing = state.sessionMap[teamId];
  if (!existing) return {};
  return {
    sessionMap: {
      ...state.sessionMap,
      [teamId]: { ...existing, ...partial },
    },
  };
}

function updateTeamAgents(
  state: TeamState, teamId: string,
  updater: (agents: Record<string, StoreAgent>) => Record<string, StoreAgent>,
): Partial<TeamState> {
  if (state.activeTeamId === teamId) {
    return { agents: updater(state.agents) };
  }
  const ts = state.sessionMap[teamId];
  if (!ts) return {};
  return {
    sessionMap: { ...state.sessionMap, [teamId]: { ...ts, agents: updater(ts.agents) } },
  };
}

function updateTeamTasks(
  state: TeamState, teamId: string,
  updater: (tasks: Record<string, StoreTask>) => Record<string, StoreTask>,
): Partial<TeamState> {
  if (state.activeTeamId === teamId) {
    return { tasks: updater(state.tasks) };
  }
  const ts = state.sessionMap[teamId];
  if (!ts) return {};
  return {
    sessionMap: { ...state.sessionMap, [teamId]: { ...ts, tasks: updater(ts.tasks) } },
  };
}

function appendTeamMsg(
  state: TeamState, teamId: string, msg: StoreMessage,
): Partial<TeamState> {
  if (state.activeTeamId === teamId) {
    const msgs = [...state.messages, msg];
    return { messages: msgs.length > 200 ? msgs.slice(-200) : msgs };
  }
  const ts = state.sessionMap[teamId];
  if (!ts) return {};
  const msgs = [...ts.messages, msg];
  return {
    sessionMap: { ...state.sessionMap, [teamId]: { ...ts, messages: msgs.length > 200 ? msgs.slice(-200) : msgs } },
  };
}

/**
 * Find agent by key (direct lookup), or by agentId/name property match.
 * Classic mode: key = agent_id. Collaborative mode: key = name.
 * SSE events may use agent_id or agent_name, so we check both.
 */
function findAgentKey(agents: Record<string, StoreAgent>, id: string): string | null {
  // Direct key match
  if (agents[id]) return id;
  // Search by agentId property
  for (const [key, agent] of Object.entries(agents)) {
    if (agent.agentId === id || agent.name === id) return key;
  }
  return null;
}

function ensureAgent(agents: Record<string, StoreAgent>, agentId: string, role?: string): [string, StoreAgent] {
  const key = findAgentKey(agents, agentId);
  if (key) return [key, agents[key]];
  // Auto-create for dynamically spawned workers
  return [agentId, {
    name: agentId,
    agentId,
    role: role || 'custom',
    status: 'idle',
    purpose: '',
    findings: '',
    output: '',
  }];
}

// ==================== Store ====================

export const useTeamStore = create<TeamState>((set, get) => ({
  activeTeamId: null,
  agents: {},
  tasks: {},
  messages: [],
  teamStatus: 'idle',
  askUser: null,
  userRequest: '',
  sessionMap: {},

  // ─── Lifecycle ───

  setTeamSpawned: (teamId, agents, userRequest) => {
    const state = get();
    const agentMap: Record<string, StoreAgent> = {};
    for (const a of agents) {
      const key: string = a.agent_id || a.name || `agent-${Object.keys(agentMap).length}`;
      const displayName: string = a.name || a.agent_id || a.role;
      agentMap[key] = {
        name: displayName,
        agentId: a.agent_id,
        role: a.role,
        status: 'idle',
        purpose: a.purpose || '',
        findings: '',
        output: '',
      };
    }
    // Save current active team to sessionMap before switching
    const newSessionMap = { ...state.sessionMap };
    if (state.activeTeamId) {
      newSessionMap[state.activeTeamId] = {
        agents: state.agents, tasks: state.tasks, messages: state.messages,
        teamStatus: state.teamStatus, userRequest: state.userRequest, askUser: state.askUser,
      };
    }
    // Also save new team to sessionMap
    newSessionMap[teamId] = {
      agents: agentMap, tasks: {}, messages: [],
      teamStatus: 'executing', userRequest, askUser: null,
    };
    set({
      activeTeamId: teamId,
      agents: agentMap,
      tasks: {},
      messages: [],
      askUser: null,
      teamStatus: 'executing',
      userRequest,
      sessionMap: newSessionMap,
    });
  },

  setTeamPlanning: (teamId) => {
    if (!guardTeam(get(), teamId)) return;
    set(setTeamState(get(), teamId, { teamStatus: 'planning' }));
  },

  setTeamSynthesizing: (teamId) => {
    if (!guardTeam(get(), teamId)) return;
    set(setTeamState(get(), teamId, { teamStatus: 'synthesizing' }));
  },

  setTeamComplete: (teamId) => {
    if (!guardTeam(get(), teamId)) return;
    set(setTeamState(get(), teamId, { teamStatus: 'complete' }));
  },

  setTeamError: (teamId) => {
    if (!guardTeam(get(), teamId)) return;
    set(setTeamState(get(), teamId, { teamStatus: 'error' }));
  },

  resetTeam: () => {
    const state = get();
    const newSessionMap = { ...state.sessionMap };
    // Save current active team to sessionMap before clearing
    if (state.activeTeamId) {
      newSessionMap[state.activeTeamId] = {
        agents: state.agents, tasks: state.tasks, messages: state.messages,
        teamStatus: state.teamStatus, userRequest: state.userRequest, askUser: state.askUser,
      };
    }
    set({
      activeTeamId: null,
      agents: {},
      tasks: {},
      messages: [],
      askUser: null,
      teamStatus: 'idle',
      userRequest: '',
      sessionMap: newSessionMap,
    });
  },

  // ─── Agent Updates ───

  updateAgentStart: (teamId, agentId, role, taskTitle, agentName?) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId, role);
      const updated = { ...agent, role, status: 'working' as AgentStatus, purpose: taskTitle, output: '' };
      if (agentName) updated.name = agentName;
      return { ...agents, [key]: updated };
    }));
  },

  updateAgentProgress: (teamId, agentId, status, preview?) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId);
      const newAgent = { ...agent, status: 'working' as AgentStatus };
      if (preview) newAgent.output = preview;
      if (status) newAgent.purpose = status;
      return { ...agents, [key]: newAgent };
    }));
  },

  appendAgentDelta: (teamId, agentId, delta) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId);
      return { ...agents, [key]: { ...agent, output: agent.output + delta } };
    }));
  },

  updateAgentTool: (teamId, agentId, toolName, status) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId);
      return { ...agents, [key]: { ...agent, status: 'tool_calling', currentTool: toolName, toolStatus: status } };
    }));
  },

  updateAgentComplete: (teamId, agentId, role, findings) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId, role);
      return { ...agents, [key]: { ...agent, role, status: 'complete', findings } };
    }));
  },

  updateAgentError: (teamId, agentId, error) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const [key, agent] = ensureAgent(agents, agentId);
      return { ...agents, [key]: { ...agent, status: 'error', error } };
    }));
  },

  // ─── Task Board ───

  updateTaskBoard: (teamId, tasks) => {
    if (!guardTeam(get(), teamId)) return;
    const taskMap: Record<string, StoreTask> = {};
    for (const t of tasks) {
      taskMap[t.id] = { id: t.id, title: t.title, owner: t.owner, status: t.status, blockedBy: t.blockedBy };
    }
    set(setTeamState(get(), teamId, { tasks: taskMap }));
  },

  updateTaskCreated: (teamId, taskId, title, owner?) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamTasks(state, teamId, (tasks) => ({
      ...tasks, [taskId]: { id: taskId, title, owner, status: 'pending' },
    })));
  },

  updateTaskUpdated: (teamId, taskId, status, owner?, title?) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamTasks(state, teamId, (tasks) => {
      const existing = tasks[taskId] || { id: taskId, title: title || taskId, status: 'pending' };
      return {
        ...tasks,
        [taskId]: { ...existing, status, ...(owner !== undefined && { owner }), ...(title !== undefined && { title }) },
      };
    }));
  },

  updateTaskUnblocked: (teamId, taskId, owner?, title?) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamTasks(state, teamId, (tasks) => {
      const existing = tasks[taskId] || { id: taskId, title: title || taskId, status: 'pending' };
      return {
        ...tasks,
        [taskId]: { ...existing, status: 'unblocked', blockedBy: [], ...(owner !== undefined && { owner }), ...(title !== undefined && { title }) },
      };
    }));
  },

  // ─── Messages ───

  appendMessage: (teamId, sender, recipient, content, summary?, isBroadcast = false) => {
    if (!guardTeam(get(), teamId)) return;
    // Skip user ↔ team-lead messages (they belong in main chat)
    if (sender === 'user' || recipient === 'user') return;
    const msg: StoreMessage = {
      id: genId('msg'),
      sender, recipient, content, summary, isBroadcast, timestamp: Date.now(),
    };
    set((state) => appendTeamMsg(state, teamId, msg));
  },

  updateAgentIdle: (teamId, agentId) => {
    if (!guardTeam(get(), teamId)) return;
    set((state) => updateTeamAgents(state, teamId, (agents) => {
      const key = findAgentKey(agents, agentId);
      if (!key) return agents;
      const agent = agents[key];
      if (agent.status === 'complete' || agent.status === 'error') return agents;
      return { ...agents, [key]: { ...agent, status: 'idle' } };
    }));
  },

  // ─── Ask User ───

  setAskUser: (teamId, agentName, question, options) => {
    if (!guardTeam(get(), teamId)) return;
    set(setTeamState(get(), teamId, { askUser: { agentName, question, options } }));
  },

  clearAskUser: () => {
    set({ askUser: null });
  },

  // ─── Historical Team Loading ───

  loadTeamFromAPI: async (teamId: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8081/v1/teams/${teamId}`);
      if (!res.ok) return false;
      const data = await res.json();

      // Map API agents to StoreAgent
      const teamIsTerminal = data.status === 'complete' || data.status === 'error';
      const agentMap: Record<string, StoreAgent> = {};
      for (const a of data.agents || []) {
        const statusMap: Record<string, AgentStatus> = {
          complete: 'complete', error: 'error',
          working: 'working', tool_calling: 'tool_calling',
          executing: 'working', thinking: 'working', idle: 'idle',
        };
        let agentStatus = statusMap[a.status] || 'idle';
        // If team is terminal but agent shows active, fix the status
        if (teamIsTerminal && (agentStatus === 'working' || agentStatus === 'tool_calling' || agentStatus === 'idle')) {
          agentStatus = data.status === 'complete' ? 'complete' : 'error';
        }
        const key: string = a.agent_id || a.name || `agent-${Object.keys(agentMap).length}`;
        const displayName: string = a.name || a.agent_id || a.role || 'agent';
        agentMap[key] = {
          name: displayName,
          agentId: a.agent_id,
          role: a.role || 'custom',
          status: agentStatus,
          purpose: a.purpose || '',
          findings: a.findings || '',
          output: '',
        };
      }

      // Map API tasks to StoreTask
      const taskMap: Record<string, StoreTask> = {};
      for (const t of data.task_board || []) {
        taskMap[t.task_id] = {
          id: t.task_id,
          title: t.title,
          owner: t.assigned_to,
          status: t.status,
        };
      }

      // Map team status
      const teamStatusMap: Record<string, TeamStatus> = {
        complete: 'complete', error: 'error',
        planning: 'planning', executing: 'executing',
        synthesizing: 'synthesizing', created: 'idle',
      };

      // Fetch inter-agent messages
      let messagesList: StoreMessage[] = [];
      try {
        const msgRes = await fetch(`http://127.0.0.1:8081/v1/teams/${teamId}/messages`);
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          messagesList = (msgData.messages || [])
            .filter((m: Record<string, unknown>) => m.sender !== 'user' && m.recipient !== 'user')
            .map((m: Record<string, unknown>) => ({
              id: (m.message_id as string) || genId('msg'),
              sender: (m.sender as string) || '',
              recipient: (m.recipient as string) || '',
              content: (m.content as string) || '',
              summary: (m.summary as string) || '',
              isBroadcast: m.type === 'broadcast',
              timestamp: (m.timestamp as number) || 0,
            }));
        }
      } catch { /* messages are optional */ }

      const state = get();
      const newSessionMap = { ...state.sessionMap };
      // Save current active team before switching
      if (state.activeTeamId && state.activeTeamId !== teamId) {
        newSessionMap[state.activeTeamId] = {
          agents: state.agents, tasks: state.tasks, messages: state.messages,
          teamStatus: state.teamStatus, userRequest: state.userRequest, askUser: state.askUser,
        };
      }
      const loadedStatus = teamStatusMap[data.status] || 'idle';
      const loadedRequest = data.user_request || '';
      newSessionMap[teamId] = {
        agents: agentMap, tasks: taskMap, messages: messagesList,
        teamStatus: loadedStatus, userRequest: loadedRequest, askUser: null,
      };
      set({
        activeTeamId: teamId,
        agents: agentMap,
        tasks: taskMap,
        messages: messagesList,
        teamStatus: loadedStatus,
        userRequest: loadedRequest,
        sessionMap: newSessionMap,
      });

      return true;
    } catch (e) {
      console.warn('Failed to load team from API:', e);
      return false;
    }
  },
}));
