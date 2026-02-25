/**
 * Springo SSE Stream Parser
 *
 * Async-generator-based SSE parser and high-level stream processor
 * for /v1/messages-auto responses.
 */

import type {
  SSEFrame,
  SSEEventType,
  ToolUse,
  ToolResultEvent,
  HeartbeatEvent,
  ToolExecutionStartEvent,
  TeamSpawnedEvent,
  TeamTaskBoardEvent,
  TeamAgentStartEvent,
  TeamAgentProgressEvent,
  TeamAgentCompleteEvent,
  TeamAgentErrorEvent,
  TeamAgentDeltaEvent,
  TeamAgentToolEvent,
  TeamSynthesizingEvent,
  TeamCompleteEvent,
  TeamErrorEvent,
  TeamAgentMessageEvent,
  TeamAgentBroadcastEvent,
  TeamAskUserEvent,
  TeamAgentIdleEvent,
  TeamAgentShutdownEvent,
  TeamTaskCreatedEvent,
  TeamTaskUpdatedEvent,
  TeamTaskUnblockedEvent,
  ContextCompactEvent,
  ContextCompactDoneEvent,
  ContextCompactFailedEvent,
  MessagesUpdatedEvent,
} from '../types';
import { CONFIG } from '../types';

// ---------------------------------------------------------------------------
// Low-level SSE parser
// ---------------------------------------------------------------------------

const SSE_BUFFER_LIMIT = 10 * 1024 * 1024; // 10 MB safety limit

/**
 * Parse a ReadableStream of SSE bytes into typed frames.
 *
 * Yields `{ event, data }` for each complete SSE block.
 * Throws on timeout (no data received for `timeoutMs`).
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number = CONFIG.TIMEOUTS.SSE_HEARTBEAT,
): AsyncGenerator<SSEFrame, void, undefined> {
  const decoder = new TextDecoder();
  let buffer = '';

  async function readWithTimeout(): Promise<ReadableStreamReadResult<Uint8Array>> {
    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        reject(new Error(`SSE stream timeout: no data received for ${timeoutMs / 1000}s`));
      }, timeoutMs);

      reader
        .read()
        .then((result) => {
          clearTimeout(timeoutId);
          resolve(result);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          reject(err);
        });
    });
  }

  while (true) {
    const { done, value } = await readWithTimeout();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Split on double newlines (SSE event separator)
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    // Safety: prevent unbounded buffer growth
    if (buffer.length > SSE_BUFFER_LIMIT) {
      console.error('SSE buffer overflow, clearing');
      buffer = '';
    }

    for (const eventBlock of events) {
      if (!eventBlock.trim()) continue;

      const lines = eventBlock.split('\n');
      let eventType: string | null = null;
      let eventData: string | null = null;

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          eventData = line.slice(6);
        }
      }

      if (eventType && eventData) {
        try {
          yield { event: eventType, data: JSON.parse(eventData) };
        } catch (e) {
          console.warn('SSE parse error:', e, eventData?.substring(0, 200));
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Callback interface for processStreamingResponse
// ---------------------------------------------------------------------------

export interface StreamCallbacks {
  /** Incremental text + tool-use update (called frequently during streaming). */
  onTextUpdate: (text: string, toolUses: ToolUse[], isFinal: boolean) => void;

  /** A tool_use block was fully parsed from the stream. */
  onToolUse?: (tool: ToolUse) => void;

  /** Server-side tool execution started. */
  onToolExecutionStart?: (tools: ToolExecutionStartEvent['tools']) => void;

  /** A single tool is now executing. */
  onToolExecuting?: (id: string, name: string) => void;

  /** A tool finished executing and returned a result. */
  onToolResult?: (event: ToolResultEvent) => void;

  /** Backend heartbeat during long tool execution. */
  onHeartbeat?: (event: HeartbeatEvent) => void;

  /** All server-side tool executions in this iteration are done. */
  onToolExecutionComplete?: (count: number) => void;

  /** A skill was injected into the system prompt. */
  onSkillInjected?: (skillName: string) => void;

  // --- Context management ---
  onContextCompact?: (event: ContextCompactEvent) => void;
  onContextCompactDone?: (event: ContextCompactDoneEvent) => void;
  onContextCompactFailed?: (event: ContextCompactFailedEvent) => void;
  onMessagesUpdated?: (event: MessagesUpdatedEvent) => void;

  // --- Team events ---
  onTeamSpawned?: (event: TeamSpawnedEvent) => void;
  onTeamPlanning?: (teamId: string) => void;
  onTeamTaskBoard?: (event: TeamTaskBoardEvent) => void;
  onTeamAgentStart?: (event: TeamAgentStartEvent) => void;
  onTeamAgentProgress?: (event: TeamAgentProgressEvent) => void;
  onTeamAgentComplete?: (event: TeamAgentCompleteEvent) => void;
  onTeamAgentError?: (event: TeamAgentErrorEvent) => void;
  onTeamAgentDelta?: (event: TeamAgentDeltaEvent) => void;
  onTeamAgentTool?: (event: TeamAgentToolEvent) => void;
  onTeamSynthesisDelta?: (delta: string) => void;
  onTeamSynthesizing?: (event: TeamSynthesizingEvent) => void;
  onTeamComplete?: (event: TeamCompleteEvent) => void;
  onTeamError?: (event: TeamErrorEvent) => void;
  onTeamAgentMessage?: (event: TeamAgentMessageEvent) => void;
  onTeamAgentBroadcast?: (event: TeamAgentBroadcastEvent) => void;
  onTeamAskUser?: (event: TeamAskUserEvent) => void;
  onTeamAgentIdle?: (event: TeamAgentIdleEvent) => void;
  onTeamAgentShutdown?: (event: TeamAgentShutdownEvent) => void;
  onTeamTaskCreated?: (event: TeamTaskCreatedEvent) => void;
  onTeamTaskUpdated?: (event: TeamTaskUpdatedEvent) => void;
  onTeamTaskUnblocked?: (event: TeamTaskUnblockedEvent) => void;

  // --- Lifecycle ---
  onComplete: (text: string, toolUses: ToolUse[]) => void;
  onError?: (error: Error) => void;
}

// ---------------------------------------------------------------------------
// High-level stream processor
// ---------------------------------------------------------------------------

export interface StreamResult {
  textContent: string;
  toolUses: ToolUse[];
}

/**
 * Process a streaming SSE response from /v1/messages-auto.
 *
 * Manages the incremental text buffer, tool-use JSON accumulation,
 * and dispatches callbacks for every SSE event type.
 */
export async function processStreamingResponse(
  response: Response,
  convId: string,
  callbacks: StreamCallbacks,
): Promise<StreamResult> {
  const reader = response.body!.getReader();
  let textContent = '';
  let toolUses: ToolUse[] = [];
  let currentToolUse: { id: string; name: string; input: Record<string, unknown> } | null = null;
  let currentToolInput = '';
  let streamCompleted = false;

  const STREAM_TIMEOUT_MS = CONFIG.TIMEOUTS.SSE_HEARTBEAT;

  try {
    for await (const { event, data } of parseSSEStream(reader, STREAM_TIMEOUT_MS)) {
      const eventType = event as SSEEventType;

      switch (eventType) {
        // ---- Core message events ----

        case 'message_start':
          break;

        case 'content_block_start': {
          const block = (data as Record<string, unknown>).content_block as {
            type: string;
            id?: string;
            name?: string;
          };
          if (block.type === 'tool_use') {
            currentToolUse = { id: block.id!, name: block.name!, input: {} };
            currentToolInput = '';
          }
          break;
        }

        case 'content_block_delta': {
          const delta = (data as Record<string, unknown>).delta as Record<string, unknown>;
          if (delta.type === 'text_delta') {
            textContent += delta.text as string;
            callbacks.onTextUpdate(textContent, toolUses, false);
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
            const tool: ToolUse = { ...currentToolUse };
            toolUses.push(tool);
            console.log(`[SSE] tool_use accumulated: ${tool.name} (total: ${toolUses.length})`);
            callbacks.onToolUse?.(tool);
            currentToolUse = null;
            currentToolInput = '';
            callbacks.onTextUpdate(textContent, toolUses, false);
          }
          break;
        }

        case 'message_stop':
          break;

        // ---- Server-side tool execution events ----

        case 'tool_execution_start': {
          const evt = data as ToolExecutionStartEvent;
          if (evt.tools) {
            for (const t of evt.tools) {
              if (!toolUses.find((tu) => tu.id === t.id)) {
                toolUses.push({ id: t.id, name: t.name, input: t.input || {}, status: 'running' });
                console.log(`[SSE] tool_execution_start added: ${t.name} (total: ${toolUses.length})`);
              }
            }
          }
          callbacks.onToolExecutionStart?.(evt.tools);
          // Push running tools to UI immediately
          callbacks.onTextUpdate(textContent, toolUses, false);
          break;
        }

        case 'tool_start':
        case 'tool_executing': {
          // Backend sends 'tool_start' with { tool_use_id, tool_name }
          const evt = data as { id?: string; name?: string; tool_use_id?: string; tool_name?: string };
          const toolId = evt.id || evt.tool_use_id || '';
          const toolName = evt.name || evt.tool_name || '';
          const executing = toolUses.find((tu) => tu.id === toolId);
          if (executing) executing.status = 'running';
          callbacks.onToolExecuting?.(toolId, toolName);
          // Push status update to UI
          callbacks.onTextUpdate(textContent, toolUses, false);
          break;
        }

        case 'tool_result': {
          const evt = data as ToolResultEvent;
          const match = toolUses.find((tu) => tu.id === evt.tool_use_id);
          if (match) {
            match.result = evt.result;
            match.status = 'complete';
          }
          callbacks.onToolResult?.(evt);
          // Push updated toolUses (with status/result) to the UI
          callbacks.onTextUpdate(textContent, toolUses, false);
          break;
        }

        case 'heartbeat': {
          // Backend sends { elapsed, tool_use_id? }, normalize to HeartbeatEvent
          const raw = data as Record<string, unknown>;
          const evt: HeartbeatEvent = {
            tool_id: (raw.tool_id || raw.tool_use_id || '') as string,
            tool_name: (raw.tool_name || '') as string,
            elapsed_seconds: (raw.elapsed_seconds ?? raw.elapsed ?? 0) as number,
          };
          const hbTool = toolUses.find((tu) => tu.id === evt.tool_id);
          if (hbTool) hbTool.elapsed = evt.elapsed_seconds;
          callbacks.onHeartbeat?.(evt);
          // Push updated elapsed time to the UI
          callbacks.onTextUpdate(textContent, toolUses, false);
          break;
        }

        case 'tool_execution_complete': {
          const evt = data as { count: number };
          callbacks.onToolExecutionComplete?.(evt.count);
          break;
        }

        case 'skill_injected': {
          const evt = data as { skill_name: string };
          callbacks.onSkillInjected?.(evt.skill_name);
          break;
        }

        // ---- Context management events ----

        case 'context_compact':
          callbacks.onContextCompact?.(data as ContextCompactEvent);
          break;

        case 'context_compact_done':
          callbacks.onContextCompactDone?.(data as ContextCompactDoneEvent);
          break;

        case 'context_compact_failed':
          callbacks.onContextCompactFailed?.(data as ContextCompactFailedEvent);
          break;

        case 'messages_updated':
          callbacks.onMessagesUpdated?.(data as MessagesUpdatedEvent);
          break;

        // ---- Team events ----

        case 'team_spawned':
          callbacks.onTeamSpawned?.(data as TeamSpawnedEvent);
          break;

        case 'team_planning':
          callbacks.onTeamPlanning?.((data as { team_id: string }).team_id);
          break;

        case 'team_task_board':
          callbacks.onTeamTaskBoard?.(data as TeamTaskBoardEvent);
          break;

        case 'team_agent_start':
          callbacks.onTeamAgentStart?.(data as TeamAgentStartEvent);
          break;

        case 'team_agent_progress':
          callbacks.onTeamAgentProgress?.(data as TeamAgentProgressEvent);
          break;

        case 'team_agent_complete':
          callbacks.onTeamAgentComplete?.(data as TeamAgentCompleteEvent);
          break;

        case 'team_agent_error':
          callbacks.onTeamAgentError?.(data as TeamAgentErrorEvent);
          break;

        case 'team_agent_delta':
          callbacks.onTeamAgentDelta?.(data as TeamAgentDeltaEvent);
          break;

        case 'team_agent_tool':
          callbacks.onTeamAgentTool?.(data as TeamAgentToolEvent);
          break;

        case 'team_synthesis_delta': {
          const delta = (data as { delta: string }).delta;
          textContent += delta;
          callbacks.onTextUpdate(textContent, toolUses, false);
          callbacks.onTeamSynthesisDelta?.(delta);
          break;
        }

        case 'team_synthesizing':
          callbacks.onTeamSynthesizing?.(data as TeamSynthesizingEvent);
          break;

        case 'team_complete':
          callbacks.onTeamComplete?.(data as TeamCompleteEvent);
          break;

        case 'team_error':
          callbacks.onTeamError?.(data as TeamErrorEvent);
          break;

        case 'team_agent_message':
          callbacks.onTeamAgentMessage?.(data as TeamAgentMessageEvent);
          break;

        case 'team_agent_broadcast':
          callbacks.onTeamAgentBroadcast?.(data as TeamAgentBroadcastEvent);
          break;

        case 'team_ask_user':
          callbacks.onTeamAskUser?.(data as TeamAskUserEvent);
          break;

        case 'team_agent_idle':
          callbacks.onTeamAgentIdle?.(data as TeamAgentIdleEvent);
          break;

        case 'team_agent_shutdown':
          callbacks.onTeamAgentShutdown?.(data as TeamAgentShutdownEvent);
          break;

        case 'team_task_created':
          callbacks.onTeamTaskCreated?.(data as TeamTaskCreatedEvent);
          break;

        case 'team_task_updated':
          callbacks.onTeamTaskUpdated?.(data as TeamTaskUpdatedEvent);
          break;

        case 'team_task_unblocked':
          callbacks.onTeamTaskUnblocked?.(data as TeamTaskUnblockedEvent);
          break;

        // ---- Error ----

        case 'error': {
          const errData = data as { error?: { message: string } };
          throw new Error(errData.error?.message || 'Stream error');
        }
      }
    }

    streamCompleted = true;
    console.log(`[SSE] Stream complete: ${toolUses.length} tools accumulated, text length: ${textContent.length}`);
    callbacks.onComplete(textContent, toolUses);
    return { textContent, toolUses };
  } catch (e) {
    const error = e as Error;
    console.error(`[${convId}] Stream error:`, error);
    if (!streamCompleted) {
      callbacks.onComplete(textContent, toolUses);
    }
    callbacks.onError?.(error);
    throw error;
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Ignore cancel errors — reader may already be closed
    }
  }
}
