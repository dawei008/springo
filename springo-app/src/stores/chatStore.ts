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
import { processStreamingResponse } from '@/services/sse';
import { api } from '@/services/api';
import { useUIStore } from '@/stores/uiStore';

const BASE_URL = 'http://127.0.0.1:8081';

/** Memory management configuration */
const MEMORY_CONFIG = {
  MAX_CACHED_SESSIONS: 10,
  GC_INTERVAL_MS: 5 * 60 * 1000,
  MIN_IDLE_TIME_MS: 3 * 60 * 1000,
};

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
        session_id: options.sessionId || convId,
        compact_model: options.compactModel || '',
      };

      // Use api.messages.sendAutoRaw for fetchWithRetry + proper error handling
      const response = await api.messages.sendAutoRaw(requestBody, abortController.signal);

      // Remove thinking indicator
      const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

      // Process SSE stream using the comprehensive parser from sse.ts
      const store = useChatStore.getState();
      await processStreamingResponse(response, convId, {
        onTextUpdate: (text, toolUses, isFinal) => {
          options.onTextUpdate?.(text, toolUses);
          store.updateAssistantMessage(convId, text, toolUses, isFinal);
        },
        onToolUse: () => {
          // Tool-use blocks are already accumulated by the parser and
          // forwarded through onTextUpdate with the updated toolUses array
        },
        onToolExecutionStart: () => {
          // Tools are added to the toolUses array by the parser
          // and state is updated on next onTextUpdate call
        },
        onToolResult: (evt) => {
          // The parser already updates toolUses[].result and status
          // Trigger a re-render with current state
          const { textContent, toolUses } = getCurrentStreamState();
          store.updateAssistantMessage(convId, textContent, toolUses, false);
        },
        onHeartbeat: (evt) => {
          // Update elapsed time on the tool — parser already does this
          // Trigger a re-render to show the updated elapsed time
          const { textContent, toolUses } = getCurrentStreamState();
          store.updateAssistantMessage(convId, textContent, toolUses, false);
        },
        onToolExecutionComplete: () => {
          // All tools done in this iteration
        },
        onSkillInjected: (skillName) => {
          console.log(`[${convId}] Skill injected: ${skillName}`);
        },
        onContextCompact: () => {
          // TODO: Show compacting status in UI
          console.log(`[${convId}] Context compacting...`);
        },
        onContextCompactDone: () => {
          console.log(`[${convId}] Context compaction complete`);
        },
        onContextCompactFailed: (evt) => {
          console.warn(`[${convId}] Context compaction failed:`, evt);
        },
        onMessagesUpdated: (evt) => {
          // Sync frontend messages after compaction
          if (evt.messages) {
            const rt = get().getRuntime(convId);
            rt.messages = evt.messages as Message[];
            set((state) => ({
              runtimes: { ...state.runtimes, [convId]: { ...rt, messages: [...rt.messages] } },
            }));
          }
        },
        onTeamSpawned: (evt) => {
          // Set active team in UI store
          useUIStore.getState().setActiveTeamId(evt.team_id);
          console.log(`[${convId}] Team spawned: ${evt.team_id}`);
        },
        onTeamPlanning: (teamId) => {
          console.log(`[${convId}] Team planning: ${teamId}`);
        },
        onTeamSynthesisDelta: () => {
          // Text already accumulated by parser via onTextUpdate
        },
        onTeamComplete: (evt) => {
          console.log(`[${convId}] Team complete:`, evt.team_id);
        },
        onTeamError: (evt) => {
          console.error(`[${convId}] Team error:`, evt);
        },
        onComplete: (text, toolUses) => {
          store.updateAssistantMessage(convId, text, toolUses, true);
          options.onComplete?.();
        },
        onError: (error) => {
          console.error(`[${convId}] Stream error:`, error);
        },
      });

      // Helper to get current stream state from the parser's accumulated data
      // processStreamingResponse returns the final result, but during streaming
      // the callbacks provide incremental updates. For re-renders triggered by
      // tool_result/heartbeat, we read the latest state from the runtime.
      function getCurrentStreamState() {
        const rt = get().getRuntime(convId);
        const lastMsg = rt.messages[rt.messages.length - 1];
        let textContent = '';
        const toolUses: ToolUse[] = [];
        if (lastMsg && lastMsg.role === 'assistant') {
          if (typeof lastMsg.displayContent === 'string') {
            textContent = lastMsg.displayContent;
          } else if (typeof lastMsg.content === 'string') {
            textContent = lastMsg.content;
          }
          if (Array.isArray(lastMsg.content)) {
            for (const block of lastMsg.content) {
              if (typeof block === 'object' && block !== null && 'type' in block && block.type === 'tool_use') {
                const tb = block as ToolUseBlock;
                toolUses.push({ id: tb.id, name: tb.name, input: tb.input || {} });
              }
            }
          }
        }
        return { textContent, toolUses };
      }
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

