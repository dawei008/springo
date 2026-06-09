import { useState, useCallback, useEffect } from 'react';
import Header from './Header';
import ChatArea from '@/components/Chat/ChatArea';
import MessageInput from '@/components/Chat/MessageInput';
import SkillProposalBanner from '@/components/Chat/SkillProposalBanner';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useTeamStore } from '@/stores/teamStore';
import { usePlanStore } from '@/stores/planStore';
import Canvas from '@/components/Canvas/Canvas';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import type { UsageData } from '@/types';
import { BACKEND_BASE_URL } from '@/stores/unifiedArtifactStore';

const BASE_URL = BACKEND_BASE_URL;

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function computeCacheHitRate(usage: UsageData): number | null {
  const { cache_read_input_tokens, cache_creation_input_tokens, input_tokens } = usage;
  if (cache_read_input_tokens === 0 && cache_creation_input_tokens === 0) return null;
  const total = input_tokens + cache_creation_input_tokens + cache_read_input_tokens;
  if (total === 0) return null;
  return Math.round((cache_read_input_tokens / total) * 100);
}

// ==================== StatusBar ====================

function StatusBar() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const settings = useSettingsStore((s) => s.settings);

  // Context indicator state
  const [contextPercent, setContextPercent] = useState(0);
  const [contextStatus, setContextStatus] = useState<'normal' | 'warning' | 'critical'>('normal');
  const [contextTitle, setContextTitle] = useState('Click for context breakdown');
  const [showContextBreakdown, setShowContextBreakdown] = useState(false);
  const [contextBreakdownHtml, setContextBreakdownHtml] = useState('');

  // Memory sync status state
  const [syncStatus, setSyncStatus] = useState<'synced' | 'syncing' | 'disabled' | 'error' | 'checking'>('checking');
  const [syncText, setSyncText] = useState('Memory: checking...');
  const [syncTitle, setSyncTitle] = useState('AgentCore Memory Sync Status');

  // Token usage tracking
  const sessionUsage = useChatStore((s) =>
    currentSessionId ? s.sessionUsage[currentSessionId] : undefined,
  );

  // Load persisted usage from backend when session changes
  useEffect(() => {
    if (currentSessionId) {
      useChatStore.getState().loadUsage(currentSessionId);
    }
  }, [currentSessionId]);

  // Model for context stats
  const currentModel = settings.model || useSettingsStore((s) => s.defaultModel);

  // Health polling state. Single chained setTimeout with adaptive interval —
  // poll every 3s while disconnected, every 30s while healthy. setState is
  // gated on actual change so subscribers (StatusBar) don't churn.
  const [serverHealthy, setServerHealthy] = useState(false);
  useEffect(() => {
    let mounted = true;
    let healthy = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const res = await fetch(`${BASE_URL}/health`);
        const data = await res.json();
        const next = data.status === 'healthy';
        if (mounted && next !== healthy) {
          healthy = next;
          setServerHealthy(next);
        }
      } catch {
        if (mounted && healthy) {
          healthy = false;
          setServerHealthy(false);
        }
      }
      if (mounted) timer = setTimeout(tick, healthy ? 30_000 : 3000);
    };
    void tick();
    return () => {
      mounted = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  // Derive status from health + session + streaming state
  const status = !serverHealthy ? 'error' : isStreaming ? 'running' : session?.status || 'idle';

  const statusText: Record<string, string> = {
    idle: '\u25cf Ready',
    running: '\u25d0 Running...',
    completed: '\u2713 Completed',
    error: !serverHealthy ? '\u25d0 Connecting...' : '\u2715 Error',
    compacting: '\u25d0 Compacting...',
  };

  const statusClass: Record<string, string> = {
    idle: 'status-connected',
    running: 'status-running',
    completed: 'status-completed',
    error: !serverHealthy ? 'status-connecting' : 'status-error',
    compacting: 'status-running',
  };

  // Memory sync status polling — only commits state when the displayed
  // values actually change so StatusBar doesn't re-render every 10s.
  useEffect(() => {
    let lastStatus: typeof syncStatus | null = null;
    let lastText = '';
    let lastTitle = '';
    const formatSyncTime = (iso: string) => {
      if (!iso) return '';
      const diff = Date.now() - new Date(iso + 'Z').getTime();
      if (diff < 60000) return 'just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return `${Math.floor(diff / 86400000)}d ago`;
    };
    const tick = async () => {
      let nextStatus: typeof syncStatus = 'disabled';
      let nextText = 'Memory: --';
      let nextTitle = lastTitle;
      try {
        const res = await fetch(`${BASE_URL}/v1/memory/status`);
        const data = await res.json();
        const syncTime = data.last_file_sync ? formatSyncTime(data.last_file_sync) : '';
        const filesCount = data.files_synced || 0;
        switch (data.status) {
          case 'synced':
            nextStatus = 'synced';
            nextText = syncTime ? `Synced ${syncTime}` : `Synced: ${filesCount} files`;
            break;
          case 'syncing':
            nextStatus = 'syncing';
            nextText = `Syncing... (${data.pending} pending)`;
            break;
          case 'disabled':
          case 'not_running':
            nextStatus = 'disabled';
            nextText = syncTime ? `Synced ${syncTime}` : 'Memory: off';
            break;
          case 'error':
            nextStatus = 'error';
            nextText = syncTime ? `Synced ${syncTime}` : 'Sync paused';
            break;
          default:
            nextStatus = 'disabled';
            nextText = syncTime ? `Synced ${syncTime}` : 'Memory: --';
        }
        nextTitle =
          `Memory Sync (${data.memory_backend || 'agentcore'})\n` +
          `Status: ${data.status || 'unknown'}\n` +
          `Memory ID: ${data.memory_id || 'N/A'}\n` +
          `Region: ${data.region || 'N/A'}\n` +
          `Files synced: ${filesCount}\n` +
          (syncTime ? `Last sync: ${syncTime}` : '');
      } catch {
        nextStatus = 'disabled';
        nextText = 'Memory: --';
      }
      if (nextStatus !== lastStatus) { lastStatus = nextStatus; setSyncStatus(nextStatus); }
      if (nextText !== lastText) { lastText = nextText; setSyncText(nextText); }
      if (nextTitle !== lastTitle) { lastTitle = nextTitle; setSyncTitle(nextTitle); }
    };
    void tick();
    const interval = setInterval(tick, 10000);
    return () => clearInterval(interval);
  }, []);

  // Context indicator: refresh when session changes or streaming ends
  useEffect(() => {
    if (isStreaming) return;

    if (!currentSessionId) {
      setContextPercent(0);
      setContextStatus('normal');
      setContextTitle('Click for context breakdown');
      return;
    }

    const refreshContextStats = async () => {
      try {
        const response = await fetch(`${BASE_URL}/v1/context/stats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            model: currentModel,
          }),
        });

        if (response.ok) {
          const data = await response.json();
          const percent = data.usage_percent || 0;
          const ctxStatus: 'normal' | 'warning' | 'critical' =
            percent >= 80 ? 'critical' : percent >= 60 ? 'warning' : 'normal';
          setContextPercent(Math.round(percent));
          setContextStatus(ctxStatus);
          setContextTitle(
            `Tokens: ${(data.total_tokens || 0).toLocaleString()} / ${(data.max_tokens || 0).toLocaleString()}`,
          );
        }
      } catch {
        // Ignore errors
      }
    };

    refreshContextStats();
  }, [currentSessionId, isStreaming, currentModel]);

  // Render context breakdown data into HTML
  const renderContextBreakdown = useCallback((data: Record<string, unknown>) => {
    const breakdown = data.breakdown as Record<string, { count: number; tokens: number; percent: number }>;
    if (!breakdown) return '<div class="breakdown-empty">No breakdown data</div>';

    const categories = [
      { key: 'system_prompt', label: 'System Prompt', cssClass: 'system' },
      { key: 'system_tools', label: 'System Tools', cssClass: 'tools' },
      { key: 'skills', label: 'Skills', cssClass: 'skills' },
      { key: 'memory_files', label: 'Memory Files', cssClass: 'memory' },
      { key: 'user_text', label: 'User', cssClass: 'user' },
      { key: 'assistant_text', label: 'Assistant', cssClass: 'assistant' },
      { key: 'tool_use', label: 'Tool Use', cssClass: 'tool-use' },
      { key: 'tool_result', label: 'Tool Result', cssClass: 'tool-result' },
      { key: 'images', label: 'Images', cssClass: 'images' },
    ];

    let html = '';
    for (const cat of categories) {
      const catData = breakdown[cat.key];
      if (!catData) continue;
      if (catData.count > 0 || catData.tokens > 0) {
        const tokensStr = catData.tokens >= 1000
          ? `${(catData.tokens / 1000).toFixed(1)}k`
          : String(catData.tokens);
        html += `<div class="breakdown-row">
          <span class="breakdown-label">${cat.label}</span>
          <div class="breakdown-bar-container">
            <div class="breakdown-bar ${cat.cssClass}" style="width: ${Math.min(catData.percent, 100)}%"></div>
          </div>
          <span class="breakdown-percent">${catData.percent.toFixed(1)}% (${tokensStr})</span>
        </div>`;
      }
    }

    const usedPercent = data.usage_percent as number;
    const freePercent = Math.max(0, 100 - usedPercent);
    const totalTokens = data.total_tokens as number;
    const maxTokens = data.max_tokens as number;
    const freeTokens = maxTokens - totalTokens;
    const freeStr = freeTokens >= 1000 ? `${(freeTokens / 1000).toFixed(1)}k` : String(freeTokens);

    html += `<div class="breakdown-row breakdown-free">
      <span class="breakdown-label">Free Space</span>
      <div class="breakdown-bar-container">
        <div class="breakdown-bar free" style="width: ${freePercent}%"></div>
      </div>
      <span class="breakdown-percent">${freePercent.toFixed(1)}% (${freeStr})</span>
    </div>`;

    html += `<div class="breakdown-total">
      <span class="breakdown-total-label">Total</span>
      <span class="breakdown-total-value">${totalTokens.toLocaleString()} / ${maxTokens.toLocaleString()} (${usedPercent}%)</span>
    </div>`;

    return html;
  }, []);

  // Toggle context breakdown popup
  const toggleContextBreakdown = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setShowContextBreakdown((prev) => !prev);

      if (!showContextBreakdown && currentSessionId) {
        setContextBreakdownHtml('<div class="breakdown-loading">Loading...</div>');

        const runtime = useChatStore.getState().runtimes[currentSessionId];
        const messages = runtime?.messages?.map((msg) => {
          try {
            JSON.stringify(msg);
            return msg;
          } catch {
            return { role: msg.role || 'user', content: '[Non-serializable content]' };
          }
        }) || [];

        fetch(`${BASE_URL}/v1/context/breakdown`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages,
            system: '',
            tools: [],
            skills: [],
            memory_files: [],
            model: settings.model || '',
          }),
        })
          .then((r) => r.json())
          .then((data) => {
            setContextBreakdownHtml(renderContextBreakdown(data));
          })
          .catch(() => {
            setContextBreakdownHtml('<div class="breakdown-error">Failed to load breakdown</div>');
          });
      }
    },
    [showContextBreakdown, currentSessionId, settings.model, renderContextBreakdown],
  );

  // Close context breakdown when clicking outside
  useEffect(() => {
    if (!showContextBreakdown) return;
    const handleClick = () => setShowContextBreakdown(false);
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [showContextBreakdown]);

  // Determine context indicator class
  const contextIndicatorClass =
    'context-indicator' + (contextStatus !== 'normal' ? ` ${contextStatus}` : '');

  // Determine sync icon class
  const syncIconClass =
    'sync-icon' +
    (syncStatus === 'synced'
      ? ' synced'
      : syncStatus === 'syncing' || syncStatus === 'error'
        ? ' syncing'
        : ' disabled');

  return (
    <div className="status-bar">
      <span id="status" className={statusClass[status] || ''}>
        {statusText[status] || '\u25cf Ready'}
      </span>
      <div style={{ flex: 1 }} />

      <div
        className={contextIndicatorClass}
        id="context-indicator"
        onClick={toggleContextBreakdown}
        title={contextTitle}
      >
        <span className="context-icon">&bull;</span>
        <span id="context-text">
          {contextStatus === 'critical'
            ? `Context: ${contextPercent}% - Compacting`
            : `Context: ${contextPercent}%`}
        </span>
        {/* Context Breakdown Popup */}
        <div
          className={`context-breakdown-popup${showContextBreakdown ? ' visible' : ''}`}
          id="context-breakdown-popup"
        >
          <div className="breakdown-header">Context Breakdown</div>
          <div
            className="breakdown-content"
            id="breakdown-content"
            dangerouslySetInnerHTML={{ __html: contextBreakdownHtml }}
          />
        </div>
      </div>

      {sessionUsage && (sessionUsage.input_tokens > 0 || sessionUsage.output_tokens > 0) && (() => {
        const cacheRate = computeCacheHitRate(sessionUsage);
        const title =
          `Input: ${sessionUsage.input_tokens.toLocaleString()} tokens\n` +
          `Output: ${sessionUsage.output_tokens.toLocaleString()} tokens\n` +
          (cacheRate !== null
            ? `Cache Read: ${sessionUsage.cache_read_input_tokens.toLocaleString()}\n` +
              `Cache Create: ${sessionUsage.cache_creation_input_tokens.toLocaleString()}\n` +
              `Cache Hit: ${cacheRate}%`
            : 'No cache data');
        return (
          <div className="token-usage-indicator" title={title}>
            <span className="token-icon">&bull;</span>
            <span>
              {'\u2191'}{formatTokenCount(sessionUsage.input_tokens)}
              {' '}
              {'\u2193'}{formatTokenCount(sessionUsage.output_tokens)}
              {cacheRate !== null && ` | Cache ${cacheRate}%`}
            </span>
          </div>
        );
      })()}

      <div
        className="memory-sync-status"
        id="memory-sync-status"
        title={syncTitle}
      >
        <span className={syncIconClass} id="sync-icon">
          &bull;
        </span>
        <span id="sync-text">{syncText}</span>
      </div>
    </div>
  );
}

// ==================== MainContent ====================

export default function MainContent() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);

  // Restore team panel and clear stale UI state when switching sessions
  useEffect(() => {
    // Restore todos and queue for the session (or clear if none saved)
    const savedTodos = currentSessionId
      ? useUIStore.getState().getSessionTodos(currentSessionId)
      : [];
    useUIStore.getState().setTodos(savedTodos);
    useUIStore.getState().switchSessionQueue(currentSessionId ?? null);

    if (!currentSessionId) {
      useTeamStore.getState().resetTeam();
      return;
    }
    const teamId = useUIStore.getState().getSessionTeam(currentSessionId);
    if (teamId) {
      // Load historical team data from backend API and restore team mode
      useTeamStore.getState().loadTeamFromAPI(teamId).then((loaded) => {
        if (loaded) {
          useUIStore.getState().setActiveTeamId(teamId);
          useUIStore.getState().setTeamModeEnabled(true);
        }
      });
    } else {
      // No team for this session — reset team state and disable team mode
      useTeamStore.getState().resetTeam();
      useUIStore.getState().setActiveTeamId(null);
      useUIStore.getState().setTeamModeEnabled(false);
    }
  }, [currentSessionId]);

  // Save/restore artifact panel and plan state per session
  useEffect(() => {
    useUnifiedArtifactStore.getState().switchSession(currentSessionId ?? null);
    usePlanStore.getState().switchSession(currentSessionId ?? null);
  }, [currentSessionId]);

  // Restore the session's pinned working directory so the UI chip + tool calls
  // match this session's context, not whatever the previously-active session
  // happened to leave in the global setting.
  useEffect(() => {
    if (!currentSessionId) return;
    const session = useSessionStore.getState().sessions.find((s) => s.id === currentSessionId);
    const wd = session?.workingDir?.trim();
    if (!wd) return;
    if (useSettingsStore.getState().workingDir !== wd) {
      useSettingsStore.getState().setWorkingDir(wd);
    }
  }, [currentSessionId]);

  const hasActiveArtifact = useUnifiedArtifactStore((s) => s.activeArtifactId !== null);

  // Auto-open the plan as a Canvas internal artifact whenever the plan
  // store has content. Replaces the standalone <PlanPanel /> mount; now
  // plans get session tabs, fullscreen, the "Building…" badge, etc.
  // We only re-open if the user isn't already looking at it (don't yank
  // them away from another tab).
  useEffect(() => {
    const unsub = usePlanStore.subscribe((state, prev) => {
      const had = !!prev?.currentPlan;
      const has = !!state.currentPlan;
      if (!had && has) {
        useUnifiedArtifactStore.getState().openInternal('plan', 'Plan');
      }
    });
    return unsub;
  }, []);

  return (
    <div className="main-content">
      <Header />
      <div className="chat-panel-wrapper">
        <div className="chat-area">
          <ChatArea />
          <SkillProposalBanner />
          <MessageInput />
          <StatusBar />
        </div>
        {hasActiveArtifact && <Canvas />}
      </div>
    </div>
  );
}
