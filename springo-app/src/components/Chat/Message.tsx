import { useMemo } from 'react';
import Markdown from '@/components/common/Markdown';
import { useUIStore } from '@/stores/uiStore';
import type { Message as MessageType, ContentBlock } from '@/types';

// SVG avatar icons
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
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

interface DisplayMessage extends MessageType {
  mergedContent?: string;
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

  // Build renderable content
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

  if (isThinking) {
    return (
      <div className="message message-assistant thinking">
        <div className="message-header">
          <div className="message-avatar"><DogIcon /></div>
          <span className="message-label">Springo</span>
        </div>
        <div className="message-content">
          <div className="thinking-dots">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
        </div>
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
        {textContent && <Markdown content={textContent} />}
      </div>
    </div>
  );
}
