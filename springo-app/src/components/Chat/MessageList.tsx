import { useMemo } from 'react';
import Message from './Message';
import type { DisplayMessage } from './Message';
import type { Message as MessageType, ContentBlock } from '@/types';

/** Extract readable text from message content (string or ContentBlock[]). */
function extractTextContent(content: string | ContentBlock[] | undefined): string {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((c) => {
        if (typeof c === 'string') return c;
        if (c.type === 'text') return c.text || '';
        if (c.type === 'image') return '[Image]';
        if (c.type === 'tool_use') return '';
        if (c.type === 'tool_result') return '';
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

/** Check if a user message only contains tool_result blocks. */
function isToolResultOnlyMessage(m: MessageType): boolean {
  if (m.role !== 'user') return false;
  if (!Array.isArray(m.content)) return false;
  return (m.content as ContentBlock[]).some((c) => c.type === 'tool_result');
}

interface Props {
  messages: MessageType[];
}

export default function MessageList({ messages }: Props) {
  const displayMessages = useMemo(() => {
    // Filter out internal messages for display
    const filtered = messages.filter((m, idx) => {
      // Skip user messages that contain tool_result blocks
      if (isToolResultOnlyMessage(m)) {
        return false;
      }
      // Skip assistant messages that only have tool_use (no text),
      // but don't skip the last message (active streaming message)
      if (m.role === 'assistant' && m.hasToolUse && idx < messages.length - 1) {
        const display = m.displayContent || '';
        if (!display.trim()) return false;
      }
      // Skip thinking indicators
      if (m.isThinking) return false;
      return true;
    });

    // Merge consecutive assistant messages for display
    // BUT don't merge delegation result messages - they should stay separate
    const result: DisplayMessage[] = [];
    for (const m of filtered) {
      const last = result[result.length - 1];
      const shouldMerge =
        m.role === 'assistant' &&
        last?.role === 'assistant' &&
        !m.isDelegationResult &&
        !last.isDelegationResult &&
        !m.isTaskResult &&
        !last.isTaskResult;

      if (shouldMerge) {
        // Merge with previous assistant message - extract text properly
        const prevContent =
          last.mergedContent ||
          extractTextContent(last.displayContent as string | undefined) ||
          extractTextContent(last.content);
        const currContent =
          extractTextContent(m.displayContent as string | undefined) ||
          extractTextContent(m.content);
        if (currContent) {
          last.mergedContent = prevContent + '\n\n' + currContent;
        }
      } else {
        // Add new message (clone to avoid modifying original)
        result.push({ ...m });
      }
    }

    return result;
  }, [messages]);

  return (
    <>
      {displayMessages.map((msg, i) => (
        <Message key={`${msg.timestamp || i}-${i}`} message={msg} />
      ))}
    </>
  );
}
