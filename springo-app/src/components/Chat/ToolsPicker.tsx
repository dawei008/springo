import { useState, useRef, useEffect, useCallback } from 'react';
import { useToolsStore } from '@/stores/toolsStore';
import { useUIStore } from '@/stores/uiStore';
import type { Skill } from '@/types';
import type { McpServer, PluginInfo } from '@/stores/toolsStore';

export default function ToolsPicker() {
  const plugins = useToolsStore((s) => s.plugins);
  const skills = useToolsStore((s) => s.skills);
  const mcpServers = useToolsStore((s) => s.mcpServers);

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const totalCount = plugins.length + skills.length + mcpServers.length;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const insertTextToInput = useCallback((text: string) => {
    const input = document.getElementById('message-input') as HTMLTextAreaElement | null;
    if (input) {
      input.focus();
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      if (nativeSetter) {
        nativeSetter.call(input, text);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      input.selectionStart = input.selectionEnd = text.length;
    }
  }, []);

  const handleSkillClick = useCallback((skill: Skill) => {
    useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
    setOpen(false);
  }, []);

  const handleServerClick = useCallback((server: McpServer) => {
    insertTextToInput(`Use the ${server.name} MCP server to `);
    setOpen(false);
  }, [insertTextToInput]);

  const handlePluginDoubleClick = useCallback((plugin: PluginInfo) => {
    if (plugin.path && window.electronAPI?.openPath) {
      window.electronAPI.openPath(plugin.path);
    }
  }, []);

  const handleSkillDoubleClick = useCallback((skill: Skill) => {
    if (skill.path && window.electronAPI?.openPath) {
      window.electronAPI.openPath(`${skill.path}/SKILL.md`);
    }
  }, []);

  if (totalCount === 0) return null;

  return (
    <div className="tools-picker-compact" ref={rootRef}>
      <button
        className="tools-picker-btn"
        onClick={() => setOpen((p) => !p)}
        title={`${totalCount} tools available`}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
        <span className="tools-picker-label">Tools</span>
        <span className="tools-picker-count">{totalCount}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
          <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.2" fill="none" />
        </svg>
      </button>

      {open && (
        <div className="tools-picker-dropdown">
          {plugins.length > 0 && (
            <div className="tools-picker-group">
              <div className="tools-picker-group-label">Plugins</div>
              {plugins.map((plugin) => (
                <div
                  key={plugin.name}
                  className="tools-picker-item"
                  onDoubleClick={() => handlePluginDoubleClick(plugin)}
                  title={plugin.description}
                >
                  <span className="tools-picker-icon plugin-icon">⚡</span>
                  <span className="tools-picker-name">{plugin.name}</span>
                  {plugin.hooks.length > 0 && (
                    <span className="tools-picker-badge">{plugin.hooks.length}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {skills.length > 0 && (
            <div className="tools-picker-group">
              <div className="tools-picker-group-label">Skills</div>
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className="tools-picker-item"
                  onClick={() => handleSkillClick(skill)}
                  onDoubleClick={() => handleSkillDoubleClick(skill)}
                  title={skill.description}
                >
                  <span className="tools-picker-icon skill-slash">/</span>
                  <span className="tools-picker-name">{skill.name}</span>
                </div>
              ))}
            </div>
          )}

          {mcpServers.length > 0 && (
            <div className="tools-picker-group">
              <div className="tools-picker-group-label">MCP Servers</div>
              {mcpServers.map((server) => (
                <div
                  key={server.name}
                  className="tools-picker-item"
                  onClick={() => handleServerClick(server)}
                  title={server.description || server.name}
                >
                  <span className={`tools-picker-icon server-status-dot${server.running ? ' running' : ''}`} />
                  <span className="tools-picker-name">{server.name}</span>
                  {(server.tools > 0 || server.cached_tools > 0) && (
                    <span className="tools-picker-badge">
                      {server.tools || server.cached_tools}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
