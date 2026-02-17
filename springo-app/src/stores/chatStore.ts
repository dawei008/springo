import { create } from 'zustand';
import type {
  Message,
  ContentBlock,
  TextBlock,
  ImageBlock,
  ToolUseBlock,
  ConvRuntime,
  ToolUse,
} from '@/types';

const BASE_URL = 'http://127.0.0.1:8081';

/** Memory management configuration */
const MEMORY_CONFIG = {
  MAX_CACHED_SESSIONS: 10,
  GC_INTERVAL_MS: 5 * 60 * 1000,
  MIN_IDLE_TIME_MS: 3 * 60 * 1000,
};

/** SSE event types from the streaming response */
type SSEEvent =
  | 'message_start'
  | 'content_block_start'
  | 'content_block_delta'
  | 'content_block_stop'
  | 'message_stop'
  | 'tool_execution_start'
  | 'tool_execution_complete'
  | 'tool_result'
  | 'iteration_complete'
  | 'error'
  | 'ping';

interface ChatState {
  runtimes: Record<string, ConvRuntime>;
  abortControllers: Record<string, AbortController>;
  recentlyAccessedSessions: string[];

  // Core accessors
  getRuntime: (convId: string) => ConvRuntime;
  isStreaming: (convId: string) => boolean;
  getStreamingConvIds: () => string[];

  // Message actions
  addMessage: (convId: string, message: Message) => void;
  updateAssistantMessage: (
    convId: string,
    text: string,
    toolUses: ToolUse[],
    isFinal: boolean,
  ) => void;
  setStreaming: (convId: string, streaming: boolean) => void;
  loadMessages: (convId: string) => Promise<Message[]>;

  // Streaming / Send
  sendMessage: (
    convId: string,
    content: string,
    attachments?: Array<{ type: string; data?: string; name?: string; path?: string }>,
    options?: {
      model?: string;
      maxTokens?: number;
      temperature?: number;
      systemPrompt?: string;
      compactModel?: string;
      enable1mContext?: boolean;
      sessionId?: string;
      onTextUpdate?: (text: string, tools: ToolUse[]) => void;
      onComplete?: () => void;
      onError?: (error: Error) => void;
    },
  ) => Promise<void>;
  stopTask: (convId: string) => void;

  // Cleanup
  resetStuckConversations: () => number;
  cleanupInactiveRuntimes: (currentSessionId: string | null) => number;
  cleanupRuntime: (convId: string) => void;

  // Abort controller management
  getAbortController: (convId: string) => AbortController;
  resetAbortController: (convId: string) => AbortController;
}

function createEmptyRuntime(): ConvRuntime {
  return {
    isStreaming: false,
    attachments: [],
    messages: [],
    delegatedTasks: {},
    incomingTasks: {},
    delegationQueue: [],
    todos: [],
  };
}

export const useChatStore = create<ChatState>((set, get) => ({
  runtimes: {},
  abortControllers: {},
  recentlyAccessedSessions: [],

  // ─── Accessors ───

  getRuntime: (convId: string) => {
    const { runtimes } = get();
    if (runtimes[convId]) return runtimes[convId];

    // Create and persist a new runtime
    const runtime = createEmptyRuntime();
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: runtime },
      recentlyAccessedSessions: [
        convId,
        ...state.recentlyAccessedSessions.filter((id) => id !== convId),
      ].slice(0, MEMORY_CONFIG.MAX_CACHED_SESSIONS * 2),
    }));
    return runtime;
  },

  isStreaming: (convId: string) => {
    return get().runtimes[convId]?.isStreaming ?? false;
  },

  getStreamingConvIds: () => {
    const { runtimes } = get();
    return Object.keys(runtimes).filter((id) => runtimes[id].isStreaming);
  },

  // ─── Message Actions ───

  addMessage: (convId: string, message: Message) => {
    const runtime = get().getRuntime(convId);
    runtime.messages.push(message);
    // Trigger reactivity
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime } },
    }));
  },

  updateAssistantMessage: (
    convId: string,
    text: string,
    toolUses: ToolUse[],
    isFinal: boolean,
  ) => {
    const runtime = get().getRuntime(convId);
    const messages = runtime.messages;

    let displayContent = text || '';
    if (isFinal && toolUses.length > 0) {
      const withResults = toolUses.filter((tu) => tu.result !== undefined);
      if (withResults.length > 0 && !displayContent) {
        displayContent = `Task completed with ${withResults.length} tool${withResults.length > 1 ? 's' : ''} executed.`;
      }
    }

    // Build API content structure
    let apiContent: string | ContentBlock[] = text || '';
    if (toolUses.length > 0) {
      const contentBlocks: ContentBlock[] = [];
      if (text) contentBlocks.push({ type: 'text', text } as TextBlock);
      for (const tu of toolUses) {
        contentBlocks.push({
          type: 'tool_use',
          id: tu.id,
          name: tu.name,
          input: tu.input || {},
        } as ToolUseBlock);
      }
      apiContent = contentBlocks;
    }

    // Don't add empty messages during streaming
    if (!text && toolUses.length === 0 && !isFinal) return;

    const lastMsg = messages[messages.length - 1];

    if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.isThinking) {
      // Update existing assistant message
      lastMsg.displayContent = displayContent;
      if (apiContent || toolUses.length > 0) {
        lastMsg.content = apiContent;
        lastMsg.hasToolUse = toolUses.length > 0;
      }
    } else if (text || toolUses.length > 0 || isFinal) {
      // Remove thinking indicator
      const thinkingIdx = messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) messages.splice(thinkingIdx, 1);

      messages.push({
        role: 'assistant',
        content: apiContent || text || '',
        displayContent,
        hasToolUse: toolUses.length > 0,
        timestamp: Date.now(),
      });
    }

    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime, messages: [...messages] } },
    }));
  },

  setStreaming: (convId: string, streaming: boolean) => {
    const runtime = get().getRuntime(convId);
    set((state) => ({
      runtimes: {
        ...state.runtimes,
        [convId]: { ...runtime, isStreaming: streaming },
      },
    }));
  },

  loadMessages: async (convId: string) => {
    try {
      const response = await fetch(`${BASE_URL}/v1/sessions/${convId}`);
      if (response.ok) {
        const data = await response.json();
        const messages = (data.messages || []) as Message[];
        const runtime = get().getRuntime(convId);
        set((state) => ({
          runtimes: {
            ...state.runtimes,
            [convId]: { ...runtime, messages },
          },
        }));
        return messages;
      }
    } catch (e) {
      console.error('loadMessages error:', e);
    }
    return [];
  },

  // ─── Streaming / Send ───

  sendMessage: async (convId, content, attachments = [], options = {}) => {
    const store = get();
    const runtime = store.getRuntime(convId);

    // Build message content blocks
    const messageContent: ContentBlock[] = [];
    const fileAttachments: Array<{ name: string; type: string; path: string }> = [];

    for (const att of attachments) {
      if (att.type.startsWith('image/')) {
        messageContent.push({
          type: 'image',
          source: { type: 'base64', media_type: att.type, data: att.data || '' },
        } as ImageBlock);
      } else {
        fileAttachments.push({
          name: att.name || 'file',
          type: att.type,
          path: att.path || att.name || 'file',
        });
      }
    }

    // Build text content with file references
    let textContent = content || '';
    if (fileAttachments.length > 0) {
      const fileList = fileAttachments.map((f) => `- ${f.name} (${f.path})`).join('\n');
      textContent = `[Attached files - use read_file tool to access them]:\n${fileList}\n\n${textContent}`;
    }
    if (textContent) {
      messageContent.push({ type: 'text', text: textContent } as TextBlock);
    }

    // Add user message
    const userMsg: Message = {
      role: 'user',
      content: attachments.length > 0 ? messageContent : content,
      timestamp: Date.now(),
    };
    runtime.messages.push(userMsg);

    // Mark streaming
    runtime.isStreaming = true;
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime } },
    }));

    // Add thinking indicator
    runtime.messages.push({
      role: 'assistant',
      content: '',
      isThinking: true,
    });
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime, messages: [...runtime.messages] } },
    }));

    // Reset abort controller
    const abortController = get().resetAbortController(convId);

    try {
      // Prepare messages for API
      const apiMessages = runtime.messages
        .filter((m) => !m.isThinking)
        .filter((m) => {
          if (!m.content) return false;
          if (typeof m.content === 'string' && m.content.trim() === '') return false;
          if (Array.isArray(m.content) && m.content.length === 0) return false;
          return true;
        })
        .map((m) => ({ role: m.role, content: m.content }));

      const model = options.model || 'claude-opus-4-6';
      const maxTokens = options.maxTokens || 16384;
      const temperature = options.temperature ?? 0.7;

      const requestBody = {
        model,
        max_tokens: maxTokens,
        temperature,
        system: options.systemPrompt || '',
        messages: apiMessages,
        stream: true,
        compact_model: options.compactModel || '',
        session_id: options.sessionId || convId,
        extended_context: options.enable1mContext !== false,
      };

      const reqHeaders: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (model.startsWith('claude-')) {
        reqHeaders['anthropic-version'] = '2023-06-01';
      }

      const fetchController = new AbortController();
      const timeoutId = setTimeout(() => fetchController.abort(), 900000);

      // Link external abort
      abortController.signal.addEventListener('abort', () =>
        fetchController.abort(),
      );

      const response = await fetch(`${BASE_URL}/v1/messages-auto`, {
        method: 'POST',
        headers: reqHeaders,
        body: JSON.stringify(requestBody),
        signal: fetchController.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP ${response.status}`);
      }

      // Remove thinking indicator
      const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

      // Process SSE stream
      await processSSEStream(
        response,
        convId,
        options.onTextUpdate,
        options.onComplete,
      );
    } catch (e) {
      const error = e as Error;
      const isAbort = error.name === 'AbortError';

      // Remove thinking indicator if still present
      const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

      if (!isAbort) {
        // Add error message to conversation
        runtime.messages.push({
          role: 'assistant',
          content: `Error: ${error.message}`,
          timestamp: Date.now(),
        });
      }

      options.onError?.(error);
    } finally {
      runtime.isStreaming = false;
      set((state) => ({
        runtimes: {
          ...state.runtimes,
          [convId]: { ...runtime, isStreaming: false, messages: [...runtime.messages] },
        },
      }));
      options.onComplete?.();
    }
  },

  stopTask: (convId: string) => {
    const { abortControllers, runtimes } = get();
    const controller = abortControllers[convId];
    if (controller) {
      controller.abort();
    }

    const runtime = runtimes[convId];
    if (runtime) {
      runtime.isStreaming = false;

      // Remove thinking indicator
      const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

      set((state) => ({
        runtimes: {
          ...state.runtimes,
          [convId]: { ...runtime, isStreaming: false, messages: [...runtime.messages] },
        },
      }));
    }
  },

  // ─── Cleanup ───

  resetStuckConversations: () => {
    const { runtimes } = get();
    let resetCount = 0;
    const updated = { ...runtimes };

    for (const convId of Object.keys(updated)) {
      if (updated[convId].isStreaming) {
        updated[convId] = { ...updated[convId], isStreaming: false };
        resetCount++;
      }
    }

    if (resetCount > 0) {
      set({ runtimes: updated });
    }
    return resetCount;
  },

  cleanupInactiveRuntimes: (currentSessionId: string | null) => {
    const { runtimes, recentlyAccessedSessions } = get();
    const streamingIds = Object.keys(runtimes).filter(
      (id) => runtimes[id].isStreaming,
    );
    const keepIds = new Set(
      [
        currentSessionId,
        ...streamingIds,
        ...recentlyAccessedSessions.slice(0, MEMORY_CONFIG.MAX_CACHED_SESSIONS),
      ].filter(Boolean) as string[],
    );

    let cleanedCount = 0;
    const updated = { ...runtimes };
    const updatedAbort = { ...get().abortControllers };

    for (const convId of Object.keys(updated)) {
      if (keepIds.has(convId)) continue;
      if (updated[convId].isStreaming) continue;

      delete updated[convId];
      // Cleanup abort controller
      if (updatedAbort[convId]) {
        try {
          updatedAbort[convId].abort();
        } catch {
          // ignore
        }
        delete updatedAbort[convId];
      }
      cleanedCount++;
    }

    if (cleanedCount > 0) {
      set({ runtimes: updated, abortControllers: updatedAbort });
      console.log(`[Memory GC] Cleaned up ${cleanedCount} inactive session runtimes`);
    }
    return cleanedCount;
  },

  cleanupRuntime: (convId: string) => {
    set((state) => {
      const runtimes = { ...state.runtimes };
      const abortControllers = { ...state.abortControllers };
      delete runtimes[convId];
      if (abortControllers[convId]) {
        try {
          abortControllers[convId].abort();
        } catch {
          // ignore
        }
        delete abortControllers[convId];
      }
      return { runtimes, abortControllers };
    });
  },

  // ─── Abort Controller Management ───

  getAbortController: (convId: string) => {
    const { abortControllers } = get();
    if (!abortControllers[convId]) {
      const controller = new AbortController();
      set((state) => ({
        abortControllers: { ...state.abortControllers, [convId]: controller },
      }));
      return controller;
    }
    return abortControllers[convId];
  },

  resetAbortController: (convId: string) => {
    const controller = new AbortController();
    set((state) => ({
      abortControllers: { ...state.abortControllers, [convId]: controller },
    }));
    return controller;
  },
}));

// ─── SSE Stream Processor (module-level helper) ───

async function processSSEStream(
  response: Response,
  convId: string,
  onTextUpdate?: (text: string, tools: ToolUse[]) => void,
  onComplete?: () => void,
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let textContent = '';
  let toolUses: ToolUse[] = [];
  let currentToolUse: Partial<ToolUse> | null = null;
  let currentToolInput = '';

  const store = useChatStore.getState();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const dataStr = line.slice(6).trim();
        if (dataStr === '[DONE]') continue;

        let parsed: { type?: SSEEvent; event?: SSEEvent; delta?: Record<string, unknown>; content_block?: Record<string, unknown>; tools?: Array<Record<string, unknown>>; result?: unknown; tool_id?: string };
        try {
          parsed = JSON.parse(dataStr);
        } catch {
          continue;
        }

        const event = (parsed.type || parsed.event || '') as SSEEvent;

        switch (event) {
          case 'content_block_start': {
            const block = parsed.content_block;
            if (block && block.type === 'tool_use') {
              currentToolUse = {
                id: block.id as string,
                name: block.name as string,
                input: {},
              };
              currentToolInput = '';
            }
            break;
          }

          case 'content_block_delta': {
            const delta = parsed.delta;
            if (!delta) break;
            if (delta.type === 'text_delta') {
              textContent += delta.text as string;
              onTextUpdate?.(textContent, toolUses);
              store.updateAssistantMessage(convId, textContent, toolUses, false);
            } else if (delta.type === 'input_json_delta' && currentToolUse) {
              currentToolInput += delta.partial_json as string;
            }
            break;
          }

          case 'content_block_stop': {
            if (currentToolUse) {
              try {
                currentToolUse.input = JSON.parse(currentToolInput || '{}');
              } catch {
                currentToolUse.input = {};
              }
              toolUses.push(currentToolUse as ToolUse);
              currentToolUse = null;
              currentToolInput = '';
              onTextUpdate?.(textContent, toolUses);
              store.updateAssistantMessage(convId, textContent, toolUses, false);
            }
            break;
          }

          case 'tool_execution_start': {
            if (parsed.tools) {
              for (const tool of parsed.tools) {
                if (!toolUses.find((tu) => tu.id === tool.id)) {
                  toolUses.push({
                    id: tool.id as string,
                    name: tool.name as string,
                    input: (tool.input || {}) as Record<string, unknown>,
                    status: 'running',
                  });
                }
              }
              onTextUpdate?.(textContent, toolUses);
            }
            break;
          }

          case 'tool_execution_complete':
          case 'tool_result': {
            if (parsed.tool_id && parsed.result !== undefined) {
              const tu = toolUses.find((t) => t.id === parsed.tool_id);
              if (tu) {
                tu.result = parsed.result as Record<string, unknown> | null;
                tu.status = 'complete';
              }
            }
            break;
          }

          case 'message_stop': {
            // Final update
            store.updateAssistantMessage(convId, textContent, toolUses, true);
            onComplete?.();
            break;
          }

          case 'error': {
            console.error(`[${convId}] SSE error event:`, parsed);
            break;
          }

          default:
            break;
        }
      }
    }

    // Ensure final state is set even if message_stop wasn't received
    store.updateAssistantMessage(convId, textContent, toolUses, true);
  } finally {
    reader.releaseLock();
  }
}
