import { useMemo, useState, useCallback } from 'react';
import Markdown from '@/components/common/Markdown';
import ArtifactRenderer, { ArtifactInline } from '@/components/Visual/ArtifactRenderer';
import ToolVisualContent from '@/components/Visual/ToolVisualContent';
import { useUIStore } from '@/stores/uiStore';
import type { Message as MessageType, ContentBlock, ToolUseBlock } from '@/types';

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

// ==================== ToolUse type from store ====================

interface ToolUseRuntime {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  status?: 'running' | 'complete' | 'error';
  elapsed?: number;
}

// ==================== ToolCall Component ====================

function ToolCall({ tool }: { tool: ToolUseRuntime }) {
  const [collapsed, setCollapsed] = useState(true);

  const hasResult = tool.result !== undefined && tool.result !== null;
  const hasError = !!(tool.result && (tool.result as Record<string, unknown>).error);

  let statusClass = 'running';
  let statusText = 'Running';
  let statusIcon = '\u21BB'; // ⟳
  if (hasError) {
    statusClass = 'error';
    statusText = 'Error';
    statusIcon = '\u2717'; // ✗
  } else if (hasResult) {
    statusClass = 'success';
    statusText = 'Done';
    statusIcon = '\u2713'; // ✓
  }

  const inputStr = formatToolInput(tool.input || {});
  const outputStr = hasResult ? formatToolOutput(tool.result, hasError) : '';

  const elapsedStr = tool.elapsed ? `${tool.elapsed}s` : '';

  const handleToggle = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  return (
    <div className={`chat-tool-item ${statusClass}`} data-tool-id={tool.id}>
      <div className="chat-tool-header" onClick={handleToggle}>
        <span className="chat-tool-name">{tool.name}</span>
        <span className={`tool-status ${statusClass}`}>
          {statusIcon} {statusText}
          {elapsedStr && <span className="item-elapsed"> ({elapsedStr})</span>}
        </span>
      </div>
      {!collapsed && (
        <div className="chat-tool-body">
          <div className="chat-tool-section">
            <div className="chat-tool-label">Input</div>
            <pre className="chat-tool-code">{escapeHtml(inputStr)}</pre>
          </div>
          {hasResult && (
            <div className="chat-tool-section">
              <div className="chat-tool-label">{hasError ? 'Error' : 'Output'}</div>
              <pre className={`chat-tool-code${hasError ? ' error' : ''}`}>
                {escapeHtml(outputStr)}
              </pre>
            </div>
          )}
        </div>
      )}
      {hasResult && !hasError && <ToolVisualContent toolUse={tool} />}
    </div>
  );
}

// ==================== ToolContainer Component ====================

function ToolContainer({ tools }: { tools: ToolUseRuntime[] }) {
  const [collapsed, setCollapsed] = useState(false);

  if (tools.length === 0) return null;

  const completedCount = tools.filter((t) => t.result !== undefined && t.result !== null).length;
  const allComplete = completedCount === tools.length;

  const handleToggle = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  return (
    <div className={`chat-tool-container${collapsed ? ' collapsed' : ''}`}>
      <div className="chat-tool-header-bar" onClick={handleToggle}>
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
        <span>
          {allComplete
            ? `${completedCount} Tool${completedCount > 1 ? 's' : ''} Completed`
            : `${tools.length} Tool${tools.length > 1 ? 's' : ''} Executed`}
        </span>
      </div>
      {!collapsed && (
        <div className="chat-tool-list">
          {tools.map((tool) => (
            <ToolCall key={tool.id} tool={tool} />
          ))}
        </div>
      )}
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
}

export default function Message({ message }: Props) {
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
  const textContent = useMemo(() => {
    return (
      message.mergedContent ||
      (message.displayContent as string | undefined) ||
      extractTextContent(message.content)
    );
  }, [message.mergedContent, message.displayContent, message.content]);

  // Extract inline images from content blocks
  const imageBlocks = useMemo(() => {
    if (!Array.isArray(message.content)) return [];
    return (message.content as ContentBlock[]).filter((c) => c.type === 'image');
  }, [message.content]);

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
        <div className="message-header">
          <div className="message-avatar"><DogIcon /></div>
          <span className="message-label">Springo</span>
          <span className="thinking">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </span>
        </div>
        <div className="message-content" />
      </div>
    );
  }

  return (
    <div className={`message message-${message.role}${extraClass}`}>
      <div className="message-header">
        <div className="message-avatar">{avatar}</div>
        <span className="message-label">{label}</span>
        {timeStr && <span className="message-time">{timeStr}</span>}
      </div>
      <div className="message-content">
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
            {(cleaned, artifacts) => (
              <>
                <Markdown content={cleaned} />
                {artifacts.map((a) => (
                  <ArtifactInline key={a.id} artifactId={a.id} />
                ))}
              </>
            )}
          </ArtifactRenderer>
        )}
        {toolUses.length > 0 && <ToolContainer tools={toolUses} />}
      </div>
    </div>
  );
}
