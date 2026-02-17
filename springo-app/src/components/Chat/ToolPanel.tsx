import { useUIStore } from '@/stores/uiStore';

export default function ToolPanel() {
  const currentToolPanel = useUIStore((s) => s.currentToolPanel);
  const setToolPanelOpen = useUIStore((s) => s.setToolPanelOpen);

  if (!currentToolPanel) return null;

  const { toolName, input, status, result } = currentToolPanel;
  const isRunning = status === 'running';
  const isComplete = status === 'complete';
  const isError = status === 'error';

  return (
    <div className={`tool-panel ${isRunning ? 'running' : ''}`}>
      <div className="tool-panel-header">
        <div className="tool-panel-title">
          <span className={`tool-status-dot ${status}`} />
          <span className="tool-name">{toolName}</span>
        </div>
        <button
          className="tool-panel-close"
          onClick={() => setToolPanelOpen(false)}
          title="Close"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>

      <div className="tool-panel-body">
        <div className="tool-section">
          <div className="tool-section-label">Input</div>
          <pre className="tool-input">
            {JSON.stringify(input, null, 2)}
          </pre>
        </div>

        {isRunning && (
          <div className="tool-progress">
            <div className="tool-progress-bar" />
          </div>
        )}

        {(isComplete || isError) && result && (
          <div className="tool-section">
            <div className="tool-section-label">
              {isError ? 'Error' : 'Result'}
            </div>
            <pre className={`tool-output ${isError ? 'error' : ''}`}>
              {typeof result === 'string'
                ? result
                : JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
