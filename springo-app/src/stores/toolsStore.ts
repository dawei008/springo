import { create } from 'zustand';
import { api } from '@/services/api';
import type { Skill } from '@/types';

export interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  enabled: boolean;
  path: string;
  hooks: Array<{ hook_point: string; priority: number }>;
}

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
  plugins: PluginInfo[];
  skills: Skill[];
  mcpServers: McpServer[];
  fetchAll: () => Promise<void>;
}

export const useToolsStore = create<ToolsState>((set) => ({
  plugins: [],
  skills: [],
  mcpServers: [],

  fetchAll: async () => {
    const [pluginsRes, skillsRes, serversRes] = await Promise.allSettled([
      api.plugins.list(),
      api.skills.list(),
      api.mcp.listServers(),
    ]);

    const plugins = pluginsRes.status === 'fulfilled'
      ? (pluginsRes.value.data?.plugins || []) as PluginInfo[]
      : [];
    const skills = skillsRes.status === 'fulfilled' ? skillsRes.value.data?.skills || [] : [];
    const mcpServers = serversRes.status === 'fulfilled'
      ? (serversRes.value.data?.servers || []) as McpServer[]
      : [];

    set({ plugins, skills, mcpServers });
  },
}));
