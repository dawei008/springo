import { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import Markdown from '@/components/common/Markdown';
import ArtifactRenderer, { extractModelArtifacts, parseSpringoFiles } from '@/components/Visual/ArtifactRenderer';
import { hasPatch, parsePatch, hasAction, parseAction } from '@/utils/artifactPatcher';
import ToolVisualContent from '@/components/Visual/ToolVisualContent';
import ArtifactCard from '@/components/ArtifactPanel/ArtifactCard';
import { useArtifactStore, createArtifactId } from '@/stores/artifactStore';
import type { ArtifactType } from '@/stores/artifactStore';
import { useUnifiedArtifactStore } from '@/stores/unifiedArtifactStore';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useTeamStore } from '@/stores/teamStore';
import type { Message as MessageType, ContentBlock, ToolUseBlock } from '@/types';

const PATH_KEYS = ['file_path', 'filePath', 'path', 'output_path', 'outputPath', 'filename'];

// ==================== SVG Avatar Icons ====================

const DogIcon = () => (
  <svg viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <ellipse cx="50" cy="38" rx="22" ry="20" />
    <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55" />
    <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55" />
    <circle cx="40" cy="35" r="3" fill="currentColor" />
    <circle cx="60" cy="35" r="3" fill="currentColor" />
    <ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor" />
    <path d="M45 52 Q50 58, 55 52" />
  </svg>
);

const UserIcon = () => (
  <svg viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="50" cy="35" r="18" />
    <path d="M20 90 C20 65 35 55 50 55 C65 55 80 65 80 90" />
  </svg>
);

const DelegationIcon = () => (
  <svg viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M70 30 L30 50 L70 70" />
    <path d="M30 50 L80 50" />
  </svg>
);

const TaskIcon = () => (
  <svg viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <rect x="20" y="15" width="60" height="70" rx="5" />
    <line x1="35" y1="35" x2="65" y2="35" />
    <line x1="35" y1="50" x2="65" y2="50" />
    <line x1="35" y1="65" x2="55" y2="65" />
  </svg>
);

// ==================== Helpers ====================

function formatTimestamp(ts?: number): string {
  if (!ts) return '';
  const date = new Date(ts);
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  if (isToday) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  return (
    date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
    ' ' +
    date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  );
}

function extractTextContent(content: string | ContentBlock[] | undefined): string {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((c) => {
        if (typeof c === 'string') return c;
        if (c.type === 'text') return c.text || '';
        if (c.type === 'image') return '';
        if (c.type === 'tool_use') return '';
        if (c.type === 'tool_result') return '';
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

/**
 * Detect skill-wrapped user messages and extract the user's actual request.
 * Format: <skill name="xxx">...instructions...</skill>\n\nUser request: ...\n\nPlease follow...
 * Returns { skillName, userText } or null if not a skill message.
 */
function parseSkillMessage(text: string): { skillName: string; userText: string } | null {
  const match = text.match(/^<skill\s+name="([^"]+)">/);
  if (!match) return null;
  const skillName = match[1];
  // Extract the "User request: ..." portion after </skill>
  const afterSkill = text.replace(/^<skill[^>]*>[\s\S]*?<\/skill>\s*/, '');
  const userRequest = afterSkill
    .replace(/^User request:\s*/i, '')
    .replace(/\s*Please follow the skill instructions above.*$/s, '')
    .trim();
  return { skillName, userText: userRequest || `/${skillName}` };
}

function extractToolUseBlocks(content: string | ContentBlock[] | undefined): ToolUseBlock[] {
  if (!content || !Array.isArray(content)) return [];
  return content.filter((c): c is ToolUseBlock => c.type === 'tool_use');
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatToolInput(input: Record<string, unknown>): string {
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

function formatToolOutput(result: Record<string, unknown> | null | undefined, isError: boolean): string {
  if (result === undefined || result === null) return '';
  try {
    const data = isError ? (result as Record<string, unknown>).error : result;
    let str = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    if (str.length > 2000) {
      str = str.substring(0, 2000) + '\n... (truncated)';
    }
    return str;
  } catch {
    return String(result);
  }
}

// ==================== Clickable file paths in pre blocks ====================

const FILE_PATH_RE = /((?:\/[\w.+@-]+){2,}(?:\.[\w]+)?|~\/[\w.+@/-]+)/g;

function renderWithClickablePaths(text: string): React.ReactNode[] {
  const escaped = escapeHtml(text);
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  // Re-run regex on escaped text — file paths don't contain HTML special chars
  FILE_PATH_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = FILE_PATH_RE.exec(escaped)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`t-${lastIndex}`} dangerouslySetInnerHTML={{ __html: escaped.slice(lastIndex, match.index) }} />);
    }
    const path = match[1];
    parts.push(
      <span
        key={`p-${match.index}`}
        className="clickable-path"
        title={`Open ${path}`}
        onClick={() => window.electronAPI?.openPath(path)}
      >
        {path}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (parts.length === 0) {
    return [<span key="all" dangerouslySetInnerHTML={{ __html: escaped }} />];
  }
  if (lastIndex < escaped.length) {
    parts.push(<span key={`t-${lastIndex}`} dangerouslySetInnerHTML={{ __html: escaped.slice(lastIndex) }} />);
  }
  return parts;
}

// ==================== ToolUse type from store ====================

interface ToolUseRuntime {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  status?: 'running' | 'complete' | 'error';
  elapsed?: number;
}

// ==================== Tool Detail Modal ====================

function ToolDetailModal({ tool, onClose }: { tool: ToolUseRuntime; onClose: () => void }) {
  const hasResult = tool.result !== undefined && tool.result !== null;
  const hasError = !!(tool.result && (tool.result as Record<string, unknown>).error);

  const inputStr = formatToolInput(tool.input || {});
  const outputStr = hasResult ? formatToolOutput(tool.result, hasError) : '';

  return (
    <div className="tool-detail-modal active" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="tool-detail-content">
        <div className="tool-detail-header">
          <h3>
            <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            {tool.name}
          </h3>
          <button className="icon-btn" onClick={onClose}>
            <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4l10 10M14 4L4 14" />
            </svg>
          </button>
        </div>
        <div className="tool-detail-body">
          <div className="tool-detail-section">
            <div className="tool-detail-section-label">Input</div>
            <pre>{renderWithClickablePaths(inputStr)}</pre>
          </div>
          {hasResult ? (
            <div className="tool-detail-section">
              <div className="tool-detail-section-label">{hasError ? 'Error' : 'Output'}</div>
              <pre>{renderWithClickablePaths(outputStr)}</pre>
            </div>
          ) : (
            <div className="tool-detail-section">
              <div className="tool-detail-section-label">Status</div>
              <p style={{ color: 'var(--text-secondary)' }}>Running...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ==================== ToolContainer Component (inline-chat-tool-panel style) ====================

function ToolContainer({ tools, isStreaming = false }: { tools: ToolUseRuntime[]; isStreaming?: boolean }) {
  const [collapsed, setCollapsed] = useState(false);
  const [detailTool, setDetailTool] = useState<ToolUseRuntime | null>(null);
  const prevToolCountRef = useRef(0);
  const hasCollapsedRef = useRef(false);
  const listRef = useRef<HTMLDivElement>(null);

  if (tools.length === 0) return null;

  // Determine completion by status field OR result presence
  const isToolDone = (t: ToolUseRuntime) =>
    t.status === 'complete' || t.status === 'error' ||
    (t.result !== undefined && t.result !== null);
  const completedCount = tools.filter(isToolDone).length;
  const allComplete = completedCount === tools.length && tools.length > 0;
  const totalCount = tools.length;

  // Auto-expand when new tools arrive while collapsed during streaming
  useEffect(() => {
    if (tools.length > prevToolCountRef.current && collapsed && isStreaming) {
      setCollapsed(false);
      hasCollapsedRef.current = false;
    }
    prevToolCountRef.current = tools.length;
  }, [tools.length, collapsed, isStreaming]);

  // Auto-collapse when streaming ends and all tools are complete
  // Also handles component remount (mounts with isStreaming=false after sync)
  useEffect(() => {
    if (isStreaming) {
      hasCollapsedRef.current = false;
      return;
    }
    if (allComplete && tools.length > 0 && !hasCollapsedRef.current) {
      const timer = setTimeout(() => {
        setCollapsed(true);
        hasCollapsedRef.current = true;
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, allComplete, tools.length]);

  // Auto-scroll to bottom when new tools arrive or status changes
  useEffect(() => {
    if (!collapsed && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [tools.length, completedCount, collapsed]);

  // Title: show total tool count (keeps incrementing as more tools are added)
  const statusText = allComplete
    ? `${totalCount} tools completed`
    : `Running ${totalCount} tool${totalCount > 1 ? 's' : ''}...`;

  return (
    <>
      <div className={`inline-chat-tool-panel${collapsed ? ' collapsed' : ''}`}>
        <div className="inline-panel-header" onClick={() => setCollapsed((prev) => !prev)}>
          <svg className="inline-panel-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          <span className="inline-panel-status">
            {allComplete ? '\u2713 ' : ''}{statusText}
          </span>
          <svg className="inline-panel-toggle" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
        <div className="inline-panel-list" ref={listRef}>
          {tools.map((tool) => {
            const hasError = tool.status === 'error' || !!(tool.result && (tool.result as Record<string, unknown>).error);
            const done = isToolDone(tool);
            let itemClass = 'running';
            let statusIcon;
            if (hasError) {
              itemClass = 'error';
              statusIcon = (
                <svg className="item-status-icon error" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              );
            } else if (done) {
              itemClass = 'complete';
              statusIcon = (
                <svg className="item-status-icon success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
              );
            } else {
              statusIcon = (
                <svg className="item-status-icon running" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              );
            }

            const paramsStr = JSON.stringify(tool.input || {});
            const truncatedParams = paramsStr.length > 60 ? paramsStr.substring(0, 60) + '...' : paramsStr;

            const elapsedStr = tool.elapsed
              ? (tool.elapsed >= 60 ? `${Math.floor(tool.elapsed / 60)}m ${tool.elapsed % 60}s` : `${tool.elapsed}s`)
              : '';

            return (
              <div
                key={tool.id}
                className={`inline-panel-item ${itemClass}`}
                data-tool-id={tool.id}
                onClick={() => setDetailTool(tool)}
              >
                {statusIcon}
                <span className="item-name">{tool.name}</span>
                {elapsedStr && <span className="item-elapsed">{elapsedStr}</span>}
                <span className="item-params">{truncatedParams}</span>
              </div>
            );
          })}
        </div>
      </div>
      {/* Tool detail modal */}
      {detailTool && <ToolDetailModal tool={detailTool} onClose={() => setDetailTool(null)} />}
    </>
  );
}

// ==================== File Artifact Card (reads fresh from disk on click) ====================

const FILE_PREVIEW_EXTENSIONS: Record<string, ArtifactType> = {
  '.md': 'markdown', '.markdown': 'markdown', '.mdx': 'markdown',
  '.html': 'html', '.htm': 'html', '.svg': 'svg',
  '.txt': 'markdown', '.log': 'markdown',
  '.json': 'markdown', '.yaml': 'markdown', '.yml': 'markdown',
  '.xml': 'markdown', '.csv': 'markdown',
  '.ts': 'markdown', '.tsx': 'markdown', '.js': 'markdown', '.jsx': 'markdown',
  '.py': 'markdown', '.go': 'markdown', '.rs': 'markdown', '.java': 'markdown',
  '.css': 'markdown', '.scss': 'markdown',
  '.sh': 'markdown', '.bash': 'markdown', '.zsh': 'markdown',
  '.toml': 'markdown', '.ini': 'markdown', '.sql': 'markdown',
};

function getFilePreviewType(path: string): ArtifactType | null {
  const ext = path.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase();
  return ext ? FILE_PREVIEW_EXTENSIONS[ext] ?? null : null;
}

/** Artifact card for tool-modified files. Reads latest content from disk on click. */
function FileArtifactCard({ filePath, timestamp }: { filePath: string; timestamp: number }) {
  const type = getFilePreviewType(filePath);
  if (!type) return null;
  const fileName = filePath.split('/').pop() || filePath;
  const ext = filePath.match(/\.[a-z0-9]+$/i)?.[0]?.toLowerCase() || '';

  const handleClick = async () => {
    if (!window.electronAPI?.readFileBase64) return;
    try {
      const result = await window.electronAPI.readFileBase64(filePath);
      if (!result.success || !result.data) return;
      // Decode base64 → binary → UTF-8 (atob alone mangles multi-byte chars like Chinese)
      const binary = atob(result.data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const content = new TextDecoder('utf-8').decode(bytes);

      // HTML files get first-class treatment: route them through the unified
      // artifact store so Canvas renders them with Pin/Version/Open controls.
      // One shared artifact id per file path means re-opening the same file
      // reuses the existing Canvas artifact (and its version history) instead
      // of creating a duplicate.
      if (type === 'html') {
        const stableId = 'file-' + filePath.replace(/[^a-zA-Z0-9]+/g, '-').slice(-48);
        const store = useUnifiedArtifactStore.getState();
        const existing = store.artifacts[stableId];
        if (existing) {
          store.openArtifact(stableId);
          store.applyPatch(stableId, [
            { path: 'index.html', action: 'replace', fileType: 'html', content },
          ]);
        } else {
          store.createArtifact({
            id: stableId,
            name: fileName,
            icon: 'web',
            type: 'app',
            files: [{ path: 'index.html', type: 'html', content }],
          });
        }
        return;
      }

      let finalContent = content;
      if (type === 'markdown' && ext !== '.md' && ext !== '.markdown' && ext !== '.mdx' && ext !== '.txt') {
        finalContent = '```' + ext.replace('.', '') + '\n' + content + '\n```';
      }
      useArtifactStore.getState().openArtifact({
        id: createArtifactId(),
        type,
        title: fileName,
        content: finalContent,
        filePath,
        timestamp: Date.now(),
      });
    } catch { /* ignore */ }
  };

  return (
    <ArtifactCard
      artifact={{
        id: `file-${timestamp}-${fileName}`,
        type,
        title: fileName,
        content: '', // Content loaded on click
        filePath,
        timestamp,
      }}
      onClickOverride={handleClick}
    />
  );
}

// ==================== Excalidraw Link Card ====================

function ExcalidrawLinkCard({ elements }: { elements: unknown }) {
  const handleSave = () => {
    // Build a standard .excalidraw file
    const parsed = typeof elements === 'string' ? JSON.parse(elements as string) : elements;
    const scene = {
      type: 'excalidraw',
      version: 2,
      source: 'springo',
      elements: Array.isArray(parsed) ? parsed : [],
      appState: { viewBackgroundColor: '#ffffff' },
    };
    const blob = new Blob([JSON.stringify(scene, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'excalidraw-diagram.excalidraw';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="tool-visual-content" style={{ padding: '10px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2">
          <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5" />
        </svg>
        <span style={{ flex: 1, color: 'var(--text-primary)', fontSize: 13 }}>
          Excalidraw Diagram
        </span>
        <a
          href="https://excalidraw.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="tool-visual-open"
          title="Open excalidraw.com (import the saved .excalidraw file)"
        >
          excalidraw.com
        </a>
        <button
          className="tool-visual-open"
          onClick={handleSave}
          title="Save as .excalidraw file (can be imported into excalidraw.com)"
        >
          Save .excalidraw
        </button>
      </div>
    </div>
  );
}

// ==================== Ask User Options (inline in chat) ====================

function AskUserOptions({ teamId, agentName, options }: {
  teamId: string;
  agentName: string;
  options: Array<{ label: string; description?: string }>;
}) {
  const [answered, setAnswered] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

  const handleClick = useCallback(async (label: string) => {
    if (answered) return;
    setAnswered(true);
    setSelectedLabel(label);

    // Add user reply to main chat
    const convId = useSessionStore.getState().currentSessionId;
    if (convId) {
      useChatStore.getState().addMessage(convId, {
        role: 'user',
        content: label,
        timestamp: Date.now(),
      });
    }

    // Send to backend
    try {
      await fetch(`http://127.0.0.1:8081/v1/teams/${teamId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: label, recipient: 'team-lead' }),
      });
    } catch (err) {
      console.error('Failed to send ask_user reply:', err);
    }

    useTeamStore.getState().clearAskUser();
  }, [teamId, answered]);

  if (options.length === 0) return null;

  return (
    <div className="team-ask-user-options" style={{ marginTop: 8 }}>
      {options.map((opt) => (
        <button
          key={opt.label}
          className={`team-ask-option${selectedLabel === opt.label ? ' selected' : ''}`}
          disabled={answered}
          title={opt.description || ''}
          onClick={() => handleClick(opt.label)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ==================== Main Message Component ====================

export interface DisplayMessage extends MessageType {
  mergedContent?: string;
  /** Runtime tool uses attached during streaming */
  toolUses?: ToolUseRuntime[];
}

interface Props {
  message: DisplayMessage;
  /** Only the latest assistant message should render the inline tool panel */
  showToolPanel?: boolean;
  /** Whether the session is currently streaming (for tool panel collapse logic) */
  isStreaming?: boolean;
}

export default function Message({ message, showToolPanel = false, isStreaming = false }: Props) {
  const isDelegationResult = message.isDelegationResult || false;
  const isTaskResult = message.isTaskResult || false;
  const isThinking = message.isThinking || false;

  const { avatar, label, extraClass } = useMemo(() => {
    if (isDelegationResult) {
      return { avatar: <DelegationIcon />, label: 'Delegation Result', extraClass: ' delegation-result' };
    }
    if (isTaskResult) {
      return { avatar: <TaskIcon />, label: 'Task Result', extraClass: ' task-result' };
    }
    if (message.role === 'user') {
      return { avatar: <UserIcon />, label: 'You', extraClass: '' };
    }
    return { avatar: <DogIcon />, label: 'Springo', extraClass: '' };
  }, [message.role, isDelegationResult, isTaskResult]);

  const timeStr = formatTimestamp(message.timestamp);

  // Build renderable text content
  const rawText = useMemo(() => {
    return (
      message.mergedContent ||
      (message.displayContent as string | undefined) ||
      extractTextContent(message.content)
    );
  }, [message.mergedContent, message.displayContent, message.content]);

  // Extract model-generated artifacts (<springo-artifact> tags) — pure derivation
  const { textAfterArtifacts, modelArtifacts } = useMemo(() => {
    if (message.role !== 'assistant' || !rawText) return { textAfterArtifacts: rawText, modelArtifacts: [] };
    const { cleaned, artifacts } = extractModelArtifacts(rawText);
    return { textAfterArtifacts: cleaned, modelArtifacts: artifacts };
  }, [message.role, rawText]);

  // Route artifacts/patches/actions to stores (side effects)
  useEffect(() => {
    if (message.role !== 'assistant' || !rawText) return;
    const msgId = (message as any).id || message.timestamp || 0;

    // Route <springo-artifact> to unified store
    if (modelArtifacts.length > 0) {
      for (let ai = 0; ai < modelArtifacts.length; ai++) {
        const a = modelArtifacts[ai];
        const stableId = `art-msg-${msgId}-${ai}`;
        const store = useUnifiedArtifactStore.getState();

        if (store.artifacts[stableId]) continue;

        const files = parseSpringoFiles(a.content);
        if (files.length === 0 && a.content) {
          files.push({ path: 'index.html', type: 'html' as const, content: a.content });
        }
        if (files.length === 0) continue;

        store.createArtifact({
          id: stableId,
          name: a.title || 'Artifact',
          icon: a.icon,
          type: a.artifactType,
          files,
        });
      }
    }

    // Route <springo-patch> to unified store
    if (hasPatch(rawText)) {
      const patch = parsePatch(rawText);
      if (patch && patch.files.length > 0) {
        const uStore = useUnifiedArtifactStore.getState();
        const targetId = patch.artifactId || uStore.activeArtifactId;
        if (targetId && uStore.artifacts[targetId]) {
          const patchKey = `patch-${msgId}`;
          const art = uStore.artifacts[targetId];
          const alreadyApplied = art.versions.some((v) => v.id.includes(patchKey));
          if (!alreadyApplied) {
            uStore.applyPatch(targetId, patch.files);
          }
        }
      }
    }

    // Route <springo-action> to iframe via postMessage
    if (hasAction(rawText)) {
      const action = parseAction(rawText);
      if (action) {
        const uStore = useUnifiedArtifactStore.getState();
        const targetId = action.artifactId || uStore.activeArtifactId;
        if (targetId) {
          const iframe = document.querySelector('.artifact-iframe') as HTMLIFrameElement | null;
          if (iframe?.contentWindow) {
            iframe.contentWindow.postMessage({
              type: 'springo:chat-action',
              payload: action.payload,
            }, '*');
          }
        }
      }
    }
  }, [message.role, rawText, message.timestamp, modelArtifacts]);

  // Detect skill-wrapped user messages
  const skillInfo = useMemo(() => {
    if (message.role !== 'user' || !rawText) return null;
    return parseSkillMessage(rawText);
  }, [message.role, rawText]);

  // For skill messages, show only the user's request; for assistant, use artifact-cleaned text
  const textContent = skillInfo ? skillInfo.userText : (message.role === 'assistant' ? textAfterArtifacts : rawText);

  // Extract inline images from content blocks (user messages only —
  // assistant messages may contain image blocks from tool results synced
  // from the backend; these should NOT be rendered inline in the chat)
  const imageBlocks = useMemo(() => {
    if (message.role !== 'user') return [];
    if (!Array.isArray(message.content)) return [];
    return (message.content as ContentBlock[]).filter((c) => c.type === 'image');
  }, [message.role, message.content]);

  // Extract tool_use blocks from content for rendering tool calls
  const toolUses = useMemo((): ToolUseRuntime[] => {
    // If runtime tool uses are attached (from streaming), use those
    if (message.toolUses && message.toolUses.length > 0) {
      return message.toolUses;
    }
    // Otherwise extract from content blocks
    const toolBlocks = extractToolUseBlocks(message.content);
    if (toolBlocks.length === 0) return [];
    return toolBlocks.map((tb) => ({
      id: tb.id,
      name: tb.name,
      input: tb.input || {},
      status: 'complete' as const,
    }));
  }, [message.toolUses, message.content]);

  // Thinking indicator
  if (isThinking) {
    return (
      <div className="message message-assistant">
        <div className="message-avatar"><DogIcon /></div>
        <div className="message-body">
          <div className="message-header">
            <span className="message-label">Springo</span>
            <span className="thinking">
              <span className="thinking-dot" />
              <span className="thinking-dot" />
              <span className="thinking-dot" />
            </span>
          </div>
          <div className="message-content" />
        </div>
      </div>
    );
  }

  return (
    <div className={`message message-${message.role}${extraClass}`}>
      <div className="message-avatar">{avatar}</div>
      <div className="message-body">
      <div className="message-header">
        <span className="message-label">{label}</span>
        {timeStr && <span className="message-time">{timeStr}</span>}
      </div>
      <div className="message-content">
        {skillInfo && (
          <span className="skill-badge-inline">
            <span className="skill-icon-inline">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
            </span>
            /{skillInfo.skillName}
          </span>
        )}
        {imageBlocks.map((block, idx) => {
          if (block.type !== 'image') return null;
          const src = block.source?.data
            ? `data:${block.source.media_type || 'image/png'};base64,${block.source.data}`
            : undefined;
          return src ? (
            <div key={idx} className="chat-image-container">
              <img
                src={src}
                className="chat-image"
                alt="Uploaded image"
                onClick={() => {
                  useUIStore.getState().setImagePreview(src);
                }}
              />
            </div>
          ) : (
            <div key={idx} className="chat-image-placeholder">[Image loading...]</div>
          );
        })}
        {textContent && (
          <ArtifactRenderer text={textContent}>
            {(cleaned, htmlArtifacts) => (
              <>
                <Markdown content={cleaned} />
                {/* Model-generated artifacts via <springo-artifact> tags */}
                {modelArtifacts.map((a) => (
                  <ArtifactCard
                    key={a.id}
                    artifact={{
                      id: a.id,
                      type: a.type === 'code' ? 'markdown' : a.type,
                      title: a.title,
                      content: a.type === 'code' ? '```\n' + a.content + '\n```' : a.content,
                      timestamp: message.timestamp || Date.now(),
                    }}
                  />
                ))}
                {/* HTML artifacts detected from code fences */}
                {htmlArtifacts.map((a) => (
                  <ArtifactCard
                    key={a.id}
                    artifact={{
                      id: a.id,
                      type: 'html',
                      title: a.title,
                      content: a.html,
                      timestamp: message.timestamp || Date.now(),
                    }}
                  />
                ))}
              </>
            )}
          </ArtifactRenderer>
        )}
        {/* Ask user options — interactive buttons for team_ask_user */}
        {message.askUser && (
          <AskUserOptions
            teamId={message.askUser.teamId}
            agentName={message.askUser.agentName}
            options={message.askUser.options}
          />
        )}
        {toolUses.length > 0 && showToolPanel && <ToolContainer tools={toolUses} isStreaming={isStreaming} />}
        {/* Visual content from tools — show as artifact cards */}
        {toolUses.map((tool) => {
          // Extract file path / URL from tool input+result for card actions
          const { toolFilePath, toolUrl } = (() => {
            let filePath: string | undefined;
            let url: string | undefined;
            const urlKeys = ['url', 'href', 'link'];
            // Check input fields
            const inp = tool.input || {};
            for (const key of PATH_KEYS) {
              const v = inp[key];
              if (typeof v === 'string' && v.startsWith('/')) { filePath = v; break; }
            }
            for (const key of urlKeys) {
              const v = inp[key];
              if (typeof v === 'string' && /^https?:\/\//.test(v)) { url = v; break; }
            }
            // Check result object fields
            if (tool.result && typeof tool.result === 'object' && !Array.isArray(tool.result)) {
              const res = tool.result as Record<string, unknown>;
              if (!filePath) for (const key of PATH_KEYS) {
                const v = res[key];
                if (typeof v === 'string' && v.startsWith('/')) { filePath = v; break; }
              }
              if (!url) for (const key of urlKeys) {
                const v = res[key];
                if (typeof v === 'string' && /^https?:\/\//.test(v)) { url = v; break; }
              }
            }
            // Fallback: scan result string for absolute paths or URLs
            if (!filePath || !url) {
              const rs = typeof tool.result === 'string' ? tool.result : '';
              if (!filePath) {
                const pathMatch = rs.match(/(?:saved|wrote|created|output|file)[^/\n]*?(\/[\w./-]+\.\w{1,10})/i);
                if (pathMatch) filePath = pathMatch[1];
              }
              if (!url) {
                const urlMatch = rs.match(/https?:\/\/[^\s"'<>]+/);
                if (urlMatch) url = urlMatch[0];
              }
            }
            return { toolFilePath: filePath, toolUrl: url };
          })();

          // Draw.io — check both tool.input.content and tool.result for mxGraphModel/mxfile XML
          {
            const inputContent = typeof tool.input?.content === 'string' ? tool.input.content : '';
            const resultStr = typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result || '');
            const haystack = tool.name.includes('drawio') ? (inputContent || resultStr) : resultStr;
            if ((haystack.includes('<mxGraphModel') || haystack.includes('<mxfile')) && haystack.includes('</mx')) {
              const xmlMatch = haystack.match(/<mx(?:GraphModel|file)[\s\S]*?<\/mx(?:GraphModel|file)>/i);
              if (xmlMatch) {
                return (
                  <ArtifactCard
                    key={`vis-${tool.id}`}
                    artifact={{
                      id: `dio-${tool.id}`,
                      type: 'drawio',
                      title: 'Draw.io Diagram',
                      content: xmlMatch[0],
                      filePath: toolFilePath, url: toolUrl,
                      timestamp: message.timestamp || Date.now(),
                    }}
                    defaultCollapsed={!isStreaming}
                  />
                );
              }
            }
          }

          // Excalidraw
          if (tool.name === 'excalidraw__create_view' && tool.input?.elements) {
            return (
              <ArtifactCard
                key={`vis-${tool.id}`}
                artifact={{
                  id: `exc-${tool.id}`,
                  type: 'excalidraw',
                  title: 'Excalidraw Diagram',
                  content: '',
                  elements: tool.input.elements as unknown[],
                  filePath: toolFilePath,
                  timestamp: message.timestamp || Date.now(),
                }}
                defaultCollapsed={!isStreaming}
              />
            );
          }

          const hasResult = tool.result !== undefined && tool.result !== null;
          const hasError = !!(tool.result && (tool.result as Record<string, unknown>).error);
          if (!hasResult || hasError) return null;

          const rs = typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result || '');

          // MCP image blocks
          const mcpContent = tool.result && typeof tool.result === 'object' ? (tool.result as Record<string, unknown>).content : null;
          if (Array.isArray(mcpContent)) {
            const imgBlock = mcpContent.find((b: unknown) => b && typeof b === 'object' && (b as Record<string, unknown>).type === 'image') as Record<string, unknown> | undefined;
            if (imgBlock && typeof imgBlock.data === 'string' && (imgBlock.data as string).length > 50) {
              const mimeType = (imgBlock.mimeType as string) || 'image/png';
              return (
                <ArtifactCard
                  key={`vis-${tool.id}`}
                  artifact={{
                    id: `img-${tool.id}`,
                    type: 'image',
                    title: 'Screenshot',
                    content: `data:${mimeType};base64,${imgBlock.data}`,
                    filePath: toolFilePath,
                    timestamp: message.timestamp || Date.now(),
                  }}
                  defaultCollapsed={!isStreaming}
                />
              );
            }
          }

          // Base64 data URL
          const base64Match = rs.match(/data:(image\/[a-z+]+);base64,([A-Za-z0-9+/=]{50,})/);
          if (base64Match) {
            return (
              <ArtifactCard
                key={`vis-${tool.id}`}
                artifact={{
                  id: `img-${tool.id}`,
                  type: 'image',
                  title: 'Generated Image',
                  content: base64Match[0],
                  filePath: toolFilePath,
                  timestamp: message.timestamp || Date.now(),
                }}
                defaultCollapsed={!isStreaming}
              />
            );
          }

          // SVG
          if (rs.includes('<svg') && rs.includes('</svg>')) {
            const svgMatch = rs.match(/<svg[\s\S]*?<\/svg>/i);
            if (svgMatch) {
              return (
                <ArtifactCard
                  key={`vis-${tool.id}`}
                  artifact={{
                    id: `svg-${tool.id}`,
                    type: 'svg',
                    title: 'SVG Diagram',
                    content: svgMatch[0],
                    filePath: toolFilePath,
                    timestamp: message.timestamp || Date.now(),
                  }}
                  defaultCollapsed={!isStreaming}
                />
              );
            }
          }

          // Image URLs or paths — keep inline for these (they need fetching)
          const hasImageUrl = /(https?:\/\/[^\s"'`]+\.(?:png|jpg|jpeg|gif|svg|webp))/i.test(rs);
          const hasImagePath = /(?<!\w)(\/[^\s"'`,]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp))/i.test(rs);
          if (hasImageUrl || hasImagePath) {
            return <ToolVisualContent key={`vis-${tool.id}`} toolUse={tool} defaultCollapsed={!isStreaming} />;
          }

          return null;
        })}
        {/* Deduplicated file artifact cards for edit/write tools */}
        {(() => {
          const fileModTools = ['edit', 'write_file', 'create_file', 'write', 'str_replace_editor'];
          const seen = new Set<string>();
          const cards: { filePath: string; toolId: string }[] = [];
          for (const tool of toolUses) {
            if (!fileModTools.includes(tool.name)) continue;
            const inp = tool.input || {};
            let fp: string | undefined;
            for (const key of PATH_KEYS) {
              const v = inp[key];
              if (typeof v === 'string' && v.startsWith('/')) { fp = v; break; }
            }
            if (fp && getFilePreviewType(fp) && !seen.has(fp)) {
              seen.add(fp);
              cards.push({ filePath: fp, toolId: tool.id });
            }
          }
          return cards.map(({ filePath, toolId }) => (
            <FileArtifactCard key={`file-${toolId}`} filePath={filePath} timestamp={message.timestamp || Date.now()} />
          ));
        })()}
      </div>
      </div>
    </div>
  );
}
