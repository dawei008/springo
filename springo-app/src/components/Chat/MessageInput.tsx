import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import { useToolsStore } from '@/stores/toolsStore';
import { usePlanStore } from '@/stores/planStore';
import { useDesignStore } from '@/stores/designStore';
import { api } from '@/services/api';
import type { Attachment, Skill, UsageData, DesignVersion } from '@/types';
import ToolsPicker from './ToolsPicker';

const BASE_URL = 'http://127.0.0.1:8081';

/** Build design context string for iteration — serializes multi-file projects as springo-file blocks */
function buildDesignContext(design: DesignVersion): string {
  if (design.files && design.files.length > 0) {
    return design.files.map(f =>
      `<springo-file path="${f.path}" type="text/${f.type}">\n${f.content}\n</springo-file>`
    ).join('\n\n');
  }
  return design.html;
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function computeCacheHitRate(usage: UsageData): number | null {
  const { cache_read_input_tokens, cache_creation_input_tokens, input_tokens } = usage;
  // No cache data at all — model doesn't support caching
  if (cache_read_input_tokens === 0 && cache_creation_input_tokens === 0) return null;
  // Anthropic API: input_tokens = non-cached tokens, so total = all three fields
  const total = input_tokens + cache_creation_input_tokens + cache_read_input_tokens;
  if (total === 0) return null;
  return Math.round((cache_read_input_tokens / total) * 100);
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

export default function MessageInput() {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
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

  const [showModelPicker, setShowModelPicker] = useState(false);
  const modelPickerRef = useRef<HTMLDivElement>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const settings = useSettingsStore((s) => s.settings);
  const activeSkill = useUIStore((s) => s.activeSkill);
  const teamModeEnabled = useUIStore((s) => s.teamModeEnabled);
  const teamCollaborativeMode = useUIStore((s) => s.teamCollaborativeMode);
  const activeTeamId = useUIStore((s) => s.activeTeamId);
  const planModeActive = useUIStore((s) => s.planModeActive);
  const queueItems = useUIStore((s) => s.queueItems);

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
    // Shorten the model ID for display
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

  // Memory sync status polling
  useEffect(() => {
    const updateMemorySyncStatus = async () => {
      try {
        const res = await fetch(`${BASE_URL}/v1/memory/status`);
        const data = await res.json();

        // Format last sync time as relative (e.g. "3h ago") or absolute
        const formatSyncTime = (iso: string) => {
          if (!iso) return '';
          const d = new Date(iso + 'Z'); // UTC
          const now = Date.now();
          const diff = now - d.getTime();
          if (diff < 60000) return 'just now';
          if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
          if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
          return `${Math.floor(diff / 86400000)}d ago`;
        };

        const syncTime = data.last_file_sync ? formatSyncTime(data.last_file_sync) : '';
        const filesCount = data.files_synced || 0;

        switch (data.status) {
          case 'synced':
            setSyncStatus('synced');
            setSyncText(syncTime ? `Synced ${syncTime}` : `Synced: ${filesCount} files`);
            break;
          case 'syncing':
            setSyncStatus('syncing');
            setSyncText(`Syncing... (${data.pending} pending)`);
            break;
          case 'disabled':
          case 'not_running':
            setSyncStatus('disabled');
            setSyncText(syncTime ? `Synced ${syncTime}` : 'Memory: off');
            break;
          case 'error':
            setSyncStatus('error');
            setSyncText(syncTime ? `Synced ${syncTime}` : 'Sync paused');
            break;
          default:
            setSyncStatus('disabled');
            setSyncText(syncTime ? `Synced ${syncTime}` : 'Memory: --');
        }

        setSyncTitle(
          `Memory Sync (${data.memory_backend || 'agentcore'})\n` +
          `Status: ${data.status || 'unknown'}\n` +
          `Memory ID: ${data.memory_id || 'N/A'}\n` +
          `Region: ${data.region || 'N/A'}\n` +
          `Files synced: ${filesCount}\n` +
          (syncTime ? `Last sync: ${syncTime}` : ''),
        );
      } catch {
        setSyncStatus('disabled');
        setSyncText('Memory: --');
      }
    };

    updateMemorySyncStatus();
    const interval = setInterval(updateMemorySyncStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // Context indicator: refresh when session changes or streaming ends
  useEffect(() => {
    // Skip refresh while actively streaming — only refresh when it ends
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
            extended_context: settings.enable1mContext === true,
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

    // Design mode: /design activates design mode (with optional initial prompt)
    const designMatch = content.match(/^\/design(?:\s+(.+))?/);
    if (designMatch) {
      const designPrompt = designMatch[1]?.trim();
      let convId = currentSessionId;
      if (!convId) convId = useSessionStore.getState().createSession();
      const { useModeStore } = await import('@/stores/modeStore');
      useModeStore.getState().switchMode('design');
      if (!designPrompt) {
        // Just activate design mode, no message to send
        setText('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';
        return;
      }
      // Fall through with the prompt text — design_mode flag will be attached below
      setText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      // Replace content with just the design prompt for sending
      const designContent = designPrompt;
      setAttachments([]);
      const currentSettings = useSettingsStore.getState().settings;
      const designSystem = useDesignStore.getState().designSystem;
      const prevDesign = useDesignStore.getState().currentDesign();
      const designContext = prevDesign ? buildDesignContext(prevDesign) : undefined;
      await useChatStore.getState().sendMessage(convId, designContent, [], {
        model: currentSettings.model,
        maxTokens: currentSettings.maxTokens,
        temperature: currentSettings.temperature,
        systemPrompt: currentSettings.systemPrompt,
        compactModel: currentSettings.compactModel,
        sessionId: convId,
        designMode: true,
        designSystem: designSystem as unknown as Record<string, unknown> || undefined,
        designContext,
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
    const isDesignMode = useDesignStore.getState().active;
    const designSystem = isDesignMode ? useDesignStore.getState().designSystem : null;
    const prevDesign = isDesignMode ? useDesignStore.getState().currentDesign() : null;
    const designContext = prevDesign ? buildDesignContext(prevDesign) : undefined;
    const selectedEl = isDesignMode ? useDesignStore.getState().selectedElement : null;

    let finalContent = content;
    if (isDesignMode && selectedEl) {
      finalContent = `[User clicked element: <${selectedEl.tagName}> at "${selectedEl.cssPath}"${selectedEl.textPreview ? ` text="${selectedEl.textPreview}"` : ''}${selectedEl.computedStyles ? ` styles=${JSON.stringify(selectedEl.computedStyles)}` : ''}]\n\n${content}`;
      useDesignStore.getState().selectElement(null);
    }

    await useChatStore.getState().sendMessage(convId, finalContent, atts, {
      model: currentSettings.model,
      maxTokens: currentSettings.maxTokens,
      temperature: currentSettings.temperature,
      systemPrompt: currentSettings.systemPrompt,
      compactModel: currentSettings.compactModel,
      sessionId: convId,
      ...(isDesignMode ? {
        designMode: true,
        designSystem: designSystem as unknown as Record<string, unknown> || undefined,
        designContext,
      } : {}),
    });

    if (useUIStore.getState().activeSkill) {
      useUIStore.getState().clearActiveSkill();
    }
  }, [text, attachments, isStreaming, currentSessionId, activeTeamId, teamModeEnabled, teamCollaborativeMode]);

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
    [showSkillPicker, text, getFilteredSkillItems, skillPickerIndex, selectBuiltInCommand, selectSkill, selectMcpServer, isStreaming, handleStop, handleSend],
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
            sessionId: currentSessionId,
          });
        }, 500);
      }
    }
  }, [isStreaming, currentSessionId]);

  // Render context breakdown data into HTML (matching legacy renderContextBreakdown)
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

        // Get messages from chatStore for the request body (matching legacy)
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
            extended_context: settings.enable1mContext === true,
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
    [showContextBreakdown, currentSessionId, settings.model, settings.enable1mContext, renderContextBreakdown],
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

  const canSend = (text.trim() || attachments.length > 0) && !isStreaming;

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
          <button className="skill-clear" onClick={() => useUIStore.getState().clearActiveSkill()}>
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
              activeSkill
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
                        : 'Message Springo... (/ for skills)'
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
          <ToolsPicker />
          {/* Compact model selector */}
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
      </div>

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
