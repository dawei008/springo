import { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import WelcomeScreen from './WelcomeScreen';
import MessageList from './MessageList';
import ToolPanel from './ToolPanel';
import { useUIStore } from '@/stores/uiStore';
import type { Message } from '@/types';

const EMPTY_MESSAGES: Message[] = [];

export default function ChatArea() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const runtimes = useChatStore((s) => s.runtimes);
  const toolPanelOpen = useUIStore((s) => s.toolPanelOpen);

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
