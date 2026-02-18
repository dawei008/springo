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
import { useSettingsStore } from '@/stores/settingsStore';
import { useTeamStore } from '@/stores/teamStore';

const BASE_URL = 'http://127.0.0.1:8081';

/**
 * Default system prompt — kept static for KV cache efficiency.
 * Dynamic time is injected into the first user message by the backend.
 */
const DEFAULT_SYSTEM_PROMPT = `You are Springo, a helpful AI assistant with access to various tools.

## CRITICAL RULE - NO EMOJIS (STRICTLY ENFORCED)

**ABSOLUTELY DO NOT use any emojis, emoticons, or unicode symbols in your responses.** This is a strict requirement:
- NO emoji characters
- NO unicode symbols
- Use plain text only: "Done", "Error", "Success", "-", "->", "*"
- This applies to ALL responses and ALL generated files

IMPORTANT: When answering questions about current events, recent news, technical documentation, or anything that requires up-to-date information:
1. ALWAYS use the available tools to search for information first
2. DO NOT make up or guess answers - use tools to verify facts
3. If you're unsure about something, use a search tool to find accurate information

**CRITICAL - Time-sensitive searches:**
When user asks for "latest"/"recent"/"newest" content:

RULES (MUST follow ALL):
1. Use ENGLISH keywords only (never Chinese)
2. Use freshness="pw" on EVERY search call - including follow-up searches for details
3. Include the current year in query to find recent content
4. NEVER search for old content names like "Building Effective Agents" without freshness
5. Trust the FIRST search results - don't second-guess by searching for older content

Example workflow:
- User: "anthropic latest agent blog"
- Search 1: brave_web_search(query="Anthropic agent blog ${new Date().getFullYear()} latest", freshness="pw") [CORRECT]
- If need details: brave_web_search(query="<title from result> details", freshness="pw") [CORRECT]
- WRONG: brave_web_search(query="Building Effective Agents") [WRONG - finds OLD content]

WITHOUT freshness="pw", search returns OLD but popular results instead of newest!

Available MCP tool categories:
- Web search: web-search__brave_web_search (USE freshness="pw" for latest content!)
- News search: web-search__brave_news_search (for news articles)
- Documentation: strands-agents, bedrock-agentcore, context7
- File operations: read_file, write_file, glob, grep, etc.

NOTE: All web searches use MCP servers. DO NOT use built-in web_search (removed).

## Display Environment
You are running inside a GUI desktop application (Electron), NOT a terminal.
The chat window can render images inline. When you generate an image file (QR code, chart, diagram, screenshot, etc.):
1. Save the file to disk (e.g. using write_file or a Python script)
2. Mention the full file path in your response - the app will automatically detect image paths (.png, .jpg, .svg, .gif, .webp) and render them inline
3. The user can click the image to view it full-screen
Do NOT say "I cannot display images" - the GUI handles image rendering automatically.

Be concise and helpful in your responses.`;

// ---------------------------------------------------------------------------
// Message sanitization — ported from legacy app.js
// ---------------------------------------------------------------------------

// Loose block shape used during sanitization (messages from the backend
// may carry fields beyond the strict ContentBlock union).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyBlock = Record<string, any>;

interface ApiMessage {
  role: string;
  content: string | ContentBlock[];
}

/**
 * Remove orphaned tool_use / tool_result blocks that have no matching pair.
 * The Anthropic API requires every tool_use to have a corresponding tool_result
 * and vice-versa; sending orphans causes 400 errors.
 */
function sanitizeMessagesForAPI(messages: ApiMessage[]): ApiMessage[] {
  // Quick check — skip when there are no tool blocks at all (fast path)
  let hasToolBlocks = false;
  for (const msg of messages) {
    if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        const b = block as AnyBlock;
        if (b.type === 'tool_use' || b.type === 'tool_result') {
          hasToolBlocks = true;
          break;
        }
      }
      if (hasToolBlocks) break;
    }
  }
  if (!hasToolBlocks) return messages;

  // First pass: collect all tool_use IDs and tool_result IDs
  const allToolUseIds = new Set<string>();
  const allToolResultIds = new Set<string>();

  for (const msg of messages) {
    if (msg.role === 'assistant' && Array.isArray(msg.content)) {
      for (const block of msg.content) {
        const b = block as AnyBlock;
        if (b.type === 'tool_use' && b.id) allToolUseIds.add(b.id);
      }
    } else if (msg.role === 'user' && Array.isArray(msg.content)) {
      for (const block of msg.content) {
        const b = block as AnyBlock;
        if (b.type === 'tool_result' && b.tool_use_id) allToolResultIds.add(b.tool_use_id);
      }
    }
  }

  // Find orphaned tool_use IDs (tool_use without matching tool_result)
  const orphanedToolUseIds = new Set<string>();
  for (const id of allToolUseIds) {
    if (!allToolResultIds.has(id)) {
      orphanedToolUseIds.add(id);
      console.warn(`[sanitize] Orphaned tool_use id: ${id}`);
    }
  }

  // Second pass: build sanitized message list
  const sanitized: ApiMessage[] = [];

  for (const msg of messages) {
    if (msg.role === 'assistant' && Array.isArray(msg.content)) {
      const filteredContent = msg.content.filter((block) => {
        const b = block as AnyBlock;
        if (b.type === 'tool_use' && b.id && orphanedToolUseIds.has(b.id)) {
          console.warn(`[sanitize] Removing orphaned tool_use: ${b.id}`);
          return false;
        }
        return true;
      });

      if (filteredContent.length > 0) {
        const hasToolUse = filteredContent.some((b) => (b as AnyBlock).type === 'tool_use');
        if (hasToolUse) {
          sanitized.push({ role: msg.role, content: filteredContent });
        } else {
          // Only text blocks remain — flatten to string if single text block
          const textOnly = filteredContent.filter((b) => (b as AnyBlock).type === 'text');
          if (textOnly.length === filteredContent.length && textOnly.length === 1) {
            sanitized.push({ role: msg.role, content: (textOnly[0] as TextBlock).text });
          } else if (filteredContent.length > 0) {
            sanitized.push({ role: msg.role, content: filteredContent });
          }
        }
      }
    } else if (msg.role === 'user' && Array.isArray(msg.content)) {
      const hasToolResult = msg.content.some((c) => (c as AnyBlock).type === 'tool_result');
      if (hasToolResult) {
        const validResults = msg.content.filter((c) => {
          const b = c as AnyBlock;
          if (b.type !== 'tool_result') return true;
          const isValid =
            allToolUseIds.has(b.tool_use_id) && !orphanedToolUseIds.has(b.tool_use_id);
          if (!isValid) {
            console.warn(`[sanitize] Removing orphaned tool_result: ${b.tool_use_id}`);
          }
          return isValid;
        });
        if (validResults.length > 0) {
          sanitized.push({ role: msg.role, content: validResults });
        }
      } else {
        sanitized.push(msg);
      }
    } else {
      sanitized.push(msg);
    }
  }

  return sanitized;
}

/**
 * Validate and clean messages loaded from a session (e.g. after restart).
 * Removes thinking indicators, empty messages, and orphaned tool_results
 * from interrupted conversations.
 */
function validateConversationMessages(messages: Message[]): Message[] {
  if (!messages || !Array.isArray(messages)) return [];

  // Remove thinking indicators and empty messages
  let cleaned = messages.filter((m) => {
    if (m.isThinking) return false;
    if (!m.content) return false;
    if (typeof m.content === 'string' && m.content.trim() === '') return false;
    if (Array.isArray(m.content) && m.content.length === 0) return false;
    return true;
  });

  // NOTE: Do NOT strip trailing tool_result messages. They have valid matching
  // tool_use blocks in the previous assistant message. Stripping them creates
  // orphaned tool_use blocks that get removed by sanitizeMessagesForAPI, losing
  // all tool execution context. The API accepts conversations ending with a
  // user message (tool_result IS a user message).

  return cleaned;
}

/**
 * Clean content blocks before sending to API:
 * - Strip internal `_imageRef` field from image blocks
 */
function cleanContentForAPI(content: string | ContentBlock[]): string | ContentBlock[] {
  if (!Array.isArray(content)) return content;
  return content.map((block) => {
    const b = block as AnyBlock;
    if (b.type === 'image' && b._imageRef) {
      return { type: 'image', source: b.source } as ImageBlock;
    }
    return block;
  });
}

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
  sendTeamMessage: (
    convId: string,
    content: string,
    options?: {
      model?: string;
      mode?: 'classic' | 'collaborative';
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
    // Trigger reactivity — MUST create new array reference so useMemo([messages])
    // in MessageList detects the change (push alone is invisible to reference checks)
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime, messages: [...runtime.messages] } },
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

    // Find the last *streaming* assistant message (skip non-streaming ones like askUser or team→user)
    let lastMsg = messages[messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant' && (lastMsg.askUser || lastMsg._teamChat)) {
      lastMsg = undefined as unknown as Message;
    }

    if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.isThinking) {
      // Update existing assistant message
      lastMsg.displayContent = displayContent;
      if (apiContent || toolUses.length > 0) {
        lastMsg.content = apiContent;
        lastMsg.hasToolUse = toolUses.length > 0;
      }
      // Always update runtime toolUses (with status/result) for live rendering
      if (toolUses.length > 0) {
        lastMsg.toolUses = [...toolUses];
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
        toolUses: toolUses.length > 0 ? [...toolUses] : undefined,
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
        const rawMessages = (data.messages || []) as Message[];
        // Validate and clean messages (remove orphaned tool_results, etc.)
        const messages = validateConversationMessages(rawMessages);
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

    const mcpServerNames: string[] = [];

    for (const att of attachments) {
      if (att.type === 'skill' || att.type === 'mcp_server') {
        // Skill/MCP attachments: inject as context hint, not file reference
        if (att.type === 'mcp_server') {
          mcpServerNames.push(att.path || att.name || '');
        }
        // Skills are handled via activeSkill in system prompt, no extra content needed
        continue;
      } else if (att.type.startsWith('image/')) {
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

    // Build text content with file references and MCP hints
    let textContent = content || '';
    if (mcpServerNames.length > 0) {
      const mcpHint = mcpServerNames.map((n) => `Use the ${n} MCP server to `).join('; ');
      textContent = textContent ? `${mcpHint}\n\n${textContent}` : mcpHint;
    }
    if (fileAttachments.length > 0) {
      const fileList = fileAttachments.map((f) => `- ${f.name} (${f.path})`).join('\n');
      textContent = `[Attached files - use read_file tool to access them]:\n${fileList}\n\n${textContent}`;
    }
    if (textContent) {
      messageContent.push({ type: 'text', text: textContent } as TextBlock);
    }

    // Handle explicit skill invocation: fetch instructions and wrap content
    // (matches legacy: getSkillInstructions + content wrapping at app.js:4937-4944)
    // IMPORTANT: skill instructions go into API content only, NOT the UI display message.
    const activeSkill = useUIStore.getState().activeSkill;
    let skillWrappedContent = '';
    if (activeSkill && textContent) {
      try {
        const resp = await fetch(`${BASE_URL}/v1/skills/${activeSkill.name}/instructions`);
        if (resp.ok) {
          const data = await resp.json();
          const instructions = data.instructions || data.content || '';
          if (instructions) {
            skillWrappedContent = `<skill name="${activeSkill.name}">\n${instructions}\n</skill>\n\nUser request: ${textContent}\n\nPlease follow the skill instructions above to complete this task.`;
          }
        }
      } catch (e) {
        console.warn('Failed to fetch skill instructions:', e);
      }
      // Clear active skill after use
      useUIStore.getState().clearActiveSkill();
    }

    // Add user message (display version — shows original text, not skill-wrapped)
    const userMsg: Message = {
      role: 'user',
      content: messageContent.length > 0 ? messageContent : (textContent || content),
      timestamp: Date.now(),
    };
    runtime.messages.push(userMsg);

    // If skill instructions were fetched, store the API-only version separately
    // so sanitizeMessagesForAPI can use it instead of the display version
    if (skillWrappedContent) {
      (userMsg as Message & { _apiContent?: string })._apiContent = skillWrappedContent;
    }

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
      // Prepare messages for API:
      // 1. Filter out thinking indicators and empty messages
      // 2. Strip internal fields (_imageRef) from content blocks
      // 3. Sanitize tool_use/tool_result pairing (remove orphans)
      const filteredMessages = runtime.messages
        .filter((m) => !m.isThinking)
        .filter((m) => {
          if (!m.content) return false;
          if (typeof m.content === 'string' && m.content.trim() === '') return false;
          if (Array.isArray(m.content) && m.content.length === 0) return false;
          return true;
        })
        .map((m) => {
          // Use _apiContent (skill-wrapped) if available, otherwise clean the display content
          const apiContent = (m as Message & { _apiContent?: string })._apiContent;
          return { role: m.role, content: apiContent || cleanContentForAPI(m.content) };
        });

      // Sanitize to ensure tool_result/tool_use pairing is valid
      const apiMessages = sanitizeMessagesForAPI(filteredMessages);

      const settingsState = useSettingsStore.getState();
      const model = options.model || settingsState.getEffectiveModel();
      const maxTokens = options.maxTokens || 16384;
      const temperature = options.temperature ?? 0.7;

      const requestBody = {
        model,
        max_tokens: maxTokens,
        temperature,
        system: options.systemPrompt || DEFAULT_SYSTEM_PROMPT,
        messages: apiMessages,
        session_id: options.sessionId || convId,
        compact_model: options.compactModel || settingsState.getEffectiveCompactModel(),
        extended_context: options.enable1mContext !== false,
      };

      // Use api.messages.sendAutoRaw for fetchWithRetry + proper error handling
      const response = await api.messages.sendAutoRaw(requestBody, abortController.signal);

      // Remove thinking indicator
      const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

      // Process SSE stream using the comprehensive parser from sse.ts
      const store = useChatStore.getState();

      // Throttle UI updates to ~60fps via rAF to avoid re-render storm during streaming
      let rafId: number | null = null;
      let pendingText = '';
      let pendingToolUses: ToolUse[] = [];
      const flushPendingUpdate = () => {
        rafId = null;
        store.updateAssistantMessage(convId, pendingText, pendingToolUses, false);
      };

      await processStreamingResponse(response, convId, {
        onTextUpdate: (text, toolUses, isFinal) => {
          options.onTextUpdate?.(text, toolUses);
          if (isFinal) {
            // Always flush immediately on final update
            if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
            store.updateAssistantMessage(convId, text, toolUses, true);
          } else {
            // Buffer intermediate updates, flush at next animation frame
            pendingText = text;
            pendingToolUses = toolUses;
            if (rafId === null) {
              rafId = requestAnimationFrame(flushPendingUpdate);
            }
          }
        },
        onToolUse: () => {
          // Tool-use blocks are already accumulated by the parser and
          // forwarded through onTextUpdate with the updated toolUses array
        },
        onToolExecutionStart: () => {
          // Tools are added to the toolUses array by the parser
          // and state is updated on next onTextUpdate call
        },
        onToolResult: () => {
          // Parser updates toolUses[].result/status and calls onTextUpdate
        },
        onHeartbeat: () => {
          // Parser updates toolUses[].elapsed and calls onTextUpdate
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
          useUIStore.getState().setActiveTeamId(evt.team_id);
          useTeamStore.getState().setTeamSpawned(evt.team_id, evt.agents, evt.user_request);
          // Persist session → team mapping for historical restoration
          useUIStore.getState().setSessionTeam(convId, evt.team_id);
          // Auto-open right panel on Team tab
          useUIStore.getState().setRightPanelOpen(true);
          useUIStore.getState().setRightPanelTab('team');
        },
        onTeamPlanning: (teamId) => {
          useTeamStore.getState().setTeamPlanning(teamId);
        },
        onTeamTaskBoard: (evt) => {
          useTeamStore.getState().updateTaskBoard(evt.team_id, evt.tasks);
        },
        onTeamAgentStart: (evt) => {
          useTeamStore.getState().updateAgentStart(evt.team_id, evt.agent_id, evt.role, evt.task_title, evt.agent_name);
        },
        onTeamAgentProgress: (evt) => {
          useTeamStore.getState().updateAgentProgress(evt.team_id, evt.agent_id, evt.status, evt.preview);
        },
        onTeamAgentDelta: (evt) => {
          useTeamStore.getState().appendAgentDelta(evt.team_id, evt.agent_id, evt.delta);
        },
        onTeamAgentTool: (evt) => {
          useTeamStore.getState().updateAgentTool(evt.team_id, evt.agent_id, evt.tool_name, evt.status);
        },
        onTeamAgentComplete: (evt) => {
          useTeamStore.getState().updateAgentComplete(evt.team_id, evt.agent_id, evt.role, evt.findings);
        },
        onTeamAgentError: (evt) => {
          useTeamStore.getState().updateAgentError(evt.team_id, evt.agent_id, evt.error);
        },
        onTeamSynthesisDelta: () => {
          // Text already accumulated by parser via onTextUpdate
        },
        onTeamSynthesizing: (evt) => {
          useTeamStore.getState().setTeamSynthesizing(evt.team_id);
        },
        onTeamComplete: (evt) => {
          useTeamStore.getState().setTeamComplete(evt.team_id, evt.result);
        },
        onTeamError: (evt) => {
          useTeamStore.getState().setTeamError(evt.team_id, evt.error);
        },
        onTeamTaskCreated: (evt) => {
          useTeamStore.getState().updateTaskCreated(evt.team_id, evt.task_id, evt.title, evt.owner);
        },
        onTeamTaskUpdated: (evt) => {
          useTeamStore.getState().updateTaskUpdated(evt.team_id, evt.task_id, evt.status, evt.owner, evt.title);
        },
        onTeamTaskUnblocked: (evt) => {
          useTeamStore.getState().updateTaskUnblocked(evt.team_id, evt.task_id, evt.owner, evt.title);
        },
        onTeamAgentMessage: (evt) => {
          // Mirror team-lead → user messages to main chat as assistant messages (legacy parity)
          // But skip if this duplicates an ask_user question already shown in main chat
          if (evt.sender !== 'user' && evt.recipient === 'user' && evt.content) {
            const pendingAsk = useTeamStore.getState().askUser;
            if (!pendingAsk || pendingAsk.question !== evt.content) {
              const store = useChatStore.getState();
              store.addMessage(convId, { role: 'assistant', content: evt.content, timestamp: Date.now(), _teamChat: true });
            }
          }
          useTeamStore.getState().appendMessage(evt.team_id, evt.sender, evt.recipient, evt.content, evt.summary);
        },
        onTeamAgentBroadcast: (evt) => {
          useTeamStore.getState().appendMessage(evt.team_id, evt.sender, 'all', evt.content, evt.summary, true);
        },
        onTeamAskUser: (evt) => {
          // Show ask_user question in main chat FIRST (before setAskUser, so dedup check works)
          const store = useChatStore.getState();
          store.addMessage(convId, {
            role: 'assistant',
            content: evt.question,
            timestamp: Date.now(),
            askUser: {
              teamId: evt.team_id,
              agentName: evt.agent_name,
              options: evt.options || [],
            },
          });
          useTeamStore.getState().setAskUser(evt.team_id, evt.agent_name, evt.question, evt.options || []);
        },
        onTeamAgentIdle: (evt) => {
          useTeamStore.getState().updateAgentIdle(evt.team_id, evt.agent_name);
        },
        onComplete: (text, toolUses) => {
          // Detect interrupted stream: tools were executed but no final text response
          const hasCompletedTools = toolUses.some((tu) => tu.result !== undefined);
          if (hasCompletedTools && !text.trim()) {
            console.warn(`[${convId}] Stream ended after tool execution without final response`);
            store.updateAssistantMessage(
              convId,
              'Response was interrupted after tool execution. Please try again.',
              toolUses,
              true,
            );
          } else {
            store.updateAssistantMessage(convId, text, toolUses, true);
          }
        },
        onError: (error) => {
          console.error(`[${convId}] Stream error:`, error);
        },
      });

    } catch (e) {
      const error = e as Error;
      const isAbort = error.name === 'AbortError';

      // Always read the CURRENT runtime from the store (not the stale closure)
      const currentRuntime = get().getRuntime(convId);

      // Remove thinking indicator if still present
      const thinkingIdx = currentRuntime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) currentRuntime.messages.splice(thinkingIdx, 1);

      if (!isAbort) {
        // Add error message to conversation
        currentRuntime.messages.push({
          role: 'assistant',
          content: `Error: ${error.message}`,
          timestamp: Date.now(),
        });
      }

      options.onError?.(error);
    } finally {
      // Always read the CURRENT runtime from the store to avoid overwriting
      // messages that were added by the SSE stream processor
      const finalRuntime = get().getRuntime(convId);
      finalRuntime.isStreaming = false;
      set((state) => ({
        runtimes: {
          ...state.runtimes,
          [convId]: { ...finalRuntime, isStreaming: false, messages: [...finalRuntime.messages] },
        },
      }));

      // CRITICAL: In AUTO mode, the backend saves the properly structured
      // messages (separate per-iteration assistant/tool_result pairs + final
      // assistant) via _auto_save_session.  Reload from backend to sync
      // frontend state — without this, tool_result messages are missing and
      // the next turn's sanitizer strips orphaned tool_use blocks, causing
      // the model to lose all tool execution context.
      const hasToolUse = finalRuntime.messages.some((m) => m.hasToolUse);
      if (hasToolUse) {
        try {
          const resp = await fetch(`${BASE_URL}/v1/sessions/${convId}`);
          if (resp.ok) {
            const data = await resp.json();
            const rawMessages = (data.messages || []) as Message[];
            const synced = validateConversationMessages(rawMessages);
            if (synced.length > 0) {
              const rt = get().getRuntime(convId);
              rt.messages = synced;
              set((state) => ({
                runtimes: {
                  ...state.runtimes,
                  [convId]: { ...rt, messages: [...synced] },
                },
              }));
              console.log(`[${convId}] AUTO mode: synced ${synced.length} messages from backend`);
            }
          }
        } catch (syncErr) {
          console.warn(`[${convId}] AUTO mode: failed to sync from backend`, syncErr);
        }
      }

      options.onComplete?.();
    }
  },

  // ─── Team Mode Send ───

  sendTeamMessage: async (convId, content, options = {}) => {
    const runtime = get().getRuntime(convId);

    // Add user message to display
    runtime.messages.push({ role: 'user', content, timestamp: Date.now() });

    // Add thinking indicator
    runtime.messages.push({ role: 'assistant', content: '', isThinking: true });
    runtime.isStreaming = true;
    set((state) => ({
      runtimes: { ...state.runtimes, [convId]: { ...runtime, messages: [...runtime.messages] } },
    }));

    const abortController = get().resetAbortController(convId);

    try {
      const settingsState = useSettingsStore.getState();
      const model = options.model || settingsState.getEffectiveModel();
      const mode = options.mode || 'collaborative';

      // Step 1: Spawn team
      const spawnRes = await fetch(`${BASE_URL}/v1/teams/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_request: content,
          mode,
          model,
          session_id: convId,
        }),
        signal: abortController.signal,
      });

      if (!spawnRes.ok) {
        throw new Error(`Failed to spawn team: ${spawnRes.statusText}`);
      }

      const spawnData = await spawnRes.json();
      const teamId = spawnData.team_id;

      // Step 2: Execute team with SSE streaming (with reconnection)
      let reconnectCount = 0;
      let streamDone = false;
      let hasExecuted = false;

      while (!streamDone) {
        let execRes: Response;
        if (!hasExecuted) {
          execRes = await fetch(`${BASE_URL}/v1/teams/${teamId}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stream: true }),
            signal: abortController.signal,
          });
          hasExecuted = true;
        } else {
          execRes = await fetch(`${BASE_URL}/v1/teams/${teamId}/events`, {
            signal: abortController.signal,
          });
        }

        if (!execRes.ok) {
          if (execRes.status >= 400 && execRes.status < 500) break;
          reconnectCount++;
          if (reconnectCount > 50) break;
          const delay = Math.min(1000 * Math.pow(2, reconnectCount - 1), 30000);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }

        // Remove thinking indicator before SSE processing starts
        const thinkingIdx = runtime.messages.findIndex((m) => m.isThinking);
        if (thinkingIdx >= 0) runtime.messages.splice(thinkingIdx, 1);

        const store = useChatStore.getState();

        // Throttle UI updates
        let rafId: number | null = null;
        let pendingText = '';
        let pendingToolUses: ToolUse[] = [];
        const flushPendingUpdate = () => {
          rafId = null;
          store.updateAssistantMessage(convId, pendingText, pendingToolUses, false);
        };

        try {
          await processStreamingResponse(execRes, convId, {
            onTextUpdate: (text, toolUses, isFinal) => {
              if (isFinal) {
                if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
                store.updateAssistantMessage(convId, text, toolUses, true);
              } else {
                pendingText = text;
                pendingToolUses = toolUses;
                if (rafId === null) {
                  rafId = requestAnimationFrame(flushPendingUpdate);
                }
              }
            },
            onToolUse: () => {},
            onToolExecutionStart: () => {},
            onToolResult: () => {},
            onHeartbeat: () => {},
            onToolExecutionComplete: () => {},
            onTeamSpawned: (evt) => {
              useUIStore.getState().setActiveTeamId(evt.team_id);
              useTeamStore.getState().setTeamSpawned(evt.team_id, evt.agents, evt.user_request);
              useUIStore.getState().setSessionTeam(convId, evt.team_id);
              useUIStore.getState().setRightPanelOpen(true);
              useUIStore.getState().setRightPanelTab('team');
            },
            onTeamPlanning: (tid) => {
              useTeamStore.getState().setTeamPlanning(tid);
            },
            onTeamTaskBoard: (evt) => {
              useTeamStore.getState().updateTaskBoard(evt.team_id, evt.tasks);
            },
            onTeamAgentStart: (evt) => {
              useTeamStore.getState().updateAgentStart(evt.team_id, evt.agent_id, evt.role, evt.task_title, evt.agent_name);
            },
            onTeamAgentProgress: (evt) => {
              useTeamStore.getState().updateAgentProgress(evt.team_id, evt.agent_id, evt.status, evt.preview);
            },
            onTeamAgentDelta: (evt) => {
              useTeamStore.getState().appendAgentDelta(evt.team_id, evt.agent_id, evt.delta);
            },
            onTeamAgentTool: (evt) => {
              useTeamStore.getState().updateAgentTool(evt.team_id, evt.agent_id, evt.tool_name, evt.status);
            },
            onTeamAgentComplete: (evt) => {
              useTeamStore.getState().updateAgentComplete(evt.team_id, evt.agent_id, evt.role, evt.findings);
            },
            onTeamAgentError: (evt) => {
              useTeamStore.getState().updateAgentError(evt.team_id, evt.agent_id, evt.error);
            },
            onTeamSynthesisDelta: () => {},
            onTeamSynthesizing: (evt) => {
              useTeamStore.getState().setTeamSynthesizing(evt.team_id);
            },
            onTeamComplete: (evt) => {
              useTeamStore.getState().setTeamComplete(evt.team_id, evt.result);
              streamDone = true;
            },
            onTeamError: (evt) => {
              useTeamStore.getState().setTeamError(evt.team_id, evt.error);
              streamDone = true;
            },
            onTeamTaskCreated: (evt) => {
              useTeamStore.getState().updateTaskCreated(evt.team_id, evt.task_id, evt.title, evt.owner);
            },
            onTeamTaskUpdated: (evt) => {
              useTeamStore.getState().updateTaskUpdated(evt.team_id, evt.task_id, evt.status, evt.owner, evt.title);
            },
            onTeamTaskUnblocked: (evt) => {
              useTeamStore.getState().updateTaskUnblocked(evt.team_id, evt.task_id, evt.owner, evt.title);
            },
            onTeamAgentMessage: (evt) => {
              // Mirror team-lead → user messages to main chat as assistant messages (legacy parity)
              // But skip if this duplicates an ask_user question already shown in main chat
              if (evt.sender !== 'user' && evt.recipient === 'user' && evt.content) {
                const pendingAsk = useTeamStore.getState().askUser;
                if (!pendingAsk || pendingAsk.question !== evt.content) {
                  store.addMessage(convId, { role: 'assistant', content: evt.content, timestamp: Date.now(), _teamChat: true });
                }
              }
              useTeamStore.getState().appendMessage(evt.team_id, evt.sender, evt.recipient, evt.content, evt.summary);
            },
            onTeamAgentBroadcast: (evt) => {
              useTeamStore.getState().appendMessage(evt.team_id, evt.sender, 'all', evt.content, evt.summary, true);
            },
            onTeamAskUser: (evt) => {
              // Show ask_user question in main chat FIRST (before setAskUser, so dedup check works)
              store.addMessage(convId, {
                role: 'assistant',
                content: evt.question,
                timestamp: Date.now(),
                askUser: {
                  teamId: evt.team_id,
                  agentName: evt.agent_name,
                  options: evt.options || [],
                },
              });
              useTeamStore.getState().setAskUser(evt.team_id, evt.agent_name, evt.question, evt.options || []);
            },
            onTeamAgentIdle: (evt) => {
              useTeamStore.getState().updateAgentIdle(evt.team_id, evt.agent_name);
            },
            onComplete: (text) => {
              if (text) {
                store.updateAssistantMessage(convId, text, [], true);
              }
              streamDone = true;
            },
            onError: (error) => {
              console.error(`[${convId}] Team stream error:`, error);
            },
          });
        } catch (streamErr) {
          const err = streamErr as Error;
          if (err.name === 'AbortError') throw streamErr;
          // Stream disconnected — try reconnecting
        }

        if (!streamDone) {
          reconnectCount++;
          if (reconnectCount > 50) break;
          const delay = Math.min(1000 * Math.pow(2, reconnectCount - 1), 30000);
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    } catch (e) {
      const error = e as Error;
      const currentRuntime = get().getRuntime(convId);
      const thinkingIdx = currentRuntime.messages.findIndex((m) => m.isThinking);
      if (thinkingIdx >= 0) currentRuntime.messages.splice(thinkingIdx, 1);

      if (error.name !== 'AbortError') {
        currentRuntime.messages.push({
          role: 'assistant',
          content: `Team Error: ${error.message}`,
          timestamp: Date.now(),
        });
      }
    } finally {
      const finalRuntime = get().getRuntime(convId);
      finalRuntime.isStreaming = false;
      set((state) => ({
        runtimes: {
          ...state.runtimes,
          [convId]: { ...finalRuntime, isStreaming: false, messages: [...finalRuntime.messages] },
        },
      }));
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

