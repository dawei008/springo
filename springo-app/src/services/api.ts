/**
 * Springo HTTP API Client
 *
 * Singleton API service wrapping all backend endpoints.
 * SSE streaming for /v1/messages-auto is handled separately in sse.ts.
 */

import type {
  SessionListItem,
  SessionDetail,
  SessionMetadata,
  Message,
  ToolInfo,
  ToolExecuteResponse,
  Skill,
  ContextItem,
  ContextStats,
  WorkingDirConfig,
  AWSConfig,
  S3Config,
  MemoryConfig,
  FeishuConfig,
  VendorKeysConfig,
  ModelInfo,
  HealthResponse,
  TeamSpawnRequest,
  TeamInfo,
  TeamMessageRequest,
  ImageGenerateRequest,
  ImageUploadResponse,
  TerminalExecuteRequest,
  TerminalExecuteResponse,
  ContentBlock,
  PlanStructure,
  PlanSection,
} from '../types';
import { CONFIG } from '../types';

// ---------------------------------------------------------------------------
// Base URL resolution
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = 'http://127.0.0.1:8081';

/** Cached base URL resolved from Electron IPC (set via initBaseUrl). */
let _resolvedBaseUrl: string | null = null;

/**
 * Initialise the base URL from Electron IPC.
 * Call once at app startup (e.g. in App.tsx useEffect).
 * Safe to call multiple times or in non-Electron environments.
 */
export async function initBaseUrl(): Promise<string> {
  if (_resolvedBaseUrl) return _resolvedBaseUrl;
  try {
    if (typeof window !== 'undefined' && window.electronAPI?.getServerUrl) {
      const url = await window.electronAPI.getServerUrl();
      if (url) {
        _resolvedBaseUrl = url;
        return url;
      }
    }
  } catch {
    // Fall through to default
  }
  _resolvedBaseUrl = DEFAULT_BASE_URL;
  return _resolvedBaseUrl;
}

function getBaseUrl(): string {
  return _resolvedBaseUrl ?? DEFAULT_BASE_URL;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

interface ApiResult<T = unknown> {
  ok: boolean;
  data: T | null;
  error: string | null;
  status: number;
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxRetries = CONFIG.RETRY.MAX_ATTEMPTS,
  timeout = CONFIG.TIMEOUTS.FETCH_RETRY,
  externalSignal?: AbortSignal,
): Promise<Response> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const onExternalAbort = () => controller.abort();
    if (externalSignal) {
      if (externalSignal.aborted) {
        clearTimeout(timeoutId);
        throw new DOMException('Request aborted by user', 'AbortError');
      }
      externalSignal.addEventListener('abort', onExternalAbort);
    }

    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timeoutId);
      externalSignal?.removeEventListener('abort', onExternalAbort);
      return response;
    } catch (e) {
      clearTimeout(timeoutId);
      externalSignal?.removeEventListener('abort', onExternalAbort);
      lastError = e as Error;

      if (externalSignal?.aborted) {
        throw new DOMException('Request aborted by user', 'AbortError');
      }

      const isNetworkError = (e as Error).message === 'Failed to fetch' || (e as Error).name === 'TypeError';
      const isTimeout = (e as Error).name === 'AbortError';
      if (attempt < maxRetries && (isNetworkError || isTimeout)) {
        const wait = Math.min(1000 * 2 ** attempt, CONFIG.RETRY.BACKOFF_MAX);
        await new Promise((r) => setTimeout(r, wait));
        continue;
      }
      throw e;
    }
  }
  throw lastError!;
}

async function apiCall<T = unknown>(
  endpoint: string,
  options: RequestInit = {},
  config: { parseJson?: boolean; retry?: boolean; timeout?: number; maxRetries?: number } = {},
): Promise<ApiResult<T>> {
  const { parseJson = true, retry = true, timeout = 30_000, maxRetries = 2 } = config;
  const baseUrl = getBaseUrl();
  const url = endpoint.startsWith('http') ? endpoint : `${baseUrl}/v1${endpoint}`;
  const fetchOptions: RequestInit = {
    headers: { 'Content-Type': 'application/json', ...(options.headers as Record<string, string>) },
    ...options,
  };

  try {
    const response = retry
      ? await fetchWithRetry(url, fetchOptions, maxRetries, timeout)
      : await fetch(url, fetchOptions);

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorData.detail || errorData.message || errorMessage;
      } catch {
        errorMessage = response.statusText || errorMessage;
      }
      return { ok: false, data: null, error: errorMessage, status: response.status };
    }

    if (parseJson) {
      const data = (await response.json()) as T;
      return { ok: true, data, error: null, status: response.status };
    }
    return { ok: true, data: response as unknown as T, error: null, status: response.status };
  } catch (e) {
    const isAbort = (e as Error).name === 'AbortError';
    const errorMessage = isAbort ? 'Request timed out' : ((e as Error).message || 'Network error');
    return { ok: false, data: null, error: errorMessage, status: 0 };
  }
}

// Convenience wrappers
function get<T = unknown>(endpoint: string, config?: Parameters<typeof apiCall>[2]) {
  return apiCall<T>(endpoint, { method: 'GET' }, config);
}

function post<T = unknown>(endpoint: string, body?: unknown, config?: Parameters<typeof apiCall>[2]) {
  return apiCall<T>(endpoint, { method: 'POST', body: body != null ? JSON.stringify(body) : undefined }, config);
}

function patch<T = unknown>(endpoint: string, body?: unknown, config?: Parameters<typeof apiCall>[2]) {
  return apiCall<T>(endpoint, { method: 'PATCH', body: body != null ? JSON.stringify(body) : undefined }, config);
}

function del<T = unknown>(endpoint: string, config?: Parameters<typeof apiCall>[2]) {
  return apiCall<T>(endpoint, { method: 'DELETE' }, config);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const api = {
  /** Return the resolved base URL (useful for SSE connections). */
  getBaseUrl,

  // ======================== Health ========================

  health: {
    check: () => get<HealthResponse>('/health'.replace('/v1', ''), { retry: false }),
    detailed: () => get<{ status: string; services: Record<string, unknown> }>('/health/detailed'.replace('/v1', '')),
  },

  // Note: health endpoints are at /health, not /v1/health. Override URL manually.

  // ======================== Sessions ========================

  sessions: {
    list: (workingDir?: string) => {
      const qs = workingDir ? `?working_dir=${encodeURIComponent(workingDir)}` : '';
      return get<{ sessions: SessionListItem[] }>(`/sessions${qs}`);
    },
    get: (sessionId: string) => get<SessionDetail>(`/sessions/${sessionId}`),
    save: (sessionId: string, messages: Message[], metadata?: SessionMetadata) =>
      post<{ ok: boolean }>(`/sessions/${sessionId}`, { messages, metadata }),
    updateMetadata: (sessionId: string, metadata: SessionMetadata) =>
      patch<{ ok: boolean }>(`/sessions/${sessionId}`, { metadata }),
    delete: (sessionId: string) => del<{ ok: boolean }>(`/sessions/${sessionId}`),
    byNumber: (num: number) => get<SessionDetail>(`/sessions/by-number/${num}`),
    hash: (sessionId: string) => post<{ hash: string }>('/sessions/hash', { session_id: sessionId }),
  },

  // ======================== Messages ========================
  // NOTE: /v1/messages-auto (SSE streaming) is handled in sse.ts

  messages: {
    /** Non-streaming message call (rarely used; prefer messages-auto). */
    send: (body: {
      model: string;
      messages: Array<{ role: string; content: string | ContentBlock[] }>;
      max_tokens?: number;
      temperature?: number;
      system?: string;
    }) => post<Record<string, unknown>>('/messages', body, { timeout: CONFIG.TIMEOUTS.STREAMING }),

    /**
     * Start an SSE streaming request to /v1/messages-auto.
     * Returns the raw Response so callers can read the body stream.
     */
    sendAutoRaw: async (
      body: {
        model: string;
        messages: Array<{ role: string; content: string | ContentBlock[] }>;
        max_tokens?: number;
        temperature?: number;
        system?: string;
        session_id?: string;
        max_tool_iterations?: number;
        compact_model?: string;
        [key: string]: unknown;
      },
      signal?: AbortSignal,
    ): Promise<Response> => {
      const baseUrl = getBaseUrl();
      const response = await fetchWithRetry(
        `${baseUrl}/v1/messages-auto`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, stream: true }),
          signal,
        },
        1, // 1 retry
        CONFIG.TIMEOUTS.STREAMING,
        signal,
      );
      if (!response.ok) {
        let msg = `HTTP ${response.status}`;
        try {
          const err = await response.json();
          msg = err.error?.message || err.detail || msg;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      return response;
    },
  },

  // ======================== Tools ========================

  tools: {
    list: () => get<{ tools: ToolInfo[] }>('/tools'),
    get: (toolName: string) => get<ToolInfo>(`/tools/${toolName}`),
    execute: (name: string, input: Record<string, unknown>) =>
      post<ToolExecuteResponse>('/tools/execute', { name, input }, { timeout: CONFIG.TIMEOUTS.TOOL_EXECUTION }),
    batch: (tools: Array<{ name: string; input: Record<string, unknown> }>) =>
      post<{ results: ToolExecuteResponse[] }>('/tools/batch', { tools }, { timeout: CONFIG.TIMEOUTS.TOOL_EXECUTION }),
  },

  // ======================== Plugins ========================

  plugins: {
    list: () => get<{ plugins: Array<{ name: string; version: string; description: string; author: string; enabled: boolean; path: string; hooks: Array<{ hook_point: string; priority: number }> }>; count: number }>('/plugins/list'),
    reload: () => post<{ status: string; count: number }>('/plugins/reload'),
    getPath: () => get<{ path: string }>('/plugins/path'),
  },

  // ======================== Skills ========================

  skills: {
    list: () => get<{ skills: Skill[] }>('/skills'),
    get: (name: string) => get<Skill>(`/skills/${name}`),
    getInstructions: (name: string) => get<{ instructions: string }>(`/skills/${name}/instructions`),
    prompt: (name: string, body: Record<string, unknown>) =>
      post<{ prompt: string }>(`/skills/${name}/prompt`, body),
    activate: (name: string) => post<{ ok: boolean }>(`/skills/${name}/activate`),
    reload: () => post<{ ok: boolean }>('/skills/reload'),
    getPath: () => get<{ path: string }>('/skills/path'),
  },

  // ======================== Context ========================

  context: {
    list: () => get<{ items: ContextItem[] }>('/context'),
    add: (item: { type: string; content: string; source?: string }) =>
      post<{ ok: boolean }>('/context/add', item),
    clear: () => del<{ ok: boolean }>('/context'),
    deleteItem: (index: number) => del<{ ok: boolean }>(`/context/${index}`),
    stats: (body: { messages: Array<{ role: string; content: unknown }> }) =>
      post<ContextStats>('/context/stats', body),
    breakdown: (body: { messages: Array<{ role: string; content: unknown }> }) =>
      post<Record<string, unknown>>('/context/breakdown', body),
    summarize: (body: { messages: Array<{ role: string; content: unknown }>; model?: string }) =>
      post<{ messages: Message[] }>('/context/summarize', body, { timeout: CONFIG.TIMEOUTS.STREAMING }),
    autoCheck: (body: { messages: Array<{ role: string; content: unknown }> }) =>
      post<{ needs_compaction: boolean }>('/context/auto-check', body),
  },

  // ======================== Config ========================

  config: {
    workingDir: {
      get: () => get<WorkingDirConfig>('/config/working-dir'),
      set: (dir: string) => post<WorkingDirConfig>('/config/working-dir', { working_dir: dir }),
    },
    checkPaths: (paths: string[]) => post<Record<string, boolean>>('/config/check-paths', { paths }),
    warmup: () => post<{ ok: boolean }>('/warmup'.replace('/v1', '')),
    aws: {
      get: () => get<AWSConfig>('/config/aws'),
      set: (config: AWSConfig) => post<{ ok: boolean }>('/config/aws', config),
      test: () => get<{ ok: boolean }>('/config/aws/test'),
      profiles: () => get<{ profiles: string[] }>('/config/aws/profiles'),
    },
    s3: {
      get: () => get<S3Config>('/config/s3'),
      set: (config: S3Config) => post<{ ok: boolean }>('/config/s3', config),
      create: (config: S3Config) => post<{ ok: boolean }>('/config/s3/create', config),
    },
    memory: {
      get: () => get<MemoryConfig>('/config/memory'),
      set: (config: MemoryConfig) => post<{ ok: boolean }>('/config/memory', config),
      create: (config: MemoryConfig) => post<{ ok: boolean }>('/config/memory/create', config),
      test: () => get<{ ok: boolean }>('/config/memory/test'),
      refreshStrategies: () => post<{ ok: boolean }>('/config/memory/strategies/refresh'),
    },
    feishu: {
      get: () => get<FeishuConfig>('/config/feishu'),
      set: (config: FeishuConfig) => post<{ ok: boolean }>('/config/feishu', config),
      test: () => post<{ ok: boolean }>('/config/feishu/test'),
    },
    vendorKeys: {
      get: () => get<VendorKeysConfig>('/config/vendor-keys'),
      set: (keys: VendorKeysConfig) => post<{ ok: boolean }>('/config/vendor-keys', keys),
      test: (vendor: string) => post<{ ok: boolean }>('/config/vendor-keys/test', { vendor }),
    },
    setupMemoryS3: (body: Record<string, unknown>) => post<{ ok: boolean }>('/config/setup-memory-s3', body),
  },

  // ======================== S3 Sync ========================

  s3: {
    status: () => get<{ enabled: boolean; bucket?: string }>('/s3/status'.replace('/v1', '')),
    sync: (sessionId: string) => post<{ ok: boolean }>(`/s3/sync/${sessionId}`.replace('/v1', '')),
  },

  // ======================== Models ========================

  models: {
    list: () => get<{ models: ModelInfo[] }>('/models'),
  },

  // ======================== Images ========================

  images: {
    getFile: (params: { session_id?: string; filename?: string; path?: string }) => {
      const qs = new URLSearchParams(params as Record<string, string>).toString();
      return get<Blob>(`/images/file?${qs}`, { parseJson: false });
    },
    upload: (formData: FormData) =>
      apiCall<ImageUploadResponse>('/images/upload', {
        method: 'POST',
        body: formData,
        headers: {}, // let browser set content-type with boundary
      }),
    generate: (body: ImageGenerateRequest) =>
      post<{ url: string }>('/images/generate', body, { timeout: CONFIG.TIMEOUTS.TOOL_EXECUTION }),
    search: (query: string) => post<{ images: Array<{ url: string; title: string }> }>('/images/search', { query }),
  },

  // ======================== Teams ========================

  teams: {
    spawn: (body: TeamSpawnRequest) =>
      post<{ team_id: string }>('/teams/spawn', body, { timeout: CONFIG.TIMEOUTS.STREAMING }),
    list: () => get<{ teams: TeamInfo[] }>('/teams'),
    get: (teamId: string) => get<TeamInfo>(`/teams/${teamId}`),
    byNumber: (num: number) => get<TeamInfo>(`/teams/by-number/${num}`),
    getTaskBoard: (teamId: string) => get<{ tasks: unknown[] }>(`/teams/${teamId}/task-board`),
    message: (teamId: string, body: TeamMessageRequest) =>
      post<{ ok: boolean }>(`/teams/${teamId}/message`, body),
    resume: (teamId: string) => post<{ ok: boolean }>(`/teams/${teamId}/resume`),
    shutdown: (teamId: string) => post<{ ok: boolean }>(`/teams/${teamId}/shutdown`),
    getMessages: (teamId: string) => get<{ messages: unknown[] }>(`/teams/${teamId}/messages`),
    /** SSE event stream for a team (returns raw Response). */
    eventsRaw: async (teamId: string, signal?: AbortSignal): Promise<Response> => {
      const baseUrl = getBaseUrl();
      const response = await fetch(`${baseUrl}/v1/teams/${teamId}/events`, { signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response;
    },
  },

  // ======================== Plans ========================

  plans: {
    generate: async (body: { task_description: string; session_id?: string; model?: string; max_tokens?: number }, signal?: AbortSignal): Promise<Response> => {
      const baseUrl = getBaseUrl();
      return fetchWithRetry(
        `${baseUrl}/v1/plans/generate`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal,
        },
        1,
        CONFIG.TIMEOUTS.STREAMING,
        signal,
      );
    },
    get: (planId: string) => get<PlanStructure>(`/plans/${planId}`),
    list: () => get<{ plans: PlanStructure[] }>('/plans'),
    feedback: (planId: string, body: { section_id: string; action: string; feedback?: string }) =>
      post<{ ok: boolean; section?: PlanSection; plan_status?: string }>(`/plans/${planId}/feedback`, body),
    feedbackStream: async (planId: string, body: { section_id: string; action: string; feedback?: string }, signal?: AbortSignal): Promise<Response> => {
      const baseUrl = getBaseUrl();
      return fetchWithRetry(
        `${baseUrl}/v1/plans/${planId}/feedback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal,
        },
        1,
        CONFIG.TIMEOUTS.STREAMING,
        signal,
      );
    },
    approveAll: (planId: string) => post<{ ok: boolean; plan: PlanStructure }>(`/plans/${planId}/approve-all`),
    execute: async (planId: string, sessionId: string, signal?: AbortSignal): Promise<Response> => {
      const baseUrl = getBaseUrl();
      return fetchWithRetry(
        `${baseUrl}/v1/plans/${planId}/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
          signal,
        },
        1,
        CONFIG.TIMEOUTS.STREAMING,
        signal,
      );
    },
    delete: (planId: string) => del<{ ok: boolean }>(`/plans/${planId}`),
  },

  // ======================== Memory ========================

  memory: {
    status: () => get<{ enabled: boolean; agent_id?: string }>('/memory/status'),
  },

  // ======================== Terminal ========================

  terminal: {
    execute: (body: TerminalExecuteRequest) =>
      post<TerminalExecuteResponse>('/terminal/execute', body, { timeout: CONFIG.TIMEOUTS.TOOL_EXECUTION }),
    parse: (command: string) =>
      post<{ parsed: Record<string, unknown> }>('/terminal/parse', { command }),
    kill: (pid: number) => post<{ ok: boolean }>(`/terminal/kill/${pid}`),
    ssh: {
      getConfig: () => get<Record<string, unknown>>('/terminal/ssh/config'),
      connect: (body: Record<string, unknown>) =>
        post<{ connection_id: string }>('/terminal/ssh/connect', body),
      execute: (body: { connection_id: string; command: string }) =>
        post<TerminalExecuteResponse>('/terminal/ssh/execute', body, { timeout: CONFIG.TIMEOUTS.TOOL_EXECUTION }),
      connections: () => get<{ connections: unknown[] }>('/terminal/ssh/connections'),
      disconnect: (connectionId: string) =>
        post<{ ok: boolean }>(`/terminal/ssh/disconnect/${connectionId}`),
    },
  },

  // ======================== MCP Servers ========================

  mcp: {
    listServers: () => get<{ servers: unknown[] }>('/mcp/servers'),
    addServer: (body: Record<string, unknown>) => post<{ ok: boolean }>('/mcp/servers', body),
    removeServer: (name: string) => del<{ ok: boolean }>(`/mcp/servers/${name}`),
    refreshServer: (name: string) => post<{ ok: boolean }>(`/mcp/servers/${name}/refresh`),
    refreshTools: () => post<{ ok: boolean }>('/mcp/refresh-tools'),
    listTools: () => get<{ tools: ToolInfo[] }>('/mcp/tools'),
    initialize: () => post<{ ok: boolean }>('/mcp/initialize'),
  },

  // ======================== Design ========================

  design: {
    extractSystem: (dir: string) =>
      post<{ colors: Record<string, string>; fonts: { heading: string; body: string }; components: string[]; brandName?: string; raw?: string }>('/design/extract-system', { directory: dir }),
    exportPdf: (html: string) =>
      post<Blob>('/design/export/pdf', { html }, { parseJson: false, timeout: 60_000 }),
    exportPptx: (html: string) =>
      post<Blob>('/design/export/pptx', { html }, { parseJson: false, timeout: 60_000 }),
  },

  // ======================== Tool Results ========================

  toolResults: {
    get: (sessionId: string) => get<{ results: unknown[] }>(`/tool-results/${sessionId}`),
    getOne: (sessionId: string, toolUseId: string) =>
      get<Record<string, unknown>>(`/tool-results/${sessionId}/${toolUseId}`),
    save: (body: { session_id: string; tool_use_id: string; tool_name: string; result: unknown }) =>
      post<{ ok: boolean }>('/tool-results', body),
    cleanup: () => post<{ ok: boolean }>('/tool-results/cleanup'),
  },
};

// ---------------------------------------------------------------------------
// Path helpers for endpoints that live outside /v1
// ---------------------------------------------------------------------------

function fullUrlCall<T>(path: string, method: string = 'GET', body?: unknown) {
  const baseUrl = getBaseUrl();
  const url = `${baseUrl}${path}`;
  const options: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body != null) options.body = JSON.stringify(body);
  return apiCall<T>(url, options);
}

// Re-assign health / s3 / warmup to use correct base paths (no /v1 prefix)
api.health = {
  check: () => fullUrlCall<HealthResponse>('/health', 'GET'),
  detailed: () => fullUrlCall<{ status: string; services: Record<string, unknown> }>('/health/detailed', 'GET'),
};

api.s3 = {
  status: () => fullUrlCall<{ enabled: boolean; bucket?: string }>('/v1/s3/status'),
  sync: (sessionId: string) => fullUrlCall<{ ok: boolean }>(`/v1/s3/sync/${sessionId}`, 'POST'),
};

api.config.warmup = () => fullUrlCall<{ ok: boolean }>('/v1/warmup', 'POST');

export default api;
