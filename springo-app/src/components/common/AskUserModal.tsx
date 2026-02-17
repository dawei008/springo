import { useState, useCallback, useRef, useEffect } from 'react';
import { useUIStore } from '@/stores/uiStore';

export default function AskUserModal() {
  const askUserData = useUIStore((s) => s.askUserData);
  const hideAskUser = useUIStore((s) => s.hideAskUser);
  const [customInput, setCustomInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (askUserData && inputRef.current) {
      inputRef.current.focus();
    }
  }, [askUserData]);

  const handleSelect = useCallback(
    (answer: string) => {
      if (!askUserData) return;
      askUserData.resolve(answer);
      hideAskUser();
      setCustomInput('');
    },
    [askUserData, hideAskUser],
  );

  const handleCustomSubmit = useCallback(() => {
    if (customInput.trim()) {
      handleSelect(customInput.trim());
    }
  }, [customInput, handleSelect]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && customInput.trim()) {
        handleCustomSubmit();
      }
    },
    [customInput, handleCustomSubmit],
  );

  if (!askUserData) return null;

  return (
    <div className="ask-user-modal active" id="ask-user-modal">
      <div className="ask-user-content">
        <div className="ask-user-header">
          <h3>Question</h3>
          <p className="ask-user-question">{askUserData.question}</p>
        </div>
        <div className="ask-user-options">
          {askUserData.options.map((opt, i) => (
            <button
              key={i}
              className="ask-user-option"
              onClick={() => handleSelect(opt.label)}
            >
              <div className="option-label">{opt.label}</div>
              {opt.description && <div className="option-desc">{opt.description}</div>}
            </button>
          ))}
        </div>
        {askUserData.allowCustom && (
          <div className="ask-user-custom">
            <input
              ref={inputRef}
              type="text"
              placeholder="Or type your own answer..."
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
        )}
      </div>
    </div>
  );
}
