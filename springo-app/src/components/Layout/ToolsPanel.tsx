import { useState, useCallback, useRef } from 'react';
import { useToolsStore } from '@/stores/toolsStore';
import { useUIStore } from '@/stores/uiStore';
import type { Skill } from '@/types';
import type { McpServer, PluginInfo } from '@/stores/toolsStore';

export default function ToolsPanel() {
  const plugins = useToolsStore((s) => s.plugins);
  const skills = useToolsStore((s) => s.skills);
  const mcpServers = useToolsStore((s) => s.mcpServers);

  const [collapsed, setCollapsed] = useState(true);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const totalCount = plugins.length + skills.length + mcpServers.length;

  // ─── Drag handlers ───

  const handleSkillDragStart = useCallback((e: React.DragEvent, skill: Skill) => {
    e.dataTransfer.setData(
      'application/x-springo-skill',
      JSON.stringify({ name: skill.name, description: skill.description }),
    );
    e.dataTransfer.effectAllowed = 'copy';
    setDraggingId(`skill-${skill.name}`);
  }, []);

  const handleServerDragStart = useCallback((e: React.DragEvent, server: McpServer) => {
    e.dataTransfer.setData(
      'application/x-springo-mcp-server',
      JSON.stringify({ name: server.name }),
    );
    e.dataTransfer.effectAllowed = 'copy';
    setDraggingId(`server-${server.name}`);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
  }, []);

  // ─── Click handlers ───

  const handleSkillClick = useCallback((skill: Skill) => {
    useUIStore.getState().setActiveSkill({ name: skill.name, description: skill.description });
  }, []);

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

  const handleServerClick = useCallback((server: McpServer) => {
    insertTextToInput(`Use the ${server.name} MCP server to `);
  }, [insertTextToInput]);

  // Double-click: open the SKILL.md file in the system editor
  const handleSkillDoubleClick = useCallback((skill: Skill) => {
    if (skill.path && window.electronAPI?.openPath) {
      window.electronAPI.openPath(`${skill.path}/SKILL.md`);
    }
  }, []);

  const handleServerDoubleClick = useCallback((server: McpServer) => {
    insertTextToInput(`Use the ${server.name} MCP server to `);
    const wrapper = document.querySelector('.input-area');
    if (wrapper) {
      wrapper.classList.add('drag-over');
      setTimeout(() => wrapper.classList.remove('drag-over'), 400);
    }
  }, [insertTextToInput]);

  const handlePluginDoubleClick = useCallback((plugin: PluginInfo) => {
    if (plugin.path && window.electronAPI?.openPath) {
      window.electronAPI.openPath(plugin.path);
    }
  }, []);

  if (totalCount === 0) return null;

  return (
    <div className={`tools-panel-section${collapsed ? ' collapsed' : ''}`}>
      <div
        className="tools-panel-header"
        onClick={() => setCollapsed((p) => !p)}
      >
        <svg
          className="tools-panel-chevron"
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 1.5L7 5L3 8.5" />
        </svg>
        <span className="tools-panel-title">Tools</span>
        <span className="tools-panel-badge">{totalCount}</span>
      </div>

      <div className="tools-panel-body" ref={listRef}>
        <div className="tools-panel-list">
          {/* Plugins */}
          {plugins.length > 0 && (
            <div className="tools-panel-group">
              <div className="tools-panel-subtitle plugins-subtitle">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 1v4m0 0a3 3 0 100 6 3 3 0 000-6zM6 13h4m-5 0a1.5 1.5 0 01-1.5-1.5V11h9v.5A1.5 1.5 0 0111 13H5z" />
                </svg>
                Plugins
              </div>
              {plugins.map((plugin) => (
                <div
                  key={plugin.name}
                  className="tools-panel-item plugin-item"
                  onDoubleClick={() => handlePluginDoubleClick(plugin)}
                  title={`${plugin.description}${plugin.hooks.length ? ` (${plugin.hooks.length} hooks)` : ''}`}
                >
                  <span className="plugin-icon">⚡</span>
                  <span className="tools-panel-name">{plugin.name}</span>
                  {plugin.hooks.length > 0 && (
                    <span className="server-tools-count">{plugin.hooks.length}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Skills */}
          {skills.length > 0 && (
            <div className="tools-panel-group">
              <div className="tools-panel-subtitle skills-subtitle">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M13 1L8.4 8.2L9.8 9.6L1 15L6.4 6.2L5 4.8Z" />
                </svg>
                Skills
              </div>
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className={`tools-panel-item skill-item${draggingId === `skill-${skill.name}` ? ' dragging' : ''}`}
                  draggable
                  onDragStart={(e) => handleSkillDragStart(e, skill)}
                  onDragEnd={handleDragEnd}
                  onClick={() => handleSkillClick(skill)}
                  onDoubleClick={() => handleSkillDoubleClick(skill)}
                  title={skill.description}
                >
                  <span className="skill-slash">/</span>
                  <span className="tools-panel-name">{skill.name}</span>
                </div>
              ))}
            </div>
          )}

          {/* MCP Servers */}
          {mcpServers.length > 0 && (
            <div className="tools-panel-group">
              <div className="tools-panel-subtitle mcp-subtitle">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="1" y="2" width="14" height="4" rx="1" />
                  <rect x="1" y="10" width="14" height="4" rx="1" />
                  <circle cx="4" cy="4" r="0.8" fill="currentColor" />
                  <circle cx="4" cy="12" r="0.8" fill="currentColor" />
                </svg>
                MCP Servers
              </div>
              {mcpServers.map((server) => (
                <div
                  key={server.name}
                  className={`tools-panel-item server-item${draggingId === `server-${server.name}` ? ' dragging' : ''}`}
                  draggable
                  onDragStart={(e) => handleServerDragStart(e, server)}
                  onDragEnd={handleDragEnd}
                  onClick={() => handleServerClick(server)}
                  onDoubleClick={() => handleServerDoubleClick(server)}
                  title={server.description || server.name}
                >
                  <span className={`server-status-dot${server.running ? ' running' : ''}`} />
                  <span className="tools-panel-name">{server.name}</span>
                  {(server.tools > 0 || server.cached_tools > 0) && (
                    <span className="server-tools-count">
                      {server.tools || server.cached_tools}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
