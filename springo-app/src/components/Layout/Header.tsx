import { useSettingsStore } from '@/stores/settingsStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import type { ConversationStatus } from '@/types';

function StatusIndicator({ status }: { status: ConversationStatus }) {
  const labels: Record<string, string> = {
    idle: 'Ready',
    running: 'Running',
    completed: 'Completed',
    error: 'Error',
    compacting: 'Compacting',
  };

  return (
    <div className={`status-indicator ${status}`}>
      <span className="status-dot" />
      <span className="status-text">{labels[status] || 'Ready'}</span>
    </div>
  );
}

export default function Header() {
  const models = useSettingsStore((s) => s.models);
  const modelsByProvider = useSettingsStore((s) => s.modelsByProvider);
  const settings = useSettingsStore((s) => s.settings);
  const saveSettings = useSettingsStore((s) => s.saveSettings);
  const workingDir = useSettingsStore((s) => s.workingDir);
  const setWorkingDir = useSettingsStore((s) => s.setWorkingDir);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === s.currentSessionId),
  );

  const isStreaming = useChatStore((s) =>
    currentSessionId ? s.isStreaming(currentSessionId) : false,
  );

  const status: ConversationStatus = isStreaming
    ? 'running'
    : session?.status || 'idle';

  const currentModel = settings.model || 'claude-opus-4-6';

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    saveSettings({ model: e.target.value });
  };

  const handleSelectFolder = async () => {
    if (window.electronAPI?.selectFolder) {
      const folder = await window.electronAPI.selectFolder();
      if (folder) {
        setWorkingDir(folder);
      }
    }
  };

  const hasProviders = Object.keys(modelsByProvider).length > 0;

  return (
    <div className="header">
      <div className="header-left">
        <select
          className="model-selector"
          value={currentModel}
          onChange={handleModelChange}
        >
          {hasProviders
            ? Object.entries(modelsByProvider).map(([provider, providerModels]) => (
                <optgroup key={provider} label={provider}>
                  {providerModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name || m.id}
                    </option>
                  ))}
                </optgroup>
              ))
            : models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || m.id}
                </option>
              ))}
        </select>
        <StatusIndicator status={status} />
      </div>

      <div className="header-center">
        {workingDir && (
          <button
            className="working-dir-btn"
            onClick={handleSelectFolder}
            title="Click to change working directory"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span className="working-dir-path">{workingDir}</span>
          </button>
        )}
      </div>

      <div className="header-right">
        <button
          className="settings-btn"
          onClick={() => setSettingsOpen(true)}
          title="Settings"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
