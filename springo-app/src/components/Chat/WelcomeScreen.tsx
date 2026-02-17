import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';

const suggestions = [
  'Help me write a Python script',
  'Explain a concept in simple terms',
  'Analyze this code for improvements',
  'Help me draft a document',
];

export default function WelcomeScreen() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const settings = useSettingsStore((s) => s.settings);

  const handleSuggestion = async (text: string) => {
    let convId = currentSessionId;
    if (!convId) {
      convId = createSession();
    }
    await sendMessage(convId, text, [], {
      model: settings.model,
      maxTokens: settings.maxTokens,
      temperature: settings.temperature,
      sessionId: convId,
    });
  };

  return (
    <div className="welcome-screen" id="welcome">
      <div className="welcome-icon">
        <svg viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="50" cy="38" rx="22" ry="20" />
          <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55" />
          <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55" />
          <circle cx="40" cy="35" r="3" fill="currentColor" />
          <circle cx="60" cy="35" r="3" fill="currentColor" />
          <ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor" />
          <path d="M45 52 Q50 58, 55 52" />
        </svg>
      </div>
      <h1 className="welcome-title">Springo</h1>
      <p className="welcome-subtitle">AI assistant powered by Amazon Bedrock</p>
      <div className="welcome-suggestions">
        {suggestions.map((s) => (
          <button
            key={s}
            className="suggestion-chip"
            onClick={() => handleSuggestion(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
