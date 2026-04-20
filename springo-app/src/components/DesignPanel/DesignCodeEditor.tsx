/**
 * DesignCodeEditor - read-only code view for the selected file
 */
import { useDesignStore } from '@/stores/designStore';

export default function DesignCodeEditor() {
  const design = useDesignStore((s) => {
    const { versions, activeVersionIndex } = s;
    return activeVersionIndex >= 0 && activeVersionIndex < versions.length
      ? versions[activeVersionIndex]
      : null;
  });
  const activeFilePath = useDesignStore((s) => s.activeFilePath);

  if (!design) return null;

  // For legacy single-HTML designs, show the full HTML
  let content = '';
  let lang = 'html';
  if (design.files && design.files.length > 0) {
    const file = design.files.find(f => f.path === activeFilePath) || design.files[0];
    content = file?.content || '';
    lang = file?.type || 'text';
  } else {
    content = design.html;
  }

  return (
    <div className="design-code-editor">
      {activeFilePath && (
        <div className="design-code-header">
          <span className="design-code-path">{activeFilePath}</span>
          <button
            className="design-code-copy"
            onClick={() => navigator.clipboard.writeText(content)}
            title="Copy to clipboard"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          </button>
        </div>
      )}
      <pre className={`design-code-content language-${lang}`}>
        <code>{content}</code>
      </pre>
    </div>
  );
}
