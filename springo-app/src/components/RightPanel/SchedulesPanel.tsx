import { useState, useEffect, useCallback, useRef } from 'react';

// ─── Schedule Task Interface ───

interface ScheduleTask {
  id: string;
  name: string;
  scheduleType: 'cron' | 'delay' | 'once';
  scheduleValue: string;
  enabled: boolean;
  status: 'running' | 'completed' | 'failed' | 'skipped' | 'active';
  nextRun?: string | number | null;
  lastRun?: string | number | null;
  executionCount: number;
  maxExecutions?: number;
  completedAt?: string | number | null;
  num: number;
  output?: string;
}

// ─── Helper Functions ───

function describeCron(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length < 5) return cron;

  const [minute, hour, dayOfMonth, , dayOfWeek] = parts;

  // Every N minutes: */N * * * *
  if (minute.startsWith('*/') && hour === '*') {
    const n = minute.slice(2);
    return `Every ${n} minute${n === '1' ? '' : 's'}`;
  }

  // Specific time patterns
  const hStr = hour !== '*' ? hour.padStart(2, '0') : null;
  const mStr = minute !== '*' ? minute.padStart(2, '0') : '00';

  // Every hour at :MM
  if (hour === '*' && minute !== '*' && !minute.startsWith('*/')) {
    return `Every hour at :${mStr}`;
  }

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  // Weekly: specific day of week
  if (dayOfWeek !== '*' && dayOfMonth === '*' && hStr) {
    const dayIdx = parseInt(dayOfWeek, 10);
    const dayName = dayNames[dayIdx] || dayOfWeek;
    return `Every ${dayName} at ${hStr}:${mStr}`;
  }

  // Monthly: specific day of month
  if (dayOfMonth !== '*' && dayOfWeek === '*' && hStr) {
    return `Monthly on day ${dayOfMonth} at ${hStr}:${mStr}`;
  }

  // Daily at HH:MM
  if (hStr && dayOfMonth === '*' && dayOfWeek === '*') {
    return `Daily at ${hStr}:${mStr}`;
  }

  return cron;
}

function formatNextRun(nextRun: string | number | null | undefined): string {
  if (!nextRun) return '';
  const target = new Date(nextRun);
  const now = new Date();
  const diffMs = target.getTime() - now.getTime();

  if (diffMs < 0) return 'Overdue';

  const totalMinutes = Math.floor(diffMs / 60000);
  if (totalMinutes < 1) return 'In <1m';
  if (totalMinutes < 60) return `In ${totalMinutes}m`;

  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  if (hours < 24) {
    return mins > 0 ? `In ${hours}h ${mins}m` : `In ${hours}h`;
  }

  const days = Math.floor(hours / 24);
  return `In ${days}d ${hours % 24}h`;
}

function formatScheduleDescription(task: ScheduleTask): string {
  switch (task.scheduleType) {
    case 'cron':
      return describeCron(task.scheduleValue);
    case 'delay': {
      const mins = parseInt(task.scheduleValue, 10);
      if (isNaN(mins)) return `After ${task.scheduleValue}`;
      if (mins < 60) return `After ${mins} minute${mins === 1 ? '' : 's'}`;
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return m > 0 ? `After ${h}h ${m}m` : `After ${h} hour${h === 1 ? '' : 's'}`;
    }
    case 'once': {
      const d = new Date(task.scheduleValue);
      if (isNaN(d.getTime())) return `Once at ${task.scheduleValue}`;
      return `Once at ${d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`;
    }
    default:
      return task.scheduleValue;
  }
}

function isToday(dateValue: string | number | null | undefined): boolean {
  if (!dateValue) return false;
  const d = new Date(dateValue);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function formatTime(dateValue: string | number | null | undefined): string {
  if (!dateValue) return '';
  const d = new Date(dateValue);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Status Icons (SVG) ───

function StatusIcon({ status, enabled }: { status: string; enabled: boolean }) {
  // Running: spinning circle
  if (status === 'running') {
    return (
      <svg className="schedule-status-icon spinning" width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6" stroke="var(--info)" strokeWidth="2" strokeDasharray="28" strokeDashoffset="7" strokeLinecap="round" />
      </svg>
    );
  }
  // Completed: checkmark
  if (status === 'completed') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 8.5L6.5 12L13 4" />
      </svg>
    );
  }
  // Failed: X mark
  if (status === 'failed') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--error)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4L12 12M12 4L4 12" />
      </svg>
    );
  }
  // Skipped: dash
  if (status === 'skipped') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text-tertiary)" strokeWidth="2" strokeLinecap="round">
        <path d="M4 8H12" />
      </svg>
    );
  }
  // Active/enabled: clock
  if (enabled) {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="8" cy="8" r="6" />
        <path d="M8 4.5V8L10.5 9.5" />
      </svg>
    );
  }
  // Disabled: calendar (dimmed)
  return (
    <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="12" height="11" rx="1.5" />
      <path d="M5 1.5V4M11 1.5V4M2 6.5H14" />
    </svg>
  );
}

// ─── Toggle Switch ───

function ToggleSwitch({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      className={`schedule-toggle${checked ? ' on' : ''}`}
      onClick={(e) => { e.stopPropagation(); onChange(); }}
      title={checked ? 'Disable' : 'Enable'}
    >
      <span className="schedule-toggle-thumb" />
    </button>
  );
}

// ─── Schedule Item ───

function ScheduleItem({
  task,
  onToggle,
  onDelete,
}: {
  task: ScheduleTask;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const isFinished = task.status === 'completed' || task.status === 'failed' || task.status === 'skipped';
  const scheduleDesc = formatScheduleDescription(task);

  // Determine secondary text: next-run or completed-at
  let secondaryText = '';
  if (isFinished && task.completedAt) {
    secondaryText = formatTime(task.completedAt);
  } else if (task.nextRun) {
    secondaryText = formatNextRun(task.nextRun);
  }

  return (
    <div className={`schedule-item${!task.enabled && !isFinished ? ' disabled' : ''}${isFinished ? ' finished' : ''}`}>
      <StatusIcon status={task.status} enabled={task.enabled} />

      <div className="schedule-item-body">
        <div className="schedule-item-top">
          <span className="schedule-item-num">#{task.num}</span>
          <span className="schedule-item-name" title={task.name}>{task.name}</span>
          {task.scheduleType === 'cron' && task.maxExecutions && (
            <span className="schedule-item-count">{task.executionCount}/{task.maxExecutions}</span>
          )}
        </div>
        <div className="schedule-item-bottom">
          <span className="schedule-item-desc">{scheduleDesc}</span>
          {secondaryText && (
            <span className={`schedule-item-time${secondaryText === 'Overdue' ? ' overdue' : ''}`}>
              {secondaryText}
            </span>
          )}
        </div>
      </div>

      <div className="schedule-item-actions">
        {isFinished ? (
          <span className={`schedule-status-badge ${task.status}`}>
            {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
          </span>
        ) : (
          <ToggleSwitch checked={task.enabled} onChange={() => onToggle(task.id)} />
        )}
        <button
          className="schedule-delete-btn"
          onClick={(e) => { e.stopPropagation(); onDelete(task.id); }}
          title="Delete task"
        >
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M2 2l8 8M10 2l-8 8" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ─── Main Component ───

export default function SchedulesPanel() {
  const [tasks, setTasks] = useState<ScheduleTask[]>([]);
  const [olderCollapsed, setOlderCollapsed] = useState(true);
  const [, setTick] = useState(0); // force re-render for relative times
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load tasks from Electron IPC
  const loadTasks = useCallback(async () => {
    try {
      const result = await (window as any).electronAPI?.schedules?.getAll?.();
      if (Array.isArray(result)) {
        setTasks(result);
      }
    } catch (err) {
      console.error('Failed to load schedules:', err);
    }
  }, []);

  useEffect(() => {
    // Check if electronAPI is available
    if (!(window as any).electronAPI?.schedules?.getAll) return;

    loadTasks();

    // Refresh every 60 seconds for next-run times
    intervalRef.current = setInterval(() => {
      loadTasks();
      setTick((t) => t + 1);
    }, 60_000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [loadTasks]);

  // Toggle enable/disable
  const handleToggle = useCallback(async (taskId: string) => {
    try {
      await (window as any).electronAPI?.schedules?.toggle?.(taskId);
      loadTasks();
    } catch (err) {
      console.error('Failed to toggle schedule:', err);
    }
  }, [loadTasks]);

  // Delete task
  const handleDelete = useCallback(async (taskId: string) => {
    try {
      await (window as any).electronAPI?.schedules?.delete?.(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } catch (err) {
      console.error('Failed to delete schedule:', err);
    }
  }, []);

  // If electronAPI is not available, show placeholder
  if (!(window as any).electronAPI?.schedules) {
    return (
      <div className="schedules-panel">
        <div className="schedules-panel-header">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="8" r="6" />
            <path d="M8 4.5V8L10.5 9.5" />
          </svg>
          <span className="schedules-panel-title">Schedules</span>
        </div>
        <div className="schedules-panel-empty">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.5">
            <circle cx="16" cy="16" r="12" />
            <path d="M16 9V16L20 19" />
          </svg>
          <p>Schedule features require the desktop app.</p>
        </div>
      </div>
    );
  }

  // Group tasks into "Today" and "Older"
  const todayTasks: ScheduleTask[] = [];
  const olderTasks: ScheduleTask[] = [];

  for (const task of tasks) {
    const relevantDate = task.completedAt || task.nextRun;
    if (isToday(relevantDate as string | number | null | undefined)) {
      todayTasks.push(task);
    } else {
      olderTasks.push(task);
    }
  }

  if (tasks.length === 0) {
    return (
      <div className="schedules-panel">
        <div className="schedules-panel-header">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="8" r="6" />
            <path d="M8 4.5V8L10.5 9.5" />
          </svg>
          <span className="schedules-panel-title">Schedules</span>
        </div>
        <div className="schedules-panel-empty">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.5">
            <circle cx="16" cy="16" r="12" />
            <path d="M16 9V16L20 19" />
          </svg>
          <p>No scheduled tasks yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="schedules-panel">
      <div className="schedules-panel-header">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="8" cy="8" r="6" />
          <path d="M8 4.5V8L10.5 9.5" />
        </svg>
        <span className="schedules-panel-title">Schedules</span>
        <span className="schedules-panel-badge">{tasks.length}</span>
      </div>

      <div className="schedules-panel-body">
        {/* Today's tasks */}
        {todayTasks.length > 0 && (
          <div className="schedules-group">
            <div className="schedules-group-header">
              <span className="schedules-group-label">Today's tasks</span>
              <span className="schedules-group-count">{todayTasks.length}</span>
            </div>
            {todayTasks.map((task) => (
              <ScheduleItem
                key={task.id}
                task={task}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

        {/* Older tasks (collapsible) */}
        {olderTasks.length > 0 && (
          <div className={`schedules-group${olderCollapsed ? ' collapsed' : ''}`}>
            <div
              className="schedules-group-header clickable"
              onClick={() => setOlderCollapsed((p) => !p)}
            >
              <svg
                className="schedules-group-chevron"
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 1.5L7 5L3 8.5" />
              </svg>
              <span className="schedules-group-label">Older</span>
              <span className="schedules-group-count">{olderTasks.length}</span>
            </div>
            {!olderCollapsed && olderTasks.map((task) => (
              <ScheduleItem
                key={task.id}
                task={task}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
