import { useRef, useEffect, useCallback } from 'react';
import { useVoiceStore } from '@/stores/voiceStore';
import { useSessionStore } from '@/stores/sessionStore';

export default function MeetingPanel() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const partialText = useVoiceStore((s) => s.partialText);
  const transcript = useVoiceStore((s) =>
    currentSessionId ? s.transcripts[currentSessionId] || '' : '',
  );
  const language = useVoiceStore((s) => s.language);

  const contentRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new text arrives
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [transcript, partialText]);

  const handleCopy = useCallback(() => {
    if (transcript) {
      navigator.clipboard.writeText(transcript);
    }
  }, [transcript]);

  const handleClear = useCallback(() => {
    if (currentSessionId) {
      useVoiceStore.getState().clearTranscript(currentSessionId);
    }
  }, [currentSessionId]);

  const handleLangToggle = useCallback(() => {
    const current = useVoiceStore.getState().language;
    const cycle = { zh: 'en', en: 'auto', auto: 'zh' } as Record<string, string>;
    useVoiceStore.getState().setLanguage(cycle[current] || 'auto');
  }, []);

  if (!currentSessionId) {
    return (
      <div className="panel-placeholder">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 10a7 7 0 0 0 14 0" />
          <line x1="12" y1="19" x2="12" y2="22" />
        </svg>
        <span>Start a session to use meeting notes</span>
      </div>
    );
  }

  return (
    <div className="meeting-panel">
      <div className="meeting-toolbar">
        <button
          className={`meeting-lang-btn${language !== 'zh' ? ' en' : ''}`}
          onClick={handleLangToggle}
          title={`Language: ${language === 'zh' ? 'Chinese' : language === 'en' ? 'English' : 'Auto-detect'}`}
        >
          {language === 'zh' ? 'ZH' : language === 'en' ? 'EN' : 'AUTO'}
        </button>
        <div className="meeting-toolbar-spacer" />
        {isTranscribing && (
          <span className="meeting-live-dot" title="Transcribing...">
            LIVE
          </span>
        )}
        <button className="meeting-action-btn" onClick={handleCopy} title="Copy transcript">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
          </svg>
        </button>
        <button className="meeting-action-btn" onClick={handleClear} title="Clear transcript">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
          </svg>
        </button>
      </div>
      <div className="meeting-content" ref={contentRef}>
        {!transcript && !partialText && !isTranscribing && (
          <div className="meeting-empty">
            Click the microphone button in the header to start transcribing.
          </div>
        )}
        {(transcript || partialText) && (
          <div className="meeting-text">
            {transcript}
            {partialText && (
              <span className="meeting-partial">{partialText}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
