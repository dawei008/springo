import { useState, useEffect, useRef, useMemo } from 'react';
import { useScheduleStore } from '@/stores/scheduleStore';
import type { ScheduleTask } from '@/stores/scheduleStore';

// ─── Helper Functions ───

function describeCron(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length < 5) return cron;

  const [minute, hour, dayOfMonth, , dayOfWeek] = parts;

  if (minute.startsWith('*/') && hour === '*') {
    const n = minute.slice(2);
    return `Every ${n} minute${n === '1' ? '' : 's'}`;
  }

  const hStr = hour !== '*' ? hour.padStart(2, '0') : null;
  const mStr = minute !== '*' ? minute.padStart(2, '0') : '00';

  if (hour === '*' && minute !== '*' && !minute.startsWith('*/')) {
    return `Every hour at :${mStr}`;
  }

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  if (dayOfWeek !== '*' && dayOfMonth === '*' && hStr) {
    const dayIdx = parseInt(dayOfWeek, 10);
    const dayName = dayNames[dayIdx] || dayOfWeek;
    return `Every ${dayName} at ${hStr}:${mStr}`;
  }

  if (dayOfMonth !== '*' && dayOfWeek === '*' && hStr) {
    return `Monthly on day ${dayOfMonth} at ${hStr}:${mStr}`;
  }

  if (hStr && dayOfMonth === '*' && dayOfWeek === '*') {
    return `Daily at ${hStr}:${mStr}`;
  }

  return cron;
}

function formatNextRun(nextRun: number | null | undefined): string {
  if (!nextRun) return '';
  const diffMs = nextRun - Date.now();

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

function isToday(timestamp: number | null | undefined): boolean {
  if (!timestamp) return false;
  const d = new Date(timestamp);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function formatTime(timestamp: number | null | undefined): string {
  if (!timestamp) return '';
  const d = new Date(timestamp);
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
  if (status === 'running') {
    return (
      <svg className="schedule-status-icon spinning" width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6" stroke="var(--info)" strokeWidth="2" strokeDasharray="28" strokeDashoffset="7" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === 'completed') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 8.5L6.5 12L13 4" />
      </svg>
    );
  }
  if (status === 'failed') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--error)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4L12 12M12 4L4 12" />
      </svg>
    );
  }
  if (status === 'skipped') {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text-tertiary)" strokeWidth="2" strokeLinecap="round">
        <path d="M4 8H12" />
      </svg>
    );
  }
  if (enabled) {
    return (
      <svg className="schedule-status-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="8" cy="8" r="6" />
        <path d="M8 4.5V8L10.5 9.5" />
      </svg>
    );
  }
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
  const tasksMap = useScheduleStore((s) => s.tasks);
  const toggleTask = useScheduleStore((s) => s.toggleTask);
  const deleteTask = useScheduleStore((s) => s.deleteTask);
  const tasks = useMemo(
    () => Object.values(tasksMap).sort((a, b) => a.num - b.num),
    [tasksMap],
  );

  const [olderCollapsed, setOlderCollapsed] = useState(true);
  const [, setTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Refresh relative times every 60s
  useEffect(() => {
    intervalRef.current = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const headerIcon = (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8L10.5 9.5" />
    </svg>
  );

  if (tasks.length === 0) {
    return (
      <div className="schedules-panel">
        <div className="schedules-panel-header">
          {headerIcon}
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

  // Group tasks into "Today" and "Older"
  const todayTasks: ScheduleTask[] = [];
  const olderTasks: ScheduleTask[] = [];

  for (const task of tasks) {
    const relevantDate = task.completedAt || task.nextRun;
    if (isToday(relevantDate)) {
      todayTasks.push(task);
    } else {
      olderTasks.push(task);
    }
  }

  return (
    <div className="schedules-panel">
      <div className="schedules-panel-header">
        {headerIcon}
        <span className="schedules-panel-title">Schedules</span>
        <span className="schedules-panel-badge">{tasks.length}</span>
      </div>

      <div className="schedules-panel-body">
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
                onToggle={toggleTask}
                onDelete={deleteTask}
              />
            ))}
          </div>
        )}

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
                onToggle={toggleTask}
                onDelete={deleteTask}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
