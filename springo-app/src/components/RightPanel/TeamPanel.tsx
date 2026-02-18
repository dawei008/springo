import { useRef, useEffect, useCallback, useMemo } from 'react';
import { useTeamStore, getRoleConfig, type AgentStatus, type StoreAgent, type StoreTask } from '@/stores/teamStore';

// ─── Role SVG Paths ───

const ROLE_ICON_PATHS: Record<string, string> = {
  orchestrator: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z',
  explorer: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  researcher: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253',
  implementer: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
  reviewer: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  custom: 'M13 10V3L4 14h7v7l9-11h-7z',
};

function getRoleIconPath(role: string): string {
  return ROLE_ICON_PATHS[role] || ROLE_ICON_PATHS.custom;
}

// ─── Status Display Mapping ───

function getStatusBadgeClass(status: AgentStatus): string {
  switch (status) {
    case 'working': return 'thinking';
    case 'tool_calling': return 'executing';
    case 'complete': return 'complete';
    case 'error': return 'error';
    default: return 'idle';
  }
}

function getStatusLabel(status: AgentStatus): string {
  switch (status) {
    case 'working': return 'Thinking';
    case 'tool_calling': return 'Executing';
    case 'complete': return 'Complete';
    case 'error': return 'Error';
    default: return 'Idle';
  }
}

// ─── Constants ───

const MAX_OUTPUT_LEN = 50_000;

// ─── Agent Card ───

function AgentCard({ agent }: { agent: StoreAgent }) {
  const outputRef = useRef<HTMLDivElement>(null);
  const roleConfig = getRoleConfig(agent.role);
  const badgeClass = getStatusBadgeClass(agent.status);
  const isActive = agent.status === 'working' || agent.status === 'tool_calling';
  const isTerminal = agent.status === 'complete' || agent.status === 'error';

  const truncatedOutput = useMemo(() => {
    if (agent.output.length > MAX_OUTPUT_LEN) {
      return agent.output.slice(-MAX_OUTPUT_LEN);
    }
    return agent.output;
  }, [agent.output]);

  // Auto-scroll output to bottom
  useEffect(() => {
    if (outputRef.current && isActive) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [truncatedOutput, isActive]);

  const outputClass = isTerminal
    ? `team-split-agent-output ${agent.status === 'complete' ? 'success' : 'error'}`
    : 'team-split-agent-output';

  return (
    <div
      className={`team-split-agent-card${isActive ? ' active' : ''}`}
      style={{ '--agent-color': roleConfig.color } as React.CSSProperties}
    >
      <div className="team-split-agent-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={roleConfig.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={getRoleIconPath(agent.role)} />
        </svg>
        <span className="team-split-agent-role">{roleConfig.label}</span>
        <span className={`team-split-agent-badge ${badgeClass}`}>
          {getStatusLabel(agent.status)}
        </span>
      </div>

      {agent.purpose && (
        <div className="team-split-agent-task">{agent.purpose}</div>
      )}

      {truncatedOutput && (
        <div
          ref={outputRef}
          className={outputClass}
          style={{ display: 'block' }}
        >
          {truncatedOutput}
        </div>
      )}

      {isTerminal && agent.findings && (
        <div className={`team-agent-findings ${agent.status === 'complete' ? 'success' : 'error'}`}>
          {agent.findings}
        </div>
      )}

      <div className="team-split-agent-resize" />
    </div>
  );
}

// ─── Task Item ───

function TaskItem({ task }: { task: StoreTask }) {
  const roleConfig = task.owner ? getRoleConfig(task.owner) : null;

  // Map task status to dot class
  let dotClass = 'pending';
  if (task.status === 'in_progress') dotClass = 'in_progress';
  else if (task.status === 'completed') dotClass = 'complete';
  else if (task.status === 'error') dotClass = 'error';
  else if (task.status === 'unblocked') dotClass = 'pending';

  return (
    <div className={`team-task-item ${task.status}`}>
      <span className={`team-task-status-dot ${dotClass}`} />
      <span className="team-task-id">#{task.id}</span>
      <span className="team-task-title">{task.title}</span>
      {task.owner && roleConfig && (
        <span className="team-task-owner">{roleConfig.label}</span>
      )}
      <span className={`team-task-status ${task.status}`}>{task.status}</span>
    </div>
  );
}

// ─── Task Board ───

function TaskBoard({ tasks }: { tasks: Record<string, StoreTask> }) {
  const taskList = Object.values(tasks);
  if (taskList.length === 0) return null;

  return (
    <div className="team-task-board">
      <div className="team-task-board-title">Tasks</div>
      <div className="team-task-board-list">
        {taskList.map((task) => (
          <TaskItem key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}

// ─── Main Component ───

export default function TeamPanel() {
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const teamStatus = useTeamStore((s) => s.teamStatus);
  const userRequest = useTeamStore((s) => s.userRequest);
  const agents = useTeamStore((s) => s.agents);
  const tasks = useTeamStore((s) => s.tasks);

  const handleStop = useCallback(async () => {
    if (!activeTeamId) return;
    try {
      await fetch(`http://127.0.0.1:8081/v1/teams/${activeTeamId}/stop`, {
        method: 'POST',
      });
    } catch (err) {
      console.error('Failed to stop team:', err);
    }
  }, [activeTeamId]);

  // No active team — show placeholder
  if (!activeTeamId) {
    return (
      <div className="team-split-panel">
        <div className="team-split-placeholder">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.5">
            <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 00-3-3.87" />
            <path d="M16 3.13a4 4 0 010 7.75" />
          </svg>
          <p>No active team</p>
          <span style={{ fontSize: 11, opacity: 0.6 }}>
            Start a team task to see agent activity here
          </span>
        </div>
      </div>
    );
  }

  const agentList = Object.values(agents);
  const isRunning = teamStatus === 'planning' || teamStatus === 'executing' || teamStatus === 'synthesizing';

  return (
    <div className="team-split-panel">
      <div className="team-split-content">
        {/* Header */}
        <div className="team-split-header">
          <div className="team-split-status-row">
            <span className={`team-split-status-badge ${teamStatus}`}>
              {teamStatus.charAt(0).toUpperCase() + teamStatus.slice(1)}
            </span>
            {userRequest && (
              <span className="team-split-request-preview" title={userRequest}>
                {userRequest}
              </span>
            )}
            {isRunning && (
              <button className="team-stop-btn" onClick={handleStop}>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                  <rect x="1" y="1" width="8" height="8" rx="1" />
                </svg>
                Stop
              </button>
            )}
          </div>
        </div>

        {/* Agent Cards */}
        <div className="team-split-agents full-height">
          {agentList.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>

        {/* Task Board */}
        {Object.keys(tasks).length > 0 && (
          <div style={{ padding: '0 14px 14px', flexShrink: 0 }}>
            <TaskBoard tasks={tasks} />
          </div>
        )}
      </div>
    </div>
  );
}
