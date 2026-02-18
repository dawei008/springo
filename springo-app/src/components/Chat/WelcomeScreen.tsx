const prompts = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" />
        <path d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    ),
    title: 'Use MCP tools',
    description: 'Search the web, read docs, query databases',
    prompt: 'What MCP tools are available? Show me what each server can do.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 00-3-3.87" />
        <path d="M16 3.13a4 4 0 010 7.75" />
      </svg>
    ),
    title: 'Multi-agent team',
    description: 'Enable Team Mode for complex tasks',
    prompt: 'Help me architect a new microservice. Use team mode to research, design, and review in parallel.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
    title: 'Analyze code',
    description: 'Review, refactor, or explain a codebase',
    prompt: 'Analyze the current working directory. Give me a project overview, key patterns, and any issues you spot.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
    title: 'Draft a document',
    description: 'Write reports, specs, or documentation',
    prompt: 'Help me write a technical design document for ',
  },
];

export default function WelcomeScreen() {
  const handlePromptClick = (text: string) => {
    const input = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (input) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      if (nativeInputValueSetter) {
        nativeInputValueSetter.call(input, text);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      input.focus();
    }
  };

  return (
    <div className="welcome" id="welcome">
      <div className="welcome-glow" />
      <svg
        className="welcome-icon"
        viewBox="0 0 100 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* Head */}
        <ellipse cx="50" cy="38" rx="22" ry="20" />
        {/* Left ear (floppy) */}
        <path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55" />
        {/* Right ear (floppy) */}
        <path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55" />
        {/* Eyes */}
        <circle cx="40" cy="35" r="3" fill="currentColor" />
        <circle cx="60" cy="35" r="3" fill="currentColor" />
        {/* Nose */}
        <ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor" />
        {/* Mouth */}
        <path d="M45 52 Q50 58, 55 52" />
        {/* Body hint */}
        <path d="M35 56 Q50 65, 65 56" />
      </svg>
      <h1>Springo</h1>
      <p>Your AI assistant, powered by AWS Bedrock</p>
      <div className="welcome-prompts">
        {prompts.map((item, idx) => (
          <div
            key={item.title}
            className="welcome-prompt"
            onClick={() => handlePromptClick(item.prompt)}
            style={{ animationDelay: `${idx * 80 + 200}ms` }}
          >
            <div className="welcome-prompt-icon">{item.icon}</div>
            <div className="welcome-prompt-text">
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
