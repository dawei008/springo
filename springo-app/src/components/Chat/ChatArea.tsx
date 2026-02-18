import { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useTeamStore, type StoreTask } from '@/stores/teamStore';
import WelcomeScreen from './WelcomeScreen';
import MessageList from './MessageList';
import ToolPanel from './ToolPanel';
import { useUIStore } from '@/stores/uiStore';
import type { Message } from '@/types';

// ─── Inline Task Board (shown in main chat during team execution) ───

function TaskItem({ task }: { task: StoreTask }) {
  let dotClass = 'pending';
  if (task.status === 'in_progress') dotClass = 'in_progress';
  else if (task.status === 'completed') dotClass = 'complete';
  else if (task.status === 'error') dotClass = 'error';

  return (
    <div className={`team-task-item ${task.status}`}>
      <span className={`team-task-status-dot ${dotClass}`} />
      <span className="team-task-id">#{task.id}</span>
      <span className="team-task-title">{task.title}</span>
      {task.owner && (
        <span className="team-task-owner">{task.owner}</span>
      )}
      <span className={`team-task-status ${task.status}`}>{task.status}</span>
    </div>
  );
}

function ChatTaskBoard({ tasks }: { tasks: Record<string, StoreTask> }) {
  const [collapsed, setCollapsed] = useState(false);
  const teamStatus = useTeamStore((s) => s.teamStatus);

  // Auto-collapse when team completes
  const prevStatusRef = useRef(teamStatus);
  useEffect(() => {
    if (prevStatusRef.current !== 'complete' && teamStatus === 'complete') {
      setCollapsed(true);
    }
    prevStatusRef.current = teamStatus;
  }, [teamStatus]);

  const taskList = Object.values(tasks);
  if (taskList.length === 0) return null;

  const completedCount = taskList.filter((t) => t.status === 'completed').length;
  const totalCount = taskList.length;

  return (
    <div className={`chat-task-board${collapsed ? ' collapsed' : ''}`}>
      <div className="chat-task-board-header" onClick={() => setCollapsed((p) => !p)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <line x1="9" y1="9" x2="15" y2="9" />
          <line x1="9" y1="13" x2="15" y2="13" />
          <line x1="9" y1="17" x2="12" y2="17" />
        </svg>
        <span>Team Tasks ({completedCount}/{totalCount})</span>
        <svg className="chat-task-board-toggle" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      {!collapsed && (
        <div className="chat-task-board-list">
          {taskList.map((task) => (
            <TaskItem key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}

const EMPTY_MESSAGES: Message[] = [];

export default function ChatArea() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const runtimes = useChatStore((s) => s.runtimes);
  const toolPanelOpen = useUIStore((s) => s.toolPanelOpen);
  const tasks = useTeamStore((s) => s.tasks);
  const activeTeamId = useTeamStore((s) => s.activeTeamId);

  const messages = useMemo(() => {
    if (!currentSessionId) return EMPTY_MESSAGES;
    return runtimes[currentSessionId]?.messages ?? EMPTY_MESSAGES;
  }, [currentSessionId, runtimes]);

  // Load messages when switching sessions (uses store.loadMessages which validates)
  useEffect(() => {
    if (currentSessionId) {
      const runtime = useChatStore.getState().runtimes[currentSessionId];
      if (!runtime || runtime.messages.length === 0) {
        useChatStore.getState().loadMessages(currentSessionId);
      }
    }
  }, [currentSessionId]);

  // Track message count to force scroll on new user message
  const prevMsgCountRef = useRef(0);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (containerRef.current) {
      const el = containerRef.current;
      const msgCount = messages.length;
      const prevCount = prevMsgCountRef.current;
      prevMsgCountRef.current = msgCount;

      // Force scroll when a new message is added (user just sent or assistant starts)
      const newMessageAdded = msgCount > prevCount;
      const isNearBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight < 150;

      if (newMessageAdded || isNearBottom) {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight;
        });
      }
    }
  }, [messages]);

  // Track scroll position to show/hide scroll-to-bottom button
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(distanceFromBottom > 300);
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  const isStreaming = useMemo(() => {
    if (!currentSessionId) return false;
    return runtimes[currentSessionId]?.isStreaming === true;
  }, [currentSessionId, runtimes]);

  const hasMessages = messages.length > 0 && !messages.every((m) => m.isThinking);

  return (
    <div className="chat-container" ref={containerRef}>
      <div className="chat-content">
        {hasMessages ? <MessageList messages={messages} isStreaming={isStreaming} /> : <WelcomeScreen />}
        {activeTeamId && Object.keys(tasks).length > 0 && (
          <ChatTaskBoard tasks={tasks} />
        )}
      </div>
      {toolPanelOpen && <ToolPanel />}
      {showScrollBtn && (
        <button
          className="scroll-to-bottom-btn"
          onClick={scrollToBottom}
          title="Scroll to bottom"
        >
          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
          </svg>
        </button>
      )}
    </div>
  );
}
