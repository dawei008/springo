import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import { useToolsStore } from '@/stores/toolsStore';
import { usePlanStore } from '@/stores/planStore';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import { api } from '@/services/api';
import type { Attachment, Skill } from '@/types';
import ToolsPicker from './ToolsPicker';
import { escapeHtml } from '@/utils/escapeHtml';

function formatRuntimeState(state: Record<string, unknown>): string {
  if (!state || Object.keys(state).length === 0) return '(empty — artifact has not reported any state yet)';
  // Pretty-print JSON so the model can see structure, but keep it compact.
  try {
    const pretty = JSON.stringify(state, null, 2);
    // Cap to 2KB so long lists don't blow the context.
    if (pretty.length > 2000) {
      return pretty.slice(0, 2000) + '\n... (truncated)';
    }
    return pretty;
  } catch {
    return '(state not serializable)';
  }
}

function buildArtifactContext(): string | undefined {
  const store = useUnifiedArtifactStore.getState();
  const artifact = store.activeArtifactId ? store.artifacts[store.activeArtifactId] : null;
  if (!artifact) return undefined;

  const totalLines = artifact.files.reduce((sum, f) => sum + f.content.split('\n').length, 0);
  const includeFullContent = totalLines < 500;

  let ctx = `<artifact-context>\n`;
  ctx += `  <!-- To edit this artifact, emit <springo-artifact op="patch" id="${escapeHtml(artifact.id)}">. Do NOT rebuild it with op="create". -->\n`;
  ctx += `  <artifact id="${escapeHtml(artifact.id)}" name="${escapeHtml(artifact.name)}" type="${escapeHtml(artifact.type)}" version="${artifact.versions.length}">\n`;
  ctx += `    <runtime-state>\n${formatRuntimeState(artifact.state)}\n    </runtime-state>\n`;

  if (includeFullContent) {
    ctx += `    <files count="${artifact.files.length}">\n`;
    for (const f of artifact.files) {
      ctx += `<springo-file path="${escapeHtml(f.path)}" type="text/${f.type}">\n${f.content}\n</springo-file>\n`;
    }
    ctx += `    </files>\n`;
  } else {
    ctx += `    <files count="${artifact.files.length}">\n`;
    for (const f of artifact.files) {
      const lines = f.content.split('\n').length;
      ctx += `      <file path="${escapeHtml(f.path)}" lines="${lines}" />\n`;
    }
    ctx += `    </files>\n`;
  }

  const pinned = store.pinnedElement;
  if (pinned) {
    ctx += `    <pinned-element>\n`;
    ctx += `      component: ${pinned.componentName}\n`;
    ctx += `      cssPath: ${pinned.cssPath}\n`;
    ctx += `      tagName: ${pinned.tagName}\n`;
    if (pinned.className) ctx += `      className: ${pinned.className}\n`;
    if (pinned.id) ctx += `      id: ${pinned.id}\n`;
    ctx += `    </pinned-element>\n`;
  }

  ctx += `  </artifact>\n`;
  ctx += `</artifact-context>`;
  return ctx;
}

const FILE_ACCEPT =
  'image/*,.pdf,.txt,.md,.json,.csv,.pptx,.ppt,.xlsx,.xls,.docx,.doc,.html,.xml,.yaml,.yml,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.h,.css,.scss,.sql,.sh,.bash,.zsh,.r,.rb,.php,.swift,.kt,.scala,.lua,.m,.mm';

/** Bedrock image size limit (5 MB). Compress images that exceed this. */
const MAX_IMAGE_BYTES = 4.5 * 1024 * 1024; // 4.5 MB to leave margin

function compressImage(base64: string, mimeType: string): Promise<{ data: string; type: string }> {
  return new Promise((resolve) => {
    const raw = atob(base64);
    if (raw.length <= MAX_IMAGE_BYTES) {
      resolve({ data: base64, type: mimeType });
      return;
    }
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      // Scale down to fit within size limit
      let { width, height } = img;
      const scale = Math.min(1, Math.sqrt(MAX_IMAGE_BYTES / raw.length) * 0.9);
      width = Math.round(width * scale);
      height = Math.round(height * scale);
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(img, 0, 0, width, height);
      // Try JPEG at decreasing quality until under limit
      for (let q = 0.85; q >= 0.3; q -= 0.1) {
        const dataUrl = canvas.toDataURL('image/jpeg', q);
        const b64 = dataUrl.split(',')[1];
        if (atob(b64).length <= MAX_IMAGE_BYTES) {
          resolve({ data: b64, type: 'image/jpeg' });
          return;
        }
      }
      // Last resort: lowest quality
      const dataUrl = canvas.toDataURL('image/jpeg', 0.2);
      resolve({ data: dataUrl.split(',')[1], type: 'image/jpeg' });
    };
    img.onerror = () => resolve({ data: base64, type: mimeType }); // fallback: send as-is
    img.src = `data:${mimeType};base64,${base64}`;
  });
}

/** Built-in commands shown in the skill picker */
const BUILT_IN_COMMANDS = [
  { name: 'name', description: 'Rename current session (usage: /name New Title)', isBuiltIn: true as const },
  { name: 'rename', description: 'Alias for /name', isBuiltIn: true as const },
  { name: 'clear', description: 'Clear current session messages', isBuiltIn: true as const },
  { name: 'terminal', description: 'Execute a command inline (usage: /terminal ls -la)', isBuiltIn: true as const },
  { name: 'plan', description: 'Generate a structured plan (usage: /plan Migrate auth to JWT)', isBuiltIn: true as const },
  { name: 'ultraplan', description: 'Alias for /plan — generate a structured plan', isBuiltIn: true as const },
  { name: 'design', description: 'Enter design mode — generate visual designs via chat', isBuiltIn: true as const },
];

// ─── @-mention picker (ACP agents + named tasks) ───

interface MentionTarget {
  /** "task" → resume; "agent" → start fresh */
  kind: 'task' | 'agent';
  name: string;
  /** Display label shown in the chip and picker. */
  label: string;
  description: string;
  /** Only set for kind="task". The agent backing this task. */
  agentName?: string;
}

export default function MessageInput() {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);

  // @ mention state. ``mention`` is the locked-in target the next send goes
  // to; while ``showMentionPicker`` is true the user is typing the query.
  const [mention, setMention] = useState<MentionTarget | null>(null);
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [mentionPickerIndex, setMentionPickerIndex] = useState(0);
  const [mentionTasks, setMentionTasks] = useState<Array<{
    name: string; agent_name: string; description: string;
  }>>([]);
  const [mentionAgents, setMentionAgents] = useState<Array<{
    name: string; description: string; running: boolean;
  }>>([]);

  // Fetch agents + tasks when picker opens. Cheap calls; no debounce needed
  // since we cache once per open.
  const refreshMentionData = useCallback(async () => {
    try {
      const [aRes, tRes] = await Promise.all([api.acp.listAgents(), api.acp.listTasks()]);
      if (aRes.ok && aRes.data) {
        setMentionAgents(aRes.data.agents.map((a) => ({
          name: a.name, description: a.description || a.transport, running: a.running,
        })));
      }
      if (tRes.ok && tRes.data) {
        setMentionTasks(tRes.data.tasks.map((t) => ({
          name: t.name, agent_name: t.agent_name, description: t.description,
        })));
      }
    } catch { /* ignore — picker shows whatever we already have */ }
  }, []);

  const [showModelPicker, setShowModelPicker] = useState(false);
  const modelPickerRef = useRef<HTMLDivElement>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const settings = useSettingsStore((s) => s.settings);
  const workingDir = useSettingsStore((s) => s.workingDir);
  const workingFolders = useSettingsStore((s) => s.workingFolders);
  const setWorkingDir = useSettingsStore((s) => s.setWorkingDir);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );
  const displayDir = session?.workingDir || workingDir || '';
  const activeSkill = useUIStore((s) => s.activeSkill);
  const teamModeEnabled = useUIStore((s) => s.teamModeEnabled);
  const teamCollaborativeMode = useUIStore((s) => s.teamCollaborativeMode);
  const activeTeamId = useUIStore((s) => s.activeTeamId);
  const planModeActive = useUIStore((s) => s.planModeActive);
  const queueItems = useUIStore((s) => s.queueItems);

  // Consume pending prompt (pre-filled from Design Dashboard, etc.)
  const pendingPrompt = useUIStore((s) => s.pendingPrompt);
  useEffect(() => {
    if (pendingPrompt) {
      setText(pendingPrompt);
      useUIStore.getState().setPendingPrompt(null);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [pendingPrompt]);

  // Model selector data
  const models = useSettingsStore((s) => s.models);
  const modelsByProvider = useSettingsStore((s) => s.modelsByProvider);
  const currentModel = settings.model || useSettingsStore((s) => s.defaultModel);

  // Compute display name for current model
  const currentModelDisplayName = useMemo(() => {
    const m = models.find((x) => x.id === currentModel);
    if (m) return (m as unknown as Record<string, string>).display_name || m.name || m.id;
    const short = currentModel.replace(/^(claude|anthropic|deepseek|minimax|kimi|qwen|glm)[.-]?/i, '');
    return short || currentModel;
  }, [models, currentModel]);

  // Close model picker when clicking outside
  useEffect(() => {
    if (!showModelPicker) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (modelPickerRef.current && !modelPickerRef.current.contains(e.target as Node)) {
        setShowModelPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModelPicker]);

  const handleModelSelect = useCallback((modelId: string) => {
    useSettingsStore.getState().saveSettings({ model: modelId });
    setShowModelPicker(false);
  }, []);

  // Auto-resize textarea
  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, []);

  // Build filtered items for skill picker (includes built-in commands, skills, and MCP servers)
  const getFilteredSkillItems = useCallback(
    (query: string) => {
      const filteredBuiltIn = BUILT_IN_COMMANDS.filter(
        (c) =>
          c.name.toLowerCase().includes(query) ||
          c.description.toLowerCase().includes(query),
      );
      const currentSkills = useToolsStore.getState().skills;
      const filteredSkills = currentSkills.filter(
        (s) =>
          s.name.toLowerCase().includes(query) ||
          s.description.toLowerCase().includes(query),
      );
      const mcpServers = useToolsStore.getState().mcpServers;
      const filteredMcp = mcpServers
        .filter(
          (s) =>
            s.name.toLowerCase().includes(query) ||
            (s.description || '').toLowerCase().includes(query),
        )
        .map((s) => ({
          name: s.name,
          description: s.description || `MCP server (${s.tools || s.cached_tools || 0} tools)`,
          isMcp: true as const,
        }));
      return [...filteredBuiltIn, ...filteredSkills, ...filteredMcp];
    },
    [],
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

      // @-mention picker detection. Only fires before any whitespace —
      // matches the / picker semantics. While a mention chip is already
      // active we suppress to avoid double-routing.
      if (!mention && value.startsWith('@') && !value.includes(' ')) {
        setShowMentionPicker(true);
        setMentionPickerIndex(0);
        void refreshMentionData();
      } else {
        setShowMentionPicker(false);
      }
    },
    [getFilteredSkillItems, mention, refreshMentionData],
  );

  const handleSend = useCallback(async () => {
    const content = text.trim();
    if (!content && attachments.length === 0) return;

    // ─── @mention dispatch: route to ACP agent / task ───
    // Wins over every other branch (team / queue / plan / design / normal).
    // Forwards the recent main-chat exchange so the @agent has context.
    if (mention && content) {
      const convId = currentSessionId;
      setText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      // Show the user's message verbatim — the @ chip already conveys
      // routing. Don't prepend "@name " to the bubble; that confuses users
      // into thinking the system added text on their behalf.
      if (convId) {
        useChatStore.getState().addMessage(convId, {
          role: 'user',
          content,
          timestamp: Date.now(),
        });
        // Mark the session as streaming so the input lock + status bar
        // accurately reflect that the @agent is working. Without this the
        // UI would let the user fire another send while ACP is still
        // pending, racing the response back into the wrong place.
        useChatStore.getState().setStreaming(convId, true);
      }
      // Build context: last 8 turns from the runtime, text-only.
      const runtime = convId ? useChatStore.getState().runtimes[convId] : undefined;
      const history = runtime?.messages ?? [];
      const contextMessages = history
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .slice(-9, -1) // exclude the just-added user turn
        .map((m) => ({
          role: m.role,
          content: typeof m.content === 'string'
            ? m.content
            : Array.isArray(m.content)
              ? m.content
                  .map((c: any) => (typeof c === 'string' ? c : c?.text || ''))
                  .filter(Boolean)
                  .join('\n')
              : '',
        }))
        .filter((m) => m.content);
      const cwdForAgent = displayDir || '/tmp';
      const target = mention.kind === 'task'
        ? { task: mention.name }
        : { agent: mention.name };
      try {
        const res = await api.acp.dispatch({
          ...target,
          prompt: content,
          cwd: cwdForAgent,
          springo_session_id: convId || undefined,
          context_messages: contextMessages,
          timeout: 600,
        });
        if (!res.ok || !res.data) {
          throw new Error(res.error || 'Dispatch failed');
        }
        const text = res.data.text || '(agent returned no text)';
        // Tag the bubble so it's clear the response came from the @agent,
        // not from the default Springo model. Compact prefix the user can
        // scan at a glance.
        const tagged = `> via @${mention.label}\n\n${text}`;
        if (convId) {
          useChatStore.getState().addMessage(convId, {
            role: 'assistant',
            content: tagged,
            timestamp: Date.now(),
          });
        }
        // First turn on a fresh agent → got a task name back? Convert the
        // mention so subsequent turns resume the same thread.
        if (mention.kind === 'agent' && res.data.task) {
          setMention({
            kind: 'task',
            name: res.data.task,
            label: res.data.task,
            description: `${mention.name} task`,
            agentName: mention.name,
          });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        useUIStore.getState().showToast(`@${mention.label} failed: ${msg}`, 'error');
      } finally {
        // Always clear the streaming lock — even on error, otherwise the
        // input box stays disabled forever after a failed dispatch.
        if (convId) useChatStore.getState().setStreaming(convId, false);
      }
      return;
    }

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

    // Queue: if streaming (and not team), enqueue instead of blocking
    if (isStreaming && !activeTeamId && content) {
      const atts = attachments.map((a) => ({
        type: a.type,
        data: a.data,
        name: a.name,
        path: a.path,
      }));
      useUIStore.getState().enqueueItem(currentSessionId!, content, atts);
      setText('');
      setAttachments([]);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
      return;
    }

    if (isStreaming) return;

    // /design — send as a design-mode message
    const designMatch = content.match(/^\/design(?:\s+(.+))?/);
    if (designMatch) {
      const designPrompt = designMatch[1]?.trim();
      if (!designPrompt) {
        setText('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';
        return;
      }
      let convId = currentSessionId;
      if (!convId) convId = useSessionStore.getState().createSession();
      setText('');
      setAttachments([]);
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      const currentSettings = useSettingsStore.getState().settings;
      const artifactCtx = buildArtifactContext();
      await useChatStore.getState().sendMessage(convId, designPrompt, [], {
        model: currentSettings.model,
        maxTokens: currentSettings.maxTokens,
        temperature: currentSettings.temperature,
        systemPrompt: currentSettings.systemPrompt,
        compactModel: currentSettings.compactModel,
        thinkingEnabled: currentSettings.thinkingEnabled !== false,
        thinkingEffort: (currentSettings.thinkingEffort as 'low' | 'medium' | 'high' | 'xhigh' | 'max') || 'xhigh',
        sessionId: convId,
        designMode: true,
        ...(artifactCtx ? { designContext: artifactCtx } : {}),
      });
      return;
    }

    // Plan mode: /plan, /ultraplan, bare "ultraplan", or active plan mode via sidebar
    const planMatch = content.match(/^(?:\/(?:plan|ultraplan)|ultraplan)\s+(.+)/);
    const isPlanModeActive = useUIStore.getState().planModeActive;
    const planTask = planMatch ? planMatch[1].trim() : (isPlanModeActive ? content : null);
    if (planTask) {
      setText('');
      setAttachments([]);
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      const currentSettings = useSettingsStore.getState().settings;
      usePlanStore.getState().generatePlan(planTask, currentSessionId || undefined, currentSettings.model);
      return;
    }

    let convId = currentSessionId;
    if (!convId) {
      convId = useSessionStore.getState().createSession();
    }

    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    // Team mode: spawn a new team instead of normal send
    if (teamModeEnabled && content) {
      const currentSettings = useSettingsStore.getState().settings;
      const mode = teamCollaborativeMode ? 'collaborative' : 'classic';
      await useChatStore.getState().sendTeamMessage(convId, content, {
        model: currentSettings.model,
        mode: mode as 'classic' | 'collaborative',
      });
      return;
    }

    const atts = attachments.map((a) => ({
      type: a.type,
      data: a.data,
      name: a.name,
      path: a.path,
    }));

    const currentSettings = useSettingsStore.getState().settings;
    const artifactCtx = buildArtifactContext();
    const artifactPinned = useUnifiedArtifactStore.getState().pinnedElement;

    let finalContent = content;
    if (artifactPinned) {
      finalContent = `[Pinned element: ${artifactPinned.componentName} (${artifactPinned.tagName}) at "${artifactPinned.cssPath}"]\n\n${content}`;
      useUnifiedArtifactStore.getState().clearPin();
    }

    await useChatStore.getState().sendMessage(convId, finalContent, atts, {
      model: currentSettings.model,
      maxTokens: currentSettings.maxTokens,
      temperature: currentSettings.temperature,
      systemPrompt: currentSettings.systemPrompt,
      compactModel: currentSettings.compactModel,
      thinkingEnabled: currentSettings.thinkingEnabled !== false,
      thinkingEffort: (currentSettings.thinkingEffort as 'low' | 'medium' | 'high' | 'xhigh' | 'max') || 'xhigh',
      sessionId: convId,
      ...(artifactCtx ? { designContext: artifactCtx } : {}),
    });

    if (useUIStore.getState().activeSkill) {
      useUIStore.getState().clearActiveSkill();
    }
  }, [text, attachments, isStreaming, currentSessionId, activeTeamId, teamModeEnabled, teamCollaborativeMode, mention, displayDir]);

  const handleStop = useCallback(() => {
    if (currentSessionId) {
      useChatStore.getState().stopTask(currentSessionId);
    }
  }, [currentSessionId]);

  const selectSkill = useCallback(
    (skill: Skill) => {
      // Add as attachment chip (like file drag)
      setAttachments((prev) => [
        ...prev,
        { type: 'skill', name: `/${skill.name}`, path: skill.name },
      ]);
      useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
      setText('');
      setShowSkillPicker(false);
      textareaRef.current?.focus();
    },
    [],
  );

  const selectMcpServer = useCallback(
    (serverName: string) => {
      // Add as attachment chip (like file drag)
      setAttachments((prev) => [
        ...prev,
        { type: 'mcp_server', name: serverName, path: serverName },
      ]);
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

  // @-mention picker items + handlers. Defined before handleKeyDown because
  // the keyboard handler captures them.
  const filteredMentionItems = useMemo<MentionTarget[]>(() => {
    if (!showMentionPicker) return [];
    const q = text.startsWith('@') ? text.substring(1).toLowerCase() : '';
    const taskItems: MentionTarget[] = mentionTasks
      .filter((t) => !q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
      .map((t) => ({
        kind: 'task',
        name: t.name,
        label: t.name,
        description: t.description || `${t.agent_name} task`,
        agentName: t.agent_name,
      }));
    const agentItems: MentionTarget[] = mentionAgents
      .filter((a) => !q || a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q))
      .map((a) => ({
        kind: 'agent',
        name: a.name,
        label: a.name,
        description: a.description,
      }));
    return [...taskItems, ...agentItems];
  }, [showMentionPicker, text, mentionTasks, mentionAgents]);

  const selectMention = useCallback((target: MentionTarget) => {
    setMention(target);
    setShowMentionPicker(false);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  }, []);

  const clearMention = useCallback(() => setMention(null), []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // @-mention picker navigation (mirrors skill picker pattern)
      if (showMentionPicker && filteredMentionItems.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setMentionPickerIndex((prev) => Math.min(prev + 1, filteredMentionItems.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setMentionPickerIndex((prev) => Math.max(prev - 1, 0));
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as KeyboardEvent).isComposing) {
          e.preventDefault();
          const item = filteredMentionItems[mentionPickerIndex];
          if (item) selectMention(item);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowMentionPicker(false);
          return;
        }
      }

      // Backspace at empty prompt with active mention → clear chip
      if (e.key === 'Backspace' && mention && text === '') {
        e.preventDefault();
        clearMention();
        return;
      }

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
            } else if ('isMcp' in item && item.isMcp) {
              selectMcpServer(item.name);
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
    [showSkillPicker, text, getFilteredSkillItems, skillPickerIndex, selectBuiltInCommand, selectSkill, selectMcpServer, isStreaming, handleStop, handleSend, showMentionPicker, filteredMentionItems, mentionPickerIndex, selectMention, mention, clearMention],
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
            reader.onload = async () => {
              const base64 = (reader.result as string).split(',')[1];
              const compressed = await compressImage(base64, file.type);
              setAttachments((prev) => [
                ...prev,
                { name: file.name || 'pasted-image', type: compressed.type, data: compressed.data },
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
        reader.onload = async () => {
          const base64 = (reader.result as string).split(',')[1];
          const compressed = await compressImage(base64, file.type);
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: compressed.type, data: compressed.data },
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

      // Check for skill drop — add as attachment chip
      const skillData = e.dataTransfer.getData('application/x-springo-skill');
      if (skillData) {
        try {
          const skill = JSON.parse(skillData) as { name: string; description: string };
          setAttachments((prev) => [
            ...prev,
            { type: 'skill', name: `/${skill.name}`, path: skill.name },
          ]);
          useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
        } catch { /* ignore */ }
        setTimeout(() => textareaRef.current?.focus(), 0);
        return;
      }

      // Check for MCP server drop — add as attachment chip
      const serverData = e.dataTransfer.getData('application/x-springo-mcp-server');
      if (serverData) {
        try {
          const server = JSON.parse(serverData) as { name: string };
          setAttachments((prev) => [
            ...prev,
            { type: 'mcp_server', name: server.name, path: server.name },
          ]);
        } catch { /* ignore */ }
        setTimeout(() => textareaRef.current?.focus(), 0);
        return;
      }

      // Check for file browser path drop
      const filePath = e.dataTransfer.getData('application/x-springo-filepath');
      if (filePath) {
        const fileName = filePath.split('/').pop() || filePath;
        setAttachments((prev) => [
          ...prev,
          { type: 'file_path', name: fileName, path: filePath },
        ]);
        return;
      }

      // Default: file drop
      const files = Array.from(e.dataTransfer.files);
      processFiles(files);
    },
    [processFiles],
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const toggleTeamMode = useCallback(() => {
    useUIStore.getState().cycleTeamMode();
  }, []);

  // Queue auto-processing: when streaming ends and queue has items, send next
  const prevStreamingRef = useRef(isStreaming);
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current;
    prevStreamingRef.current = isStreaming;

    // Transition: streaming → not streaming
    if (wasStreaming && !isStreaming && currentSessionId) {
      const next = useUIStore.getState().dequeueItem(currentSessionId);
      if (next) {
        // Small delay to let backend finalize
        setTimeout(() => {
          const currentSettings = useSettingsStore.getState().settings;
          useChatStore.getState().sendMessage(currentSessionId, next.content, next.attachments, {
            model: currentSettings.model,
            maxTokens: currentSettings.maxTokens,
            temperature: currentSettings.temperature,
            systemPrompt: currentSettings.systemPrompt,
            compactModel: currentSettings.compactModel,
            thinkingEnabled: currentSettings.thinkingEnabled !== false,
            thinkingEffort: (currentSettings.thinkingEffort as 'low' | 'medium' | 'high' | 'xhigh' | 'max') || 'xhigh',
            sessionId: currentSessionId,
          });
        }, 500);
      }
    }
  }, [isStreaming, currentSessionId]);

  // handleWorkdirChange for the working directory selector
  const handleWorkdirChange = useCallback(
    async (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value;
      if (value === '__add__') {
        if (window.electronAPI?.selectFolder) {
          const result = await window.electronAPI.selectFolder();
          const folders = Array.isArray(result) ? result : result ? [result] : [];
          if (folders.length > 0) {
            const currentFolders = useSettingsStore.getState().workingFolders;
            const updatedFolders = [...currentFolders];
            for (const folder of folders) {
              if (!updatedFolders.includes(folder)) {
                updatedFolders.push(folder);
              }
            }
            useSettingsStore.setState({ workingFolders: updatedFolders });
            setWorkingDir(folders[0]);
          }
        }
        e.target.value = displayDir;
      } else if (value) {
        setWorkingDir(value);
        if (currentSessionId) {
          useSessionStore.setState((state) => ({
            sessions: state.sessions.map((s) =>
              s.id === currentSessionId ? { ...s, workingDir: value } : s,
            ),
          }));
          useSessionStore.getState().updateSessionMetadata(currentSessionId, { workingDir: value });
        }
      }
    },
    [displayDir, setWorkingDir, currentSessionId],
  );

  // Build the filtered skill picker items
  const filteredSkillItems = showSkillPicker
    ? getFilteredSkillItems(text.substring(1).toLowerCase())
    : [];

  // Build the @-mention picker items: tasks first (resume), agents second
  // (start fresh). Filter on the user's @-prefix query.
  const canSend = (text.trim() || attachments.length > 0) && !isStreaming;


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
          <button className="skill-clear" onClick={() => useUIStore.getState().clearActiveSkill()}>
            &times;
          </button>
        </div>
      )}

      {/* Active @mention indicator: locks the next send to the chosen
          ACP task or agent. Same visual slot as the skill chip. */}
      {mention && (
        <div className="active-skill-indicator">
          <span className="skill-badge" style={{ background: 'var(--accent-soft)' }}>
            @{mention.label}
          </span>
          <span className="skill-desc">
            {mention.kind === 'task'
              ? `Resume ${mention.agentName || 'agent'} task`
              : `New thread on ${mention.name}`}
            {mention.description ? ` — ${mention.description.slice(0, 60)}` : ''}
          </span>
          <button className="skill-clear" onClick={clearMention} title="Clear mention (Backspace)">
            &times;
          </button>
        </div>
      )}

      {/* Queue widget */}
      {queueItems.length > 0 && (
        <div className="queue-widget">
          <div className="queue-widget-header">
            <span className="queue-widget-title">Queue ({queueItems.length})</span>
            <button className="queue-widget-clear" onClick={() => currentSessionId && useUIStore.getState().clearQueue(currentSessionId)}>
              Clear
            </button>
          </div>
          <div className="queue-widget-list">
            {queueItems.map((item) => (
              <div key={item.id} className="queue-widget-item">
                <span className="queue-widget-item-text">
                  {item.content.length > 80 ? item.content.slice(0, 80) + '...' : item.content}
                </span>
                <button
                  className="queue-widget-item-remove"
                  onClick={() => currentSessionId && useUIStore.getState().removeQueueItem(currentSessionId, item.id)}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
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
            const isSkill = a.type === 'skill';
            const isMcp = a.type === 'mcp_server';
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
            } else if (isSkill) {
              return (
                <div key={i} className="attachment skill-attachment" title={a.path}>
                  <span className="skill-slash" style={{ fontSize: '12px' }}>/</span>
                  {a.name.replace(/^\//, '')}
                  <span className="remove" onClick={() => { removeAttachment(i); useUIStore.getState().clearActiveSkill(); }}>
                    &times;
                  </span>
                </div>
              );
            } else if (isMcp) {
              return (
                <div key={i} className="attachment mcp-attachment" title={a.path}>
                  <span className="mcp-dot" />
                  {a.name}
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
              mention
                ? `Message @${mention.label}... (Backspace to clear)`
                : activeSkill
                  ? `Using /${activeSkill.name} skill - Enter your request...`
                  : isStreaming && !activeTeamId
                    ? queueItems.length > 0
                      ? `Type to add to queue (${queueItems.length} queued)...`
                      : 'Type to queue next message...'
                    : teamCollaborativeMode
                      ? 'Team Collaborative Mode - agents work together...'
                      : teamModeEnabled
                        ? 'Team Mode - multi-agent collaboration...'
                        : planModeActive
                          ? 'Describe your task — UltraPlan will analyze and create a plan...'
                          : 'Message Springo... (/ for skills, @ for agents)'
            }
            rows={1}
            value={text}
            onChange={handleTextChange}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
          />

          {isStreaming && !activeTeamId ? (
            <>
              <button
                id="stop-btn"
                onClick={handleStop}
                title="Stop (Esc)"
              >
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
              <button
                id="queue-btn"
                className="queue-btn"
                onClick={handleSend}
                disabled={!text.trim() && attachments.length === 0}
                title={queueItems.length > 0 ? `${queueItems.length} in queue` : 'Add to queue — runs after current task'}
              >
                {'\u21B3'} Queue{queueItems.length > 0 ? ` (${queueItems.length})` : ''}
              </button>
            </>
          ) : (
            <button
              id="send-btn"
              onClick={handleSend}
              disabled={!canSend}
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12l5-5 5 5" />
              </svg>
            </button>
          )}
        </div>

        {/* Bottom status row */}
        <div className="bottom-status-row">
          <div className="model-selector-compact" ref={modelPickerRef}>
            <button
              className="model-selector-btn"
              onClick={() => setShowModelPicker((p) => !p)}
              title={`Current model: ${currentModel}`}
            >
              <span className="model-selector-label">{currentModelDisplayName}</span>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.2" fill="none" />
              </svg>
            </button>
            {showModelPicker && (
              <div className="model-picker-dropdown">
                {Object.keys(modelsByProvider).length > 0 ? (
                  Object.entries(modelsByProvider).map(([provider, providerModels]) => (
                    <div key={provider} className="model-picker-group">
                      <div className="model-picker-group-label">{provider}</div>
                      {providerModels.map((m) => (
                        <div
                          key={m.id}
                          className={`model-picker-item${m.id === currentModel ? ' active' : ''}`}
                          onClick={() => handleModelSelect(m.id)}
                        >
                          {(m as unknown as Record<string, string>).display_name || m.name || m.id}
                        </div>
                      ))}
                    </div>
                  ))
                ) : (
                  models.map((m) => (
                    <div
                      key={m.id}
                      className={`model-picker-item${m.id === currentModel ? ' active' : ''}`}
                      onClick={() => handleModelSelect(m.id)}
                    >
                      {m.name || m.id}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
          <ToolsPicker />
          <div style={{ flex: 1 }} />
          <div className="status-workdir-area">
            <span
              className="workdir-path"
              id="workdir-path-display"
              title={displayDir ? `Click to open in Finder: ${displayDir}` : 'Click to select working directory'}
              style={{
                cursor: 'pointer',
                ...(!displayDir ? { color: 'var(--text-tertiary)' } : {}),
              }}
              onClick={() => {
                if (displayDir && window.electronAPI?.openFolder) {
                  window.electronAPI.openFolder(displayDir);
                }
              }}
            >
              {displayDir || '(No working directory)'}
            </span>
            <div className="status-workdir-selector">
              <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <select id="status-workdir-select" value={displayDir} onChange={handleWorkdirChange}>
                {workingFolders.map((folder) => {
                  const name = folder.split('/').pop() || folder;
                  return <option key={folder} value={folder} title={folder}>{name}</option>;
                })}
                {workingFolders.length > 0 && <option disabled>{'──────────'}</option>}
                <option value="__add__">+ Add folder...</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* @-mention picker — same visual class as skill picker so it picks
          up the existing dropdown styling. Two sections: Active Tasks
          (resume) + Coding Agents (start fresh). */}
      {showMentionPicker && filteredMentionItems.length > 0 && (
        <div className="skill-picker" id="mention-picker">
          {filteredMentionItems.some((i) => i.kind === 'task') && (
            <div className="skill-picker-group-label" style={{ padding: '6px 12px 2px', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Active Tasks
            </div>
          )}
          {filteredMentionItems.map((item, idx) => {
            const isFirstAgent = item.kind === 'agent' &&
              (idx === 0 || filteredMentionItems[idx - 1].kind === 'task');
            return (
              <div key={`${item.kind}-${item.name}`}>
                {isFirstAgent && (
                  <div className="skill-picker-group-label" style={{ padding: '6px 12px 2px', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Coding Agents
                  </div>
                )}
                <div
                  className={`skill-picker-item${idx === mentionPickerIndex ? ' active' : ''}`}
                  onClick={() => selectMention(item)}
                >
                  <div className="skill-picker-name">
                    @{item.label}
                    <span className="skill-picker-type-badge skill-badge">
                      {item.kind === 'task' ? 'task' : 'agent'}
                    </span>
                  </div>
                  <div className="skill-picker-desc">
                    {item.description.length > 80
                      ? item.description.substring(0, 80) + '...'
                      : item.description}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Skill picker (appended to input-area, like legacy) */}
      {showSkillPicker && filteredSkillItems.length > 0 && (
        <div className="skill-picker" id="skill-picker">
          {filteredSkillItems.map((item, idx) => {
            const isBuiltIn = 'isBuiltIn' in item && item.isBuiltIn;
            const isMcp = 'isMcp' in item && item.isMcp;
            return (
              <div
                key={item.name + (isBuiltIn ? '-builtin' : isMcp ? '-mcp' : '')}
                className={`skill-picker-item${isBuiltIn ? ' built-in' : ''}${isMcp ? ' mcp-item' : ''}${idx === skillPickerIndex ? ' active' : ''}`}
                onClick={() =>
                  isBuiltIn
                    ? selectBuiltInCommand(item.name)
                    : isMcp
                      ? selectMcpServer(item.name)
                      : selectSkill(item as Skill)
                }
              >
                <div className="skill-picker-name">
                  {isMcp ? item.name : `/${item.name}`}
                  {isBuiltIn && (
                    <span className="skill-picker-type-badge skill-badge">cmd</span>
                  )}
                  {!isBuiltIn && !isMcp && (
                    <span className="skill-picker-type-badge skill-badge">skill</span>
                  )}
                  {isMcp && (
                    <span className="skill-picker-type-badge mcp-badge">mcp</span>
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
