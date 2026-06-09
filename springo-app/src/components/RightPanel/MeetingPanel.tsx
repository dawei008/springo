import { useRef, useEffect, useCallback } from 'react';
import { useVoiceStore } from '@/stores/voiceStore';
import { useSessionStore } from '@/stores/sessionStore';

export default function MeetingPanel() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const activeSessionId = useVoiceStore((s) => s.activeSessionId);
  const partialText = useVoiceStore((s) => s.partialText);
  // While a transcription is running, always read from the session the voice
  // store is actually writing to (activeSessionId). This prevents the
  // transcript from "disappearing" if currentSessionId drifts after start
  // (e.g. an internal-artifact open or background session switch). When idle,
  // fall back to the current session so the user sees prior transcripts.
  const readSessionId = (isTranscribing && activeSessionId) || currentSessionId;
  const transcript = useVoiceStore((s) =>
    readSessionId ? s.transcripts[readSessionId] || '' : '',
  );
  const language = useVoiceStore((s) => s.language);

  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [transcript, partialText]);

  const handleTranscribeToggle = useCallback(() => {
    if (isTranscribing) {
      useVoiceStore.getState().stopTranscription();
      return;
    }
    // If there's no current session, spin up a dedicated meeting session so
    // the user can start transcribing from the panel without first creating
    // one in the sidebar.
    let sid = currentSessionId;
    if (!sid) {
      sid = useSessionStore.getState().createSession(undefined, 'meeting');
    }
    useVoiceStore.getState().startTranscription(sid);
  }, [isTranscribing, currentSessionId]);

  const handleCopy = useCallback(() => {
    if (transcript) {
      navigator.clipboard.writeText(transcript);
    }
  }, [transcript]);

  const handleClear = useCallback(() => {
    if (readSessionId) {
      useVoiceStore.getState().clearTranscript(readSessionId);
    }
  }, [readSessionId]);

  const handleLangToggle = useCallback(() => {
    const current = useVoiceStore.getState().language;
    const cycle = { zh: 'en', en: 'auto', auto: 'zh' } as Record<string, string>;
    useVoiceStore.getState().setLanguage(cycle[current] || 'auto');
  }, []);

  if (!currentSessionId) {
    return (
      <div className="meeting-panel">
        <div className="meeting-canvas-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0" />
            <line x1="12" y1="19" x2="12" y2="22" />
          </svg>
          <span>No active session</span>
          <button className="recording-canvas-start-btn" onClick={handleTranscribeToggle}>
            Start Transcription
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="meeting-panel">
      {/* Status + Controls bar */}
      <div className="meeting-canvas-controls">
        <div className="meeting-canvas-status">
          {isTranscribing && <span className="meeting-canvas-dot" />}
          <span className="meeting-canvas-label">
            {isTranscribing ? 'Transcribing' : 'Stopped'}
          </span>
        </div>

        <div className="meeting-canvas-buttons">
          {/* Start / Stop */}
          <button
            className={`meeting-canvas-btn${isTranscribing ? ' meeting-canvas-stop' : ''}`}
            onClick={handleTranscribeToggle}
            title={isTranscribing ? 'Stop transcription' : 'Start transcription'}
          >
            {isTranscribing ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
            )}
            <span>{isTranscribing ? 'Stop' : 'Start'}</span>
          </button>

          {/* Language */}
          <button
            className="meeting-canvas-btn"
            onClick={handleLangToggle}
            title={`Language: ${language === 'zh' ? 'Chinese' : language === 'en' ? 'English' : 'Auto-detect'}`}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span>{language === 'zh' ? 'ZH' : language === 'en' ? 'EN' : 'AUTO'}</span>
          </button>

          {/* Copy */}
          <button
            className="meeting-canvas-btn"
            onClick={handleCopy}
            title="Copy transcript"
            disabled={!transcript}
          >
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            <span>Copy</span>
          </button>

          {/* Clear */}
          <button
            className="meeting-canvas-btn"
            onClick={handleClear}
            title="Clear transcript"
            disabled={!transcript}
          >
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
            </svg>
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Transcript content */}
      <div className="meeting-content" ref={contentRef}>
        {!transcript && !partialText && !isTranscribing && (
          <div className="meeting-canvas-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" />
              <line x1="12" y1="19" x2="12" y2="22" />
            </svg>
            <span>Click Start to begin transcription</span>
          </div>
        )}
        {isTranscribing && !transcript && !partialText && (
          <div className="meeting-canvas-empty">
            <span className="meeting-canvas-dot" />
            <span>Listening...</span>
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
