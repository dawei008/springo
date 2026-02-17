const prompts = [
  {
    title: 'Explain a concept',
    description: 'Quantum computing in simple terms',
    prompt: 'Explain quantum computing in simple terms',
  },
  {
    title: 'Write code',
    description: 'Python function to sort a list',
    prompt: 'Write a Python function to sort a list',
  },
  {
    title: 'Brainstorm ideas',
    description: 'Ideas for a mobile app',
    prompt: 'Help me brainstorm ideas for a mobile app',
  },
  {
    title: 'Summarize a topic',
    description: 'Key points of machine learning',
    prompt: 'Summarize the key points of machine learning',
  },
];

export default function WelcomeScreen() {
  // Legacy behavior: setPrompt() inserts text into the input field and focuses it
  const handlePromptClick = (text: string) => {
    const input = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (input) {
      // Trigger React's onChange by using nativeInputValueSetter
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
      <p>Powered by AWS Bedrock</p>
      <div className="welcome-prompts">
        {prompts.map((item) => (
          <div
            key={item.title}
            className="welcome-prompt"
            onClick={() => handlePromptClick(item.prompt)}
          >
            <h3>{item.title}</h3>
            <p>{item.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
