import { create } from 'zustand';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';

// ---------------------------------------------------------------------------
// Schedule Task types (ported from legacy scheduler engine)
// ---------------------------------------------------------------------------

export interface ScheduleTask {
  id: string;
  name: string;
  prompt: string;
  scheduleType: 'cron' | 'delay' | 'once';
  scheduleValue: string;
  enabled: boolean;
  status: 'active' | 'running' | 'completed' | 'failed' | 'skipped';
  nextRun?: number | null;
  lastRun?: number | null;
  executionCount: number;
  maxExecutions?: number;
  completedAt?: number | null;
  createSession?: boolean;
  workingDirectory?: string;
  sourceSessionId?: string;
  num: number;
}

interface ScheduleState {
  tasks: Record<string, ScheduleTask>;
  nextNum: number;

  // Actions
  handleToolResult: (result: Record<string, unknown>) => void;
  toggleTask: (id: string) => void;
  deleteTask: (id: string) => void;
  getTaskList: () => ScheduleTask[];
}

// Active timers (not in store — side-effect refs)
const activeTimers: Record<string, ReturnType<typeof setTimeout>> = {};

function stopTimer(id: string) {
  if (activeTimers[id]) {
    clearTimeout(activeTimers[id]);
    delete activeTimers[id];
  }
}

// ---------------------------------------------------------------------------
// Execute scheduled task — create a new session and send prompt (like legacy)
// ---------------------------------------------------------------------------

async function executeTask(taskId: string) {
  const state = useScheduleStore.getState();
  const task = state.tasks[taskId];
  if (!task) return;

  const sourceSessionId = task.sourceSessionId;
  if (!sourceSessionId) {
    console.warn(`[Scheduler] Task ${taskId} has no sourceSessionId, skipping`);
    return;
  }

  console.log(`[Scheduler] Executing task ${taskId}: ${task.name} -> session ${sourceSessionId}`);

  // Mark running
  useScheduleStore.setState((s) => ({
    tasks: {
      ...s.tasks,
      [taskId]: { ...s.tasks[taskId], status: 'running' as const, lastRun: Date.now() },
    },
  }));

  try {
    // Use a disposable session_id for the API call (not visible to user)
    const tempSessionId = `sched_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    const settings = useSettingsStore.getState();
    const model = settings.getEffectiveModel();

    // Send the prompt to backend via messages-auto (non-streaming)
    const res = await fetch('http://127.0.0.1:8081/v1/messages-auto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: task.prompt }],
        max_tokens: settings.settings.maxTokens || 4096,
        temperature: settings.settings.temperature || 0.7,
        stream: false,
        session_id: tempSessionId,
        compact_model: settings.getEffectiveCompactModel(),
        extended_context: settings.settings.enable1mContext !== false,
      }),
    });

    let success = res.ok;
    let assistantText = '';

    if (success) {
      try {
        const data = await res.json();
        // Extract text from response content blocks
        const content = data.content || [];
        for (const block of content) {
          if (block.type === 'text' && block.text) {
            assistantText += block.text;
          }
        }
        if (!assistantText) {
          // Fallback: try top-level text field
          assistantText = data.text || data.message || '';
        }
      } catch (e) {
        console.warn(`[Scheduler] Failed to parse response for task ${taskId}:`, e);
      }
    } else {
      const errorData = await res.text().catch(() => 'Unknown error');
      console.warn(`[Scheduler] Task ${taskId} failed:`, errorData);
      assistantText = `Scheduled task failed: ${errorData}`;
    }

    // Inject messages into the source session's chat runtime
    const chatStore = useChatStore.getState();
    const userContent = `[Scheduled: ${task.name}] ${task.prompt}`;

    chatStore.addMessage(sourceSessionId, {
      role: 'user',
      content: userContent,
      timestamp: Date.now(),
    });

    if (assistantText) {
      chatStore.addMessage(sourceSessionId, {
        role: 'assistant',
        content: assistantText,
        timestamp: Date.now(),
      });
    }

    // Update the session's updatedAt in the sidebar
    useSessionStore.setState((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.id === sourceSessionId
          ? { ...sess, updatedAt: Date.now() }
          : sess,
      ),
    }));

    // Persist: load existing backend messages, append new ones, save back
    try {
      const sessionRes = await fetch(`http://127.0.0.1:8081/v1/sessions/${sourceSessionId}`);
      if (sessionRes.ok) {
        const sessionData = await sessionRes.json();
        const existingMessages = sessionData.messages || [];

        existingMessages.push({ role: 'user', content: userContent });
        if (assistantText) {
          existingMessages.push({
            role: 'assistant',
            content: [{ type: 'text', text: assistantText }],
          });
        }

        await fetch(`http://127.0.0.1:8081/v1/sessions/${sourceSessionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: existingMessages,
            metadata: sessionData.metadata || {},
          }),
        });
        console.log(`[Scheduler] Task output persisted to session ${sourceSessionId}`);
      }
    } catch (e) {
      console.warn(`[Scheduler] Failed to persist task output to session:`, e);
    }

    // Update task status
    useScheduleStore.setState((s) => {
      const t = { ...s.tasks[taskId] };
      t.executionCount = (t.executionCount || 0) + 1;

      if (t.scheduleType === 'cron') {
        const shouldTerminate =
          t.maxExecutions && t.executionCount >= t.maxExecutions;
        if (shouldTerminate) {
          t.status = 'completed';
          t.completedAt = Date.now();
          stopTimer(taskId);
        } else {
          t.status = success ? 'active' : 'failed';
        }
      } else {
        t.status = success ? 'completed' : 'failed';
        t.completedAt = Date.now();
      }

      return { tasks: { ...s.tasks, [taskId]: t } };
    });
  } catch (err) {
    console.error(`[Scheduler] Task ${taskId} error:`, err);
    useScheduleStore.setState((s) => ({
      tasks: {
        ...s.tasks,
        [taskId]: { ...s.tasks[taskId], status: 'failed' as const, completedAt: Date.now() },
      },
    }));
  }
}

// ---------------------------------------------------------------------------
// Start timer for a task
// ---------------------------------------------------------------------------

function startTimer(task: ScheduleTask) {
  stopTimer(task.id);
  if (!task.enabled) return;

  const now = Date.now();

  if (task.scheduleType === 'delay') {
    const minutes = parseInt(task.scheduleValue);
    if (isNaN(minutes) || minutes <= 0) return;
    const triggerAt = task.nextRun || (now + minutes * 60_000);
    const delay = Math.max(0, triggerAt - now);
    activeTimers[task.id] = setTimeout(() => executeTask(task.id), delay);

    // Update nextRun in store
    useScheduleStore.setState((s) => ({
      tasks: {
        ...s.tasks,
        [task.id]: { ...s.tasks[task.id], nextRun: triggerAt },
      },
    }));
  } else if (task.scheduleType === 'once') {
    const targetTime = new Date(task.scheduleValue).getTime();
    if (isNaN(targetTime)) return;
    const delay = Math.max(0, targetTime - now);
    activeTimers[task.id] = setTimeout(() => executeTask(task.id), delay);

    useScheduleStore.setState((s) => ({
      tasks: {
        ...s.tasks,
        [task.id]: { ...s.tasks[task.id], nextRun: targetTime },
      },
    }));
  } else if (task.scheduleType === 'cron') {
    // For cron, use interval approximation (parse minute field)
    // Full cron support would require croner library — use simple repeat for now
    const parts = task.scheduleValue.trim().split(/\s+/);
    if (parts.length < 5) return;

    const minuteField = parts[0];
    let intervalMs: number;

    if (minuteField.startsWith('*/')) {
      intervalMs = parseInt(minuteField.slice(2)) * 60_000;
    } else {
      // Default: check every minute and match
      intervalMs = 60_000;
    }

    const tick = () => {
      executeTask(task.id);
      // Re-schedule if still active
      const t = useScheduleStore.getState().tasks[task.id];
      if (t && t.enabled && t.status === 'active') {
        activeTimers[task.id] = setTimeout(tick, intervalMs);
        useScheduleStore.setState((s) => ({
          tasks: {
            ...s.tasks,
            [task.id]: { ...s.tasks[task.id], nextRun: Date.now() + intervalMs },
          },
        }));
      }
    };

    activeTimers[task.id] = setTimeout(tick, intervalMs);
    useScheduleStore.setState((s) => ({
      tasks: {
        ...s.tasks,
        [task.id]: { ...s.tasks[task.id], nextRun: now + intervalMs },
      },
    }));
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useScheduleStore = create<ScheduleState>((set, get) => ({
  tasks: {},
  nextNum: 1,

  handleToolResult: (result) => {
    if (!result.success) return;

    const action = result.action as string | undefined;

    if (action === 'cancel' && result.task_id) {
      // Cancel / delete a task
      const id = String(result.task_id);
      stopTimer(id);
      set((s) => {
        const copy = { ...s.tasks };
        delete copy[id];
        return { tasks: copy };
      });
    } else if (action === 'update' && result.task_id && result.updates) {
      const id = String(result.task_id);
      const updates = result.updates as Partial<ScheduleTask>;
      set((s) => {
        const existing = s.tasks[id];
        if (!existing) return s;
        return {
          tasks: { ...s.tasks, [id]: { ...existing, ...updates } },
        };
      });
    } else if (result.task) {
      // Create new task — record the current session so output goes there
      const raw = result.task as Record<string, unknown>;
      const num = get().nextNum;
      const currentSessionId = useSessionStore.getState().currentSessionId || '';
      const task: ScheduleTask = {
        id: (raw.id as string) || `sched_${Date.now()}`,
        name: (raw.name as string) || 'Untitled',
        prompt: (raw.prompt as string) || '',
        scheduleType: (raw.scheduleType as ScheduleTask['scheduleType']) || 'delay',
        scheduleValue: String(raw.scheduleValue || '60'),
        enabled: raw.enabled !== false,
        status: 'active',
        nextRun: (raw.nextRun as number) || null,
        lastRun: null,
        executionCount: 0,
        maxExecutions: (raw.maxExecutions as number) || undefined,
        createSession: (raw.createSession as boolean) || true,
        workingDirectory: (raw.workingDirectory as string) || '',
        sourceSessionId: currentSessionId,
        num,
      };

      set((s) => ({
        tasks: { ...s.tasks, [task.id]: task },
        nextNum: s.nextNum + 1,
      }));

      // Start the timer
      startTimer(task);
    }
  },

  toggleTask: (id) => {
    set((s) => {
      const task = s.tasks[id];
      if (!task) return s;
      const updated = { ...task, enabled: !task.enabled };
      if (updated.enabled) {
        startTimer(updated);
      } else {
        stopTimer(id);
      }
      return { tasks: { ...s.tasks, [id]: updated } };
    });
  },

  deleteTask: (id) => {
    stopTimer(id);
    set((s) => {
      const copy = { ...s.tasks };
      delete copy[id];
      return { tasks: copy };
    });
  },

  getTaskList: () => {
    return Object.values(get().tasks).sort((a, b) => a.num - b.num);
  },
}));
