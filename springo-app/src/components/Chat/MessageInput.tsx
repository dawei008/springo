import { useState, useRef, useCallback, useEffect } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import { api } from '@/services/api';
import type { Attachment, Skill } from '@/types';

const BASE_URL = 'http://127.0.0.1:8081';

const FILE_ACCEPT =
  'image/*,.pdf,.txt,.md,.json,.csv,.pptx,.ppt,.xlsx,.xls,.docx,.doc,.html,.xml,.yaml,.yml,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.h,.css,.scss,.sql,.sh,.bash,.zsh,.r,.rb,.php,.swift,.kt,.scala,.lua,.m,.mm';

/** Built-in commands shown in the skill picker */
const BUILT_IN_COMMANDS = [
  { name: 'name', description: 'Rename current session (usage: /name New Title)', isBuiltIn: true as const },
  { name: 'rename', description: 'Alias for /name', isBuiltIn: true as const },
  { name: 'clear', description: 'Clear current session messages', isBuiltIn: true as const },
  { name: 'terminal', description: 'Execute a command inline (usage: /terminal ls -la)', isBuiltIn: true as const },
];

export default function MessageInput() {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);

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
  const lastKnownSyncCountRef = useRef(0);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stopTask = useChatStore((s) => s.stopTask);
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const settings = useSettingsStore((s) => s.settings);
  const activeSkill = useUIStore((s) => s.activeSkill);
  const clearActiveSkill = useUIStore((s) => s.clearActiveSkill);
  const teamModeEnabled = useUIStore((s) => s.teamModeEnabled);
  const teamCollaborativeMode = useUIStore((s) => s.teamCollaborativeMode);
  const cycleTeamMode = useUIStore((s) => s.cycleTeamMode);
  const activeTeamId = useUIStore((s) => s.activeTeamId);

  // Load available skills on mount
  useEffect(() => {
    fetch(`${BASE_URL}/v1/skills`)
      .then((r) => r.json())
      .then((data) => setSkills(data.skills || []))
      .catch(() => {});
  }, []);

  // Memory sync status polling
  useEffect(() => {
    const updateMemorySyncStatus = async () => {
      try {
        const res = await fetch(`${BASE_URL}/v1/memory/status`);
        const data = await res.json();

        if (data.sessions_synced > 0) {
          lastKnownSyncCountRef.current = data.sessions_synced;
        }

        const lastCount = lastKnownSyncCountRef.current;

        switch (data.status) {
          case 'synced':
            setSyncStatus('synced');
            setSyncText(`Synced: ${data.sessions_synced} sessions`);
            break;
          case 'syncing':
            setSyncStatus('syncing');
            setSyncText(`Syncing... (${data.pending} pending)`);
            break;
          case 'disabled':
          case 'not_running':
            setSyncStatus('disabled');
            setSyncText(lastCount > 0 ? `Synced: ${lastCount} sessions` : 'Memory: off');
            break;
          case 'error':
            setSyncStatus('error');
            setSyncText(lastCount > 0 ? `Synced: ${lastCount} sessions` : 'Sync paused');
            break;
          default:
            setSyncStatus('disabled');
            setSyncText(lastCount > 0 ? `Synced: ${lastCount} sessions` : 'Memory: --');
        }

        setSyncTitle(
          `Memory Sync (${data.memory_backend || 'agentcore'})\n` +
          `Status: ${data.status || 'unknown'}\n` +
          `Memory ID: ${data.memory_id || 'N/A'}\n` +
          `Region: ${data.region || 'N/A'}\n` +
          `Sessions: ${data.sessions_synced || 0}\n` +
          `Total Events: ${data.total_events || 0}`,
        );
      } catch {
        const lastCount = lastKnownSyncCountRef.current;
        setSyncStatus('disabled');
        setSyncText(lastCount > 0 ? `Synced: ${lastCount} sessions` : 'Memory: --');
      }
    };

    updateMemorySyncStatus();
    const interval = setInterval(updateMemorySyncStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // Context indicator: refresh when session changes or streaming ends
  useEffect(() => {
    const refreshContextStats = async () => {
      if (!currentSessionId) {
        setContextPercent(0);
        setContextStatus('normal');
        setContextTitle('Click for context breakdown');
        return;
      }

      try {
        const response = await fetch(`${BASE_URL}/v1/context/stats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            extended_context: settings.enable1mContext !== false,
          }),
        });

        if (response.ok) {
          const data = await response.json();
          const percent = data.usage_percent || 0;
          const status: 'normal' | 'warning' | 'critical' =
            percent >= 80 ? 'critical' : percent >= 60 ? 'warning' : 'normal';
          setContextPercent(Math.round(percent));
          setContextStatus(status);
          setContextTitle(
            `Tokens: ${(data.total_tokens || 0).toLocaleString()} / ${(data.max_tokens || 0).toLocaleString()}`,
          );
        }
      } catch {
        // Ignore errors
      }
    };

    refreshContextStats();
  }, [currentSessionId, isStreaming, settings.enable1mContext]);

  // Auto-resize textarea
  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, []);

  // Build filtered items for skill picker
  const getFilteredSkillItems = useCallback(
    (query: string) => {
      const filteredBuiltIn = BUILT_IN_COMMANDS.filter(
        (c) =>
          c.name.toLowerCase().includes(query) ||
          c.description.toLowerCase().includes(query),
      );
      const filteredSkills = skills.filter(
        (s) =>
          s.name.toLowerCase().includes(query) ||
          s.description.toLowerCase().includes(query),
      );
      return [...filteredBuiltIn, ...filteredSkills];
    },
    [skills],
  );

  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      setText(value);

      // Skill picker detection
      if (value.startsWith('/') && !value.includes(' ')) {
        const query = value.substring(1).toLowerCase();
        const allItems = getFilteredSkillItems(query);
        if (allItems.length > 0) {
          setShowSkillPicker(true);
          setSkillPickerIndex(0);
        } else {
          setShowSkillPicker(false);
        }
      } else {
        setShowSkillPicker(false);
      }
    },
    [getFilteredSkillItems],
  );

  const handleSend = useCallback(async () => {
    const content = text.trim();
    if (!content && attachments.length === 0) return;

    // If an active team is running, send to team lead instead of new request
    if (activeTeamId && isStreaming && content) {
      setText('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
      // Add user message to chat display
      const convId = currentSessionId;
      if (convId) {
        useChatStore.getState().addMessage(convId, {
          role: 'user',
          content,
          timestamp: Date.now(),
        });
      }
      try {
        await api.teams.message(activeTeamId, { content, sender: 'user' });
      } catch (e) {
        useUIStore.getState().showToast('Failed to send message to team', 'error');
      }
      return;
    }

    if (isStreaming) return;

    let convId = currentSessionId;
    if (!convId) {
      convId = createSession();
    }

    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const atts = attachments.map((a) => ({
      type: a.type,
      data: a.data,
      name: a.name,
      path: a.path,
    }));

    await sendMessage(convId, content, atts, {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId: convId,
    });

    if (activeSkill) {
      clearActiveSkill();
    }
  }, [
    text,
    attachments,
    isStreaming,
    currentSessionId,
    createSession,
    sendMessage,
    settings,
    activeSkill,
    clearActiveSkill,
    activeTeamId,
  ]);

  const handleStop = useCallback(() => {
    if (currentSessionId) {
      stopTask(currentSessionId);
    }
  }, [currentSessionId, stopTask]);

  const selectSkill = useCallback(
    (skill: Skill) => {
      useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
      setText('');
      setShowSkillPicker(false);
      textareaRef.current?.focus();
    },
    [],
  );

  const selectBuiltInCommand = useCallback((cmdName: string) => {
    setText(`/${cmdName} `);
    setShowSkillPicker(false);
    textareaRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Skill picker navigation
      if (showSkillPicker) {
        const query = text.substring(1).toLowerCase();
        const allItems = getFilteredSkillItems(query);

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSkillPickerIndex((prev) => Math.min(prev + 1, allItems.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSkillPickerIndex((prev) => Math.max(prev - 1, 0));
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as KeyboardEvent).isComposing) {
          e.preventDefault();
          const item = allItems[skillPickerIndex];
          if (item) {
            if ('isBuiltIn' in item && item.isBuiltIn) {
              selectBuiltInCommand(item.name);
            } else {
              selectSkill(item as Skill);
            }
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowSkillPicker(false);
          return;
        }
      }

      // Escape to stop streaming
      if (e.key === 'Escape' && isStreaming) {
        e.preventDefault();
        handleStop();
        return;
      }

      // Enter to send, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as KeyboardEvent).isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [showSkillPicker, text, getFilteredSkillItems, skillPickerIndex, selectBuiltInCommand, selectSkill, isStreaming, handleStop, handleSend],
  );

  // Handle paste for images
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = e.clipboardData.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          e.preventDefault();
          const file = items[i].getAsFile();
          if (file) {
            const reader = new FileReader();
            reader.onload = () => {
              const base64 = (reader.result as string).split(',')[1];
              setAttachments((prev) => [
                ...prev,
                { name: file.name || 'pasted-image', type: file.type, data: base64 },
              ]);
            };
            reader.readAsDataURL(file);
          }
          return;
        }
      }
    },
    [],
  );

  // Handle file input change
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    processFiles(Array.from(files));
    // Reset file input so same file can be picked again
    e.target.value = '';
  }, []);

  // Process files (shared between file input and drag-and-drop)
  const processFiles = useCallback((files: File[]) => {
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: file.type, data: base64 },
          ]);
        };
        reader.readAsDataURL(file);
      } else {
        setAttachments((prev) => [
          ...prev,
          {
            name: file.name,
            type: file.type || 'application/octet-stream',
            path: (file as File & { path?: string }).path || file.name,
          },
        ]);
      }
    }
  }, []);

  // Handle drag-and-drop
  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('drag-over');
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.classList.remove('drag-over');
      const files = Array.from(e.dataTransfer.files);
      processFiles(files);
    },
    [processFiles],
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const toggleTeamMode = useCallback(() => {
    cycleTeamMode();
  }, [cycleTeamMode]);

  // Toggle context breakdown popup
  const toggleContextBreakdown = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setShowContextBreakdown((prev) => !prev);

      if (!showContextBreakdown && currentSessionId) {
        // Fetch breakdown content
        fetch(`${BASE_URL}/v1/context/breakdown`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSessionId }),
        })
          .then((r) => r.json())
          .then((data) => {
            if (data.breakdown) {
              setContextBreakdownHtml(data.breakdown);
            }
          })
          .catch(() => {
            setContextBreakdownHtml('<div class="breakdown-empty">Failed to load breakdown</div>');
          });
      }
    },
    [showContextBreakdown, currentSessionId],
  );

  // Close context breakdown when clicking outside
  useEffect(() => {
    if (!showContextBreakdown) return;
    const handleClick = () => setShowContextBreakdown(false);
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [showContextBreakdown]);

  // Build the filtered skill picker items
  const filteredSkillItems = showSkillPicker
    ? getFilteredSkillItems(text.substring(1).toLowerCase())
    : [];

  const canSend = (text.trim() || attachments.length > 0) && (!isStreaming || !!activeTeamId);

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
    <div className="input-area">
      {/* Active skill indicator (rendered before input-wrapper, like legacy) */}
      {activeSkill && (
        <div className="active-skill-indicator" id="active-skill-indicator">
          <span className="skill-badge">
            <span className="skill-icon">&#x26A1;</span>
            /{activeSkill.name}
          </span>
          <span className="skill-desc">
            {activeSkill.description ? activeSkill.description.substring(0, 60) + '...' : ''}
          </span>
          <button className="skill-clear" onClick={clearActiveSkill}>
            &times;
          </button>
        </div>
      )}

      <div
        className="input-wrapper"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Attachments container */}
        <div className="attachments" id="attachments">
          {attachments.map((a, i) => {
            const isImage = a.type && a.type.startsWith('image/');
            if (isImage && a.data) {
              return (
                <div key={i} className="attachment image-attachment" title={a.name}>
                  <img
                    src={`data:${a.type};base64,${a.data}`}
                    className="attachment-thumbnail"
                    alt={a.name}
                  />
                  <span className="attachment-name">
                    {a.name.length > 20 ? a.name.slice(0, 17) + '...' : a.name}
                  </span>
                  <span className="remove" onClick={() => removeAttachment(i)}>
                    &times;
                  </span>
                </div>
              );
            } else {
              return (
                <div key={i} className="attachment">
                  <svg className="file-icon" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Z" />
                  </svg>
                  {a.name}
                  <span className="remove" onClick={() => removeAttachment(i)}>
                    &times;
                  </span>
                </div>
              );
            }
          })}
        </div>

        {/* Input box */}
        <div className="input-box">
          <div className="input-actions">
            <button
              className="icon-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Attach file"
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Z" />
                <path d="M12 9H8M12 13H8M10 5H8" />
              </svg>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              id="file-input"
              multiple
              accept={FILE_ACCEPT}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          </div>

          <textarea
            ref={textareaRef}
            id="message-input"
            placeholder={
              activeSkill
                ? `Using /${activeSkill.name} skill - Enter your request...`
                : teamCollaborativeMode
                  ? 'Team Collaborative Mode - agents work together...'
                  : teamModeEnabled
                    ? 'Team Mode - multi-agent collaboration...'
                    : 'Message Springo... (/ for skills)'
            }
            rows={1}
            value={text}
            onChange={handleTextChange}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
          />

          <button
            id="team-toggle"
            className={`team-toggle-btn${teamModeEnabled ? ' active' : ''}${teamCollaborativeMode ? ' collab' : ''}`}
            onClick={toggleTeamMode}
            title={
              teamCollaborativeMode
                ? 'Collaborative Mode (click to disable)'
                : teamModeEnabled
                  ? 'Classic Team Mode (click for collaborative)'
                  : 'Team Mode - multi-agent collaboration'
            }
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </button>

          <button
            id="send-btn"
            onClick={handleSend}
            disabled={!canSend}
            style={{ display: (isStreaming && !activeTeamId) ? 'none' : 'flex' }}
          >
            <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12l5-5 5 5" />
            </svg>
          </button>

          <button
            id="stop-btn"
            onClick={handleStop}
            title="Stop (Esc)"
            style={{ display: (isStreaming && !activeTeamId) ? undefined : 'none' }}
          >
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        </div>

        {/* Bottom status row */}
        <div className="bottom-status-row">
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
      </div>

      {/* Skill picker (appended to input-area, like legacy) */}
      {showSkillPicker && filteredSkillItems.length > 0 && (
        <div className="skill-picker" id="skill-picker">
          {filteredSkillItems.map((item, idx) => {
            const isBuiltIn = 'isBuiltIn' in item && item.isBuiltIn;
            return (
              <div
                key={item.name + (isBuiltIn ? '-builtin' : '')}
                className={`skill-picker-item${isBuiltIn ? ' built-in' : ''}${idx === skillPickerIndex ? ' active' : ''}`}
                onClick={() =>
                  isBuiltIn ? selectBuiltInCommand(item.name) : selectSkill(item as Skill)
                }
              >
                <div className="skill-picker-name">
                  /{item.name}
                  {isBuiltIn && (
                    <span style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}> (local)</span>
                  )}
                </div>
                <div className="skill-picker-desc">
                  {item.description.length > 80
                    ? item.description.substring(0, 80) + '...'
                    : item.description}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
