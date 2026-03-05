import { create } from 'zustand';
import type { Message, ContentBlock } from '@/types';
import { useChatStore } from '@/stores/chatStore';
import { useRecordingStore } from '@/stores/recordingStore';

const BASE_URL = 'http://127.0.0.1:8081';

/** Extract plain text from a message's content (string or ContentBlock[]) */
function extractText(content: string | ContentBlock[]): string {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content
    .filter((b) => b.type === 'text')
    .map((b) => (b as { type: 'text'; text: string }).text)
    .join('');
}

/** Filter messages to only user text + assistant text (skip tool_result, tool_use for clean replay) */
function filterReplayableMessages(messages: Message[]): Message[] {
  return messages.filter((msg) => {
    if (msg.role === 'user') {
      // Only keep user messages that have actual text (not tool_result blocks)
      const content = msg.content;
      if (typeof content === 'string') return content.trim().length > 0;
      if (Array.isArray(content)) {
        return content.some((b) => b.type === 'text');
      }
      return false;
    }
    if (msg.role === 'assistant') {
      // Only keep assistant messages that have text content (not pure tool_use)
      const text = extractText(msg.content);
      return text.trim().length > 0;
    }
    return false;
  });
}

interface ReplayState {
  isReplaying: boolean;
  replaySessionId: string | null;
  allMessages: Message[];
  visibleCount: number;
  speed: number; // 1, 2, 4, 8
  typingProgress: number; // 0-1 for current message typing animation
  typingEnabled: boolean;

  // Internal
  _aborted: boolean;

  // Actions
  startReplay: (sessionId: string, targetSessionId: string) => Promise<void>;
  stopReplay: () => void;
  setSpeed: (speed: number) => void;
}

export const useReplayStore = create<ReplayState>()((set, get) => ({
  isReplaying: false,
  replaySessionId: null,
  allMessages: [],
  visibleCount: 0,
  speed: 1,
  typingProgress: 0,
  typingEnabled: true,
  _aborted: false,

  startReplay: async (sessionId: string, targetSessionId: string) => {
    // Fetch session messages from backend
    let rawMessages: Message[] = [];
    try {
      const res = await fetch(`${BASE_URL}/v1/sessions/${sessionId}`);
      if (!res.ok) {
        console.error('[Replay] Failed to fetch session:', res.status);
        return;
      }
      const data = await res.json();
      rawMessages = data.messages || [];
    } catch (err) {
      console.error('[Replay] Failed to load session:', err);
      return;
    }

    // Filter to only replayable messages (user text + assistant text)
    const messages = filterReplayableMessages(rawMessages);
    console.log(`[Replay] Source session ${sessionId}: ${rawMessages.length} raw → ${messages.length} replayable`);

    if (messages.length === 0) {
      console.warn('[Replay] No replayable messages found');
      return;
    }

    set({
      isReplaying: true,
      replaySessionId: targetSessionId,
      allMessages: messages,
      visibleCount: 0,
      typingProgress: 0,
      _aborted: false,
    });

    // Clear the target session's messages
    const chatStore = useChatStore.getState();
    chatStore.clearMessages(targetSessionId);

    // Load replay settings from cache
    let typingEnabled = true;
    try {
      const raw = await window.electronAPI?.cache?.get('recording') as Record<string, unknown> | null;
      if (raw) {
        typingEnabled = raw.typingAnimation !== false;
      }
    } catch { /* ignore */ }

    // Brief delay to let UI settle before replay starts
    await sleep(300);

    // Replay loop
    const speed = get().speed;
    const baseDelay = 600; // ms between messages

    for (let i = 0; i < messages.length; i++) {
      if (get()._aborted) break;

      const msg = messages[i];
      const text = extractText(msg.content);

      if (msg.role === 'user') {
        // User messages: show text content only, appear instantly
        chatStore.addMessage(targetSessionId, {
          role: 'user',
          content: text,
          timestamp: msg.timestamp || Date.now(),
        });
        set({ visibleCount: i + 1, typingProgress: 1 });
        await sleep(baseDelay / speed);
      } else {
        // Assistant messages: typing animation
        if (typingEnabled && text.length > 0) {
          // Add message with empty content first
          chatStore.addMessage(targetSessionId, {
            role: 'assistant',
            content: '',
            timestamp: msg.timestamp || Date.now(),
          });
          set({ visibleCount: i + 1, typingProgress: 0 });

          // Character-by-character animation
          const charsPerTick = Math.max(2, Math.floor(speed * 5));
          const tickDelay = 16; // ~60fps
          for (let c = charsPerTick; c <= text.length; c += charsPerTick) {
            if (get()._aborted) break;
            chatStore.updateLastAssistantContent(targetSessionId, text.slice(0, c));
            set({ typingProgress: c / text.length });
            await sleep(tickDelay);
          }
          // Ensure full content is set
          chatStore.updateLastAssistantContent(targetSessionId, text);
          set({ typingProgress: 1 });
        } else {
          // Typing disabled: show full text instantly
          chatStore.addMessage(targetSessionId, {
            role: 'assistant',
            content: text,
            timestamp: msg.timestamp || Date.now(),
          });
          set({ visibleCount: i + 1, typingProgress: 1 });
        }

        await sleep(baseDelay / speed);
      }
    }

    // Replay complete — auto-stop recording
    await sleep(1500); // brief pause at end
    if (useRecordingStore.getState().isRecording) {
      await useRecordingStore.getState().stopRecording();
    }

    set({ isReplaying: false });
  },

  stopReplay: () => {
    set({ _aborted: true, isReplaying: false });
    // Stop recording if active
    if (useRecordingStore.getState().isRecording) {
      useRecordingStore.getState().stopRecording();
    }
  },

  setSpeed: (speed: number) => {
    set({ speed });
  },
}));

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
