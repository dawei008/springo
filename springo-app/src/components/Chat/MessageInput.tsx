import { useState, useRef, useCallback, useEffect } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import type { Attachment, Skill } from '@/types';

export default function MessageInput() {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stopTask = useChatStore((s) => s.stopTask);
  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );
  const settings = useSettingsStore((s) => s.settings);
  const activeSkill = useUIStore((s) => s.activeSkill);
  const clearActiveSkill = useUIStore((s) => s.clearActiveSkill);

  // Load available skills on mount
  useEffect(() => {
    fetch('http://127.0.0.1:8081/v1/skills')
      .then((r) => r.json())
      .then((data) => setSkills(data.skills || []))
      .catch(() => {});
  }, []);

  // Auto-resize textarea
  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, []);

  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      setText(value);

      // Skill picker detection
      if (value.startsWith('/') && !value.includes(' ')) {
        const query = value.substring(1).toLowerCase();
        const filtered = skills.filter(
          (s) =>
            s.name.toLowerCase().includes(query) ||
            s.title.toLowerCase().includes(query),
        );
        if (filtered.length > 0) {
          setShowSkillPicker(true);
          setSkillPickerIndex(0);
        } else {
          setShowSkillPicker(false);
        }
      } else {
        setShowSkillPicker(false);
      }
    },
    [skills],
  );

  const handleSend = useCallback(async () => {
    const content = text.trim();
    if (!content && attachments.length === 0) return;
    if (isStreaming) return;

    let convId = currentSessionId;
    if (!convId) {
      convId = createSession();
    }

    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const atts = attachments.map((a) => ({
      type: a.type,
      data: a.data,
      name: a.name,
      path: a.path,
    }));

    await sendMessage(convId, content, atts, {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      systemPrompt: settings.systemPrompt,
      compactModel: settings.compactModel,
      sessionId: convId,
    });

    if (activeSkill) {
      clearActiveSkill();
    }
  }, [
    text,
    attachments,
    isStreaming,
    currentSessionId,
    createSession,
    sendMessage,
    settings,
    activeSkill,
    clearActiveSkill,
  ]);

  const handleStop = useCallback(() => {
    if (currentSessionId) {
      stopTask(currentSessionId);
    }
  }, [currentSessionId, stopTask]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Skill picker navigation
      if (showSkillPicker) {
        const query = text.substring(1).toLowerCase();
        const filtered = skills.filter(
          (s) =>
            s.name.toLowerCase().includes(query) ||
            s.title.toLowerCase().includes(query),
        );
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSkillPickerIndex((prev) => Math.min(prev + 1, filtered.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSkillPickerIndex((prev) => Math.max(prev - 1, 0));
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as KeyboardEvent).isComposing) {
          e.preventDefault();
          if (filtered[skillPickerIndex]) {
            selectSkill(filtered[skillPickerIndex]);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowSkillPicker(false);
          return;
        }
      }

      // Enter to send, Shift+Enter for newline
      // Check isComposing for IME support (Chinese/Japanese input)
      if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as KeyboardEvent).isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [showSkillPicker, text, skills, skillPickerIndex, handleSend],
  );

  const selectSkill = useCallback(
    (skill: Skill) => {
      useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
      setText('');
      setShowSkillPicker(false);
      textareaRef.current?.focus();
    },
    [],
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
            reader.onload = () => {
              const base64 = (reader.result as string).split(',')[1];
              setAttachments((prev) => [
                ...prev,
                { name: file.name || 'pasted-image', type: file.type, data: base64 },
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

  // Handle drag-and-drop
  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1];
          setAttachments((prev) => [
            ...prev,
            { name: file.name, type: file.type, data: base64 },
          ]);
        };
        reader.readAsDataURL(file);
      } else {
        setAttachments((prev) => [
          ...prev,
          { name: file.name, type: file.type, path: (file as File & { path?: string }).path || file.name },
        ]);
      }
    }
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const filteredSkills = showSkillPicker
    ? skills.filter((s) => {
        const query = text.substring(1).toLowerCase();
        return (
          s.name.toLowerCase().includes(query) ||
          s.title.toLowerCase().includes(query)
        );
      })
    : [];

  const canSend = (text.trim() || attachments.length > 0) && !isStreaming;

  return (
    <div
      className="input-area"
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onDrop={handleDrop}
    >
      {activeSkill && (
        <div className="active-skill-indicator">
          <span className="skill-badge">/{activeSkill.name}</span>
          <button className="skill-clear-btn" onClick={clearActiveSkill}>
            &times;
          </button>
        </div>
      )}

      {attachments.length > 0 && (
        <div className="attachments-preview">
          {attachments.map((att, idx) => (
            <div key={idx} className="attachment-item">
              {att.type.startsWith('image/') && att.data ? (
                <img
                  src={`data:${att.type};base64,${att.data}`}
                  alt={att.name}
                  className="attachment-thumb"
                />
              ) : (
                <span className="attachment-name">{att.name}</span>
              )}
              <button className="attachment-remove" onClick={() => removeAttachment(idx)}>
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      {showSkillPicker && filteredSkills.length > 0 && (
        <div className="skill-picker">
          {filteredSkills.map((skill, idx) => (
            <div
              key={skill.name}
              className={`skill-picker-item ${idx === skillPickerIndex ? 'highlighted' : ''}`}
              onClick={() => selectSkill(skill)}
            >
              <span className="skill-name">/{skill.name}</span>
              <span className="skill-description">{skill.description}</span>
            </div>
          ))}
        </div>
      )}

      <div className="input-row">
        <textarea
          ref={textareaRef}
          className="message-input"
          placeholder={activeSkill ? `Describe your task for /${activeSkill.name}...` : 'Type a message...'}
          value={text}
          onChange={handleTextChange}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          rows={1}
        />
        {isStreaming ? (
          <button className="stop-btn" onClick={handleStop} title="Stop">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!canSend}
            title="Send"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
