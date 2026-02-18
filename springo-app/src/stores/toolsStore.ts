import { create } from 'zustand';
import { api } from '@/services/api';
import type { Skill } from '@/types';

export interface McpServer {
  name: string;
  running: boolean;
  enabled: boolean;
  status: string;
  tools: number;
  cached_tools: number;
  description?: string;
  command?: string;
}

interface ToolsState {
  skills: Skill[];
  mcpServers: McpServer[];
  fetchAll: () => Promise<void>;
}

export const useToolsStore = create<ToolsState>((set) => ({
  skills: [],
  mcpServers: [],

  fetchAll: async () => {
    const [skillsRes, serversRes] = await Promise.allSettled([
      api.skills.list(),
      api.mcp.listServers(),
    ]);

    const skills = skillsRes.status === 'fulfilled' ? skillsRes.value.data?.skills || [] : [];
    const mcpServers = serversRes.status === 'fulfilled'
      ? (serversRes.value.data?.servers || []) as McpServer[]
      : [];

    set({ skills, mcpServers });
  },
}));
