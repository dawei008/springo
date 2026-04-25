import { create } from 'zustand';
import { Cron } from 'croner';
import { useSessionStore } from '@/stores/sessionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';

const BASE_URL = 'http://127.0.0.1:8081';

// ---------------------------------------------------------------------------
// Schedule Task types (ported from legacy scheduler engine)
// ---------------------------------------------------------------------------

export interface ExecutionRecord {
  timestamp: number;
  success: boolean;
  outputPreview: string;
}

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
  executionHistory?: ExecutionRecord[];
  num: number;
}

interface ScheduleState {
  tasks: Record<string, ScheduleTask>;
  nextNum: number;
  loaded: boolean;

  // Actions
  loadTasks: () => Promise<void>;
  handleToolResult: (result: Record<string, unknown>, sessionId?: string) => void;
  toggleTask: (id: string) => void;
  deleteTask: (id: string) => void;
  getTaskList: () => ScheduleTask[];
}

// Active timers (not in store — side-effect refs)
const activeTimers: Record<string, ReturnType<typeof setTimeout>> = {};
// Active Cron instances (for proper cron scheduling)
const activeCrons: Record<string, Cron> = {};

function stopTimer(id: string) {
  if (activeCrons[id]) {
    activeCrons[id].stop();
    delete activeCrons[id];
  }
  if (activeTimers[id]) {
    clearTimeout(activeTimers[id]);
    delete activeTimers[id];
  }
}

// ---------------------------------------------------------------------------
// Backend persistence helpers
// ---------------------------------------------------------------------------

async function persistTask(task: ScheduleTask) {
  try {
    await fetch(`${BASE_URL}/v1/schedules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    });
  } catch (e) {
    console.warn('[Scheduler] Failed to persist task:', e);
  }
}

async function persistTaskUpdate(taskId: string, updates: Partial<ScheduleTask>) {
  try {
    await fetch(`${BASE_URL}/v1/schedules/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
  } catch (e) {
    console.warn('[Scheduler] Failed to persist task update:', e);
  }
}

async function persistTaskDelete(taskId: string) {
  try {
    await fetch(`${BASE_URL}/v1/schedules/${taskId}`, { method: 'DELETE' });
  } catch (e) {
    console.warn('[Scheduler] Failed to persist task delete:', e);
  }
}

// ---------------------------------------------------------------------------
// Extract assistant text from API response
// ---------------------------------------------------------------------------

function extractAssistantText(data: Record<string, unknown>): string {
  const content = data.content || [];
  if (Array.isArray(content)) {
    for (const block of content) {
      if (block.type === 'text' && block.text) {
        return block.text;
      }
    }
  }

  // Fallback: try top-level text field
  return String(data.text || data.message || '');
}

// ---------------------------------------------------------------------------
// Build prompt with schedule context so the model knows it can signal completion
// ---------------------------------------------------------------------------

function buildSchedulePrompt(task: ScheduleTask): string {
  // For one-shot tasks (delay/once), no completion signal needed
  if (task.scheduleType !== 'cron') {
    return task.prompt;
  }

  const runNum = (task.executionCount || 0) + 1;
  const maxInfo = task.maxExecutions ? ` of ${task.maxExecutions}` : '';

  const header = [
    `[Scheduled Task Context]`,
    `Task: "${task.name}" (#${task.num})`,
    `Type: ${task.scheduleType} (${task.scheduleValue}), Run: ${runNum}${maxInfo}`,
    ``,
    `If the task's purpose has been fulfilled, the condition is already met, ` +
    `or this task is no longer needed, include the marker [SCHEDULE_COMPLETE] ` +
    `at the end of your response. This will automatically disable the recurring task.`,
    `---`,
  ].join('\n');

  return `${header}\n${task.prompt}`;
}

// ---------------------------------------------------------------------------
// Execute scheduled task — create a new session and send prompt (like legacy)
// ---------------------------------------------------------------------------

async function executeTask(taskId: string) {
  const state = useScheduleStore.getState();
  const task = state.tasks[taskId];
  if (!task) return;

  // Concurrency lock: skip if previous execution is still running
  if (task.status === 'running') {
    console.log(`[Scheduler] Task ${taskId} still running, skipping this tick`);
    return;
  }

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
  persistTaskUpdate(taskId, { status: 'running', lastRun: Date.now() });

  try {
    const settings = useSettingsStore.getState();
    const model = settings.getEffectiveModel();

    // Send the prompt to backend via messages-auto (non-streaming)
    // Do NOT pass session_id — we don't want the backend to create a new session.
    // The result will be injected into sourceSessionId below.
    const res = await fetch(`${BASE_URL}/v1/messages-auto`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: buildSchedulePrompt(task) }],
        max_tokens: settings.settings.maxTokens || 4096,
        temperature: settings.settings.temperature || 0.7,
        stream: false,
        compact_model: settings.getEffectiveCompactModel(),
        working_directory: task.workingDirectory || undefined,
      }),
    });

    const success = res.ok;
    let assistantText = '';

    if (success) {
      try {
        const data = await res.json();
        assistantText = extractAssistantText(data);
      } catch (e) {
        console.warn(`[Scheduler] Failed to parse response for task ${taskId}:`, e);
      }
    } else {
      const errorData = await res.text().catch(() => 'Unknown error');
      console.warn(`[Scheduler] Task ${taskId} failed:`, errorData);
      assistantText = `Scheduled task failed: ${errorData}`;
    }

    // Detect [SCHEDULE_COMPLETE] signal at end of line/response (avoid false positives)
    const scheduleComplete = /\[SCHEDULE_COMPLETE\]\s*$/m.test(assistantText);
    if (scheduleComplete) {
      assistantText = assistantText.replace(/\s*\[SCHEDULE_COMPLETE\]\s*$/mg, '').trimEnd();
      console.log(`[Scheduler] Task ${taskId} signaled SCHEDULE_COMPLETE by model`);
    }

    // Inject messages into the source session's chat runtime
    // Use compact format: task name + short prompt preview (full prompt is stored in the task)
    const chatStore = useChatStore.getState();
    const runNum = (task.executionCount || 0) + 1;
    const promptPreview = task.prompt.length > 100
      ? task.prompt.slice(0, 100).replace(/\n/g, ' ') + '...'
      : task.prompt.replace(/\n/g, ' ');
    let userContent = `⏰ **Scheduled: ${task.name}** (#${task.num}, run ${runNum}${task.maxExecutions ? '/' + task.maxExecutions : ''})`;
    if (scheduleComplete) {
      userContent += `\n✅ Task auto-completed: condition fulfilled`;
    }
    userContent += `\n> ${promptPreview}`;

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
      const sessionRes = await fetch(`${BASE_URL}/v1/sessions/${sourceSessionId}`);
      if (!sessionRes.ok) {
        throw new Error(`Session fetch failed: ${sessionRes.status}`);
      }

      const sessionData = await sessionRes.json();
      const existingMessages = sessionData.messages || [];

      existingMessages.push({ role: 'user', content: userContent });

      if (assistantText) {
        existingMessages.push({
          role: 'assistant',
          content: [{ type: 'text', text: assistantText }],
        });
      }

      await fetch(`${BASE_URL}/v1/sessions/${sourceSessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: existingMessages,
          metadata: sessionData.metadata || {},
        }),
      });

      console.log(`[Scheduler] Task output persisted to session ${sourceSessionId}`);
    } catch (e) {
      console.warn(`[Scheduler] Failed to persist task output to session:`, e);
    }

    // Record execution history
    const record: ExecutionRecord = {
      timestamp: Date.now(),
      success,
      outputPreview: assistantText.slice(0, 200),
    };

    // Update task status
    useScheduleStore.setState((s) => {
      const t = { ...s.tasks[taskId] };
      t.executionCount = (t.executionCount || 0) + 1;
      t.executionHistory = [...(t.executionHistory || []), record].slice(-20); // keep last 20

      const isMaxReached = t.maxExecutions && t.executionCount >= t.maxExecutions;

      if (t.scheduleType === 'cron' && (isMaxReached || scheduleComplete)) {
        t.status = 'completed';
        t.completedAt = Date.now();
        stopTimer(taskId);
      } else if (t.scheduleType === 'cron') {
        t.status = success ? 'active' : 'failed';
      } else {
        t.status = success ? 'completed' : 'failed';
        t.completedAt = Date.now();
      }

      // Persist updated status to backend
      persistTaskUpdate(taskId, {
        status: t.status,
        executionCount: t.executionCount,
        lastRun: t.lastRun,
        completedAt: t.completedAt,
        executionHistory: t.executionHistory,
      });

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
    persistTaskUpdate(taskId, { status: 'failed', completedAt: Date.now() });
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
    // Use croner for full cron expression support
    try {
      const job = new Cron(task.scheduleValue, { paused: true }, () => {
        const t = useScheduleStore.getState().tasks[task.id];
        if (!t || !t.enabled) {
          job.stop();
          delete activeCrons[task.id];
          return;
        }
        executeTask(task.id);
        // Update nextRun after execution
        const nextDate = job.nextRun();
        if (nextDate) {
          useScheduleStore.setState((s) => ({
            tasks: {
              ...s.tasks,
              [task.id]: { ...s.tasks[task.id], nextRun: nextDate.getTime() },
            },
          }));
        }
      });

      activeCrons[task.id] = job;
      job.resume();

      // Set initial nextRun
      const nextDate = job.nextRun();
      if (nextDate) {
        useScheduleStore.setState((s) => ({
          tasks: {
            ...s.tasks,
            [task.id]: { ...s.tasks[task.id], nextRun: nextDate.getTime() },
          },
        }));
      }
    } catch (e) {
      console.error(`[Scheduler] Invalid cron expression "${task.scheduleValue}":`, e);
    }
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useScheduleStore = create<ScheduleState>((set, get) => ({
  tasks: {},
  nextNum: 1,
  loaded: false,

  loadTasks: async () => {
    try {
      const res = await fetch(`${BASE_URL}/v1/schedules`);
      if (!res.ok) return;
      const data = await res.json();
      const taskList = (data.tasks || []) as ScheduleTask[];
      if (taskList.length === 0) {
        set({ loaded: true });
        return;
      }

      const tasks: Record<string, ScheduleTask> = {};
      let maxNum = 0;
      for (const t of taskList) {
        tasks[t.id] = t;
        if (t.num > maxNum) maxNum = t.num;
      }

      set({ tasks, nextNum: maxNum + 1, loaded: true });

      // Restart timers for active tasks
      for (const t of taskList) {
        if (t.enabled && (t.status === 'active' || t.status === 'running')) {
          // Reset running tasks back to active (stale from previous session)
          if (t.status === 'running') {
            tasks[t.id] = { ...t, status: 'active' };
            set((s) => ({
              tasks: { ...s.tasks, [t.id]: { ...s.tasks[t.id], status: 'active' } },
            }));
          }
          startTimer(tasks[t.id]);
        }
      }

      console.log(`[Scheduler] Restored ${taskList.length} tasks from backend`);
    } catch (e) {
      console.warn('[Scheduler] Failed to load tasks from backend:', e);
      set({ loaded: true });
    }
  },

  handleToolResult: (result, sessionId?) => {
    if (!result.success) {
      return;
    }

    const action = result.action as string | undefined;

    if (action === 'cancel' && result.task_id) {
      const id = String(result.task_id);
      stopTimer(id);
      set((s) => {
        const copy = { ...s.tasks };
        delete copy[id];
        return { tasks: copy };
      });
      persistTaskDelete(id);
      return;
    }

    if (action === 'update' && result.task_id && result.updates) {
      const id = String(result.task_id);
      const updates = result.updates as Partial<ScheduleTask>;
      set((s) => {
        const existing = s.tasks[id];
        if (!existing) return s;
        const updated = { ...existing, ...updates };
        persistTask(updated);
        return {
          tasks: { ...s.tasks, [id]: updated },
        };
      });
      return;
    }

    if (result.task) {
      const raw = result.task as Record<string, unknown>;
      const num = get().nextNum;
      // Use the sessionId from the streaming context (the conversation that created this task),
      // NOT currentSessionId which could be a different session the user is viewing.
      const ownerSessionId = sessionId || useSessionStore.getState().currentSessionId || '';

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
        sourceSessionId: ownerSessionId,
        num,
      };

      set((s) => ({
        tasks: { ...s.tasks, [task.id]: task },
        nextNum: s.nextNum + 1,
      }));

      persistTask(task);
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
      persistTaskUpdate(id, { enabled: updated.enabled });
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
    persistTaskDelete(id);
  },

  getTaskList: () => {
    return Object.values(get().tasks).sort((a, b) => a.num - b.num);
  },
}));
