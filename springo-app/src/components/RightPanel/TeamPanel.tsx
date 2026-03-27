import { useRef, useEffect, useCallback, useMemo, useState } from 'react';
import { useTeamStore, getRoleConfig, type AgentStatus, type StoreAgent, type StoreMessage } from '@/stores/teamStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useUIStore } from '@/stores/uiStore';

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

// ─── Agent Card (collapsed by default, click header to expand) ───

function AgentCard({ agent }: { agent: StoreAgent }) {
  const [expanded, setExpanded] = useState(false);
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

  // Auto-scroll output to bottom when expanded and active
  useEffect(() => {
    if (outputRef.current && expanded && isActive) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [truncatedOutput, isActive, expanded]);

  const outputClass = isTerminal
    ? `team-split-agent-output ${agent.status === 'complete' ? 'success' : 'error'}`
    : 'team-split-agent-output';

  const displayName = agent.name && agent.name !== agent.role
    ? `${roleConfig.label} (${agent.name})`
    : roleConfig.label;

  return (
    <div
      className={`team-split-agent-card${isActive ? ' active' : ''}`}
      style={{ '--agent-color': roleConfig.color } as React.CSSProperties}
    >
      <div
        className="team-split-agent-header"
        onClick={() => setExpanded((p) => !p)}
        style={{ cursor: 'pointer' }}
      >
        <svg
          className="team-agent-toggle"
          width="10" height="10" viewBox="0 0 24 24"
          fill="none" stroke="var(--text-tertiary)" strokeWidth="2"
          style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s', flexShrink: 0 }}
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={roleConfig.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={getRoleIconPath(agent.role)} />
        </svg>
        <span className="team-split-agent-role">{displayName}</span>
        <span className={`team-split-agent-badge ${badgeClass}`}>
          {getStatusLabel(agent.status)}
        </span>
      </div>

      {/* Collapsed: show purpose as one-liner */}
      {!expanded && agent.purpose && (
        <div className="team-split-agent-task" style={{ opacity: 0.6, fontSize: 11, marginBottom: 4 }}>{agent.purpose}</div>
      )}

      {/* Expanded: full content */}
      {expanded && (
        <>
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
        </>
      )}
    </div>
  );
}

// ─── Message Item ───

function MessageItem({ msg }: { msg: StoreMessage }) {
  const senderConfig = getRoleConfig(msg.sender);
  const displayContent = msg.summary || msg.content;
  const truncated = displayContent.length > 300
    ? displayContent.slice(0, 300) + '...'
    : displayContent;

  return (
    <div className={`team-split-message${msg.isBroadcast ? ' broadcast' : ''}`}>
      <div className="team-msg-header">
        <span style={{ color: senderConfig.color, fontWeight: 600 }}>{msg.sender}</span>
        {msg.isBroadcast ? (
          <span> -&gt; all</span>
        ) : (
          <span> -&gt; {msg.recipient}</span>
        )}
      </div>
      <div className="team-msg-content">{truncated}</div>
    </div>
  );
}

// ─── Team Messages Section ───

function TeamMessages({ messages }: { messages: StoreMessage[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(messages.length);

  // Auto-scroll on new messages — always scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    prevCountRef.current = messages.length;
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="team-split-messages-empty" style={{ padding: '12px 14px', fontSize: 11, opacity: 0.5 }}>
        Waiting for inter-agent messages...
      </div>
    );
  }

  return (
    <div className="team-split-messages" ref={scrollRef}>
      {messages.map((msg) => (
        <MessageItem key={msg.id} msg={msg} />
      ))}
    </div>
  );
}

// ─── Main Component ───

export default function TeamPanel() {
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const teamStatus = useTeamStore((s) => s.teamStatus);
  const userRequest = useTeamStore((s) => s.userRequest);
  const agents = useTeamStore((s) => s.agents);
  const messages = useTeamStore((s) => s.messages);

  // Divider drag state — start with agents taking most space; auto-adjust when messages arrive
  const [agentsFlex, setAgentsFlex] = useState(0.8);
  const hasAutoAdjusted = useRef(false);
  const dividerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleStop = useCallback(async () => {
    if (!activeTeamId) return;
    const convId = useSessionStore.getState().currentSessionId;

    // 1. Abort the SSE stream (stops the fetch in chatStore)
    if (convId) {
      useChatStore.getState().stopTask(convId);
    }

    // 2. Tell backend to shut down the team (best-effort)
    try {
      await fetch(`http://127.0.0.1:8081/v1/teams/${activeTeamId}/shutdown`, {
        method: 'POST',
      });
    } catch {
      // Ignore — stream is already aborted
    }

    // 3. Update team panel status
    useTeamStore.getState().setTeamComplete(activeTeamId);
  }, [activeTeamId]);

  const handleNewTeam = useCallback(async () => {
    if (!activeTeamId) return;
    const convId = useSessionStore.getState().currentSessionId;
    const running = teamStatus === 'planning' || teamStatus === 'executing' || teamStatus === 'synthesizing';

    // Stop current team if running
    if (running) {
      if (convId) useChatStore.getState().stopTask(convId);
      try {
        await fetch(`http://127.0.0.1:8081/v1/teams/${activeTeamId}/shutdown`, { method: 'POST' });
      } catch { /* ignore */ }
    }

    // Clear team state so next message spawns a new team
    useTeamStore.getState().resetTeam();
    if (convId) useUIStore.getState().setSessionTeam(convId, '');
  }, [activeTeamId, teamStatus]);

  // Divider drag handler
  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;

    const startY = e.clientY;
    const containerRect = container.getBoundingClientRect();
    const startFlex = agentsFlex;
    const divider = dividerRef.current;
    divider?.classList.add('dragging');

    const onMouseMove = (ev: MouseEvent) => {
      const delta = ev.clientY - startY;
      const totalHeight = containerRect.height;
      const newFlex = Math.min(0.85, Math.max(0.15, startFlex + delta / totalHeight));
      setAgentsFlex(newFlex);
    };

    const onMouseUp = () => {
      divider?.classList.remove('dragging');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [agentsFlex]);

  // Auto-expand messages section when first messages arrive
  useEffect(() => {
    if (messages.length > 0 && !hasAutoAdjusted.current) {
      hasAutoAdjusted.current = true;
      setAgentsFlex(0.5);
    }
  }, [messages.length]);

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
      <div className="team-split-content" ref={containerRef}>
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
            <button className="team-new-btn" onClick={handleNewTeam} title="Dismiss current team and start fresh">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 4v6h-6" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              New Team
            </button>
          </div>
        </div>

        {/* Agent Cards */}
        <div
          className="team-split-agents"
          style={{ flex: `${agentsFlex} 1 0`, maxHeight: 'none' }}
        >
          {agentList.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>

        {/* Draggable divider + Messages section — always visible */}
        <div
          ref={dividerRef}
          className="team-split-divider"
          onMouseDown={handleDividerMouseDown}
        />
        <div
          className="team-split-messages-section"
          style={{ flex: `${1 - agentsFlex} 1 0` }}
        >
          <div className="team-split-messages-title">Team Communication</div>
          <TeamMessages messages={messages} />
        </div>
      </div>
    </div>
  );
}
