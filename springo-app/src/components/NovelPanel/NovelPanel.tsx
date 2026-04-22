/**
 * NovelPanel — right-side panel for novel-writing mode.
 * Two-column layout: NovelSidebar (chapters/characters/world/timeline) + NovelEditor (textarea).
 * Visibility is driven by novelStore.active, mirroring DesignPanel / PlanPanel pattern.
 */
import { useEffect, useRef, useState } from 'react';
import { useNovelStore } from '@/stores/novelStore';
import { useSessionStore } from '@/stores/sessionStore';
import NovelSidebar from './NovelSidebar';
import NovelEditor from './NovelEditor';

export default function NovelPanel() {
  const active = useNovelStore((s) => s.active);
  const project = useNovelStore((s) => s.project);
  const workingDir = useNovelStore((s) => s.workingDir);
  const setProjectMeta = useNovelStore((s) => s.setProjectMeta);
  const saveToDisk = useNovelStore((s) => s.saveToDisk);
  const exportAsMarkdown = useNovelStore((s) => s.exportAsMarkdown);
  const deactivate = useNovelStore((s) => s.deactivateNovelMode);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));
  const [showSynopsis, setShowSynopsis] = useState(false);

  const totalWords = Object.values(project.chapters).reduce((sum, c) => sum + (c?.wordCount || 0), 0);

  const panelRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  // Initial load: when panel activates and we have a workingDir, try to hydrate from disk
  useEffect(() => {
    if (!active) return;
    const wd = workingDir || session?.workingDir;
    if (wd && wd !== workingDir) {
      useNovelStore.setState({ workingDir: wd });
      useNovelStore.getState().loadFromDisk(wd).catch(() => {});
    } else if (wd && project.chapterOrder.length === 0 && !useNovelStore.getState().isLoading) {
      useNovelStore.getState().loadFromDisk(wd).catch(() => {});
    }
  }, [active, workingDir, session?.workingDir, project.chapterOrder.length]);

  // Resize handle — mirrors DesignPanel implementation
  useEffect(() => {
    const handle = resizeRef.current;
    const panel = panelRef.current;
    if (!handle || !panel) return;

    let dragging = false;
    let startX = 0;
    let startW = 0;

    const onDown = (e: MouseEvent) => {
      dragging = true;
      startX = e.clientX;
      startW = panel.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    };
    const onMove = (e: MouseEvent) => {
      if (!dragging) return;
      const diff = startX - e.clientX;
      const maxW = Math.floor(window.innerWidth * 0.8);
      const w = Math.min(maxW, Math.max(480, startW + diff));
      panel.style.flex = 'none';
      panel.style.width = w + 'px';
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    handle.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      handle.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  if (!active) return null;

  return (
    <div className="novel-panel" ref={panelRef}>
      <div className="novel-resize-handle" ref={resizeRef} />
      <div className="novel-panel-header">
        <input
          type="text"
          className="novel-project-title"
          value={project.title}
          onChange={(e) => setProjectMeta({ title: e.target.value })}
          placeholder="小说标题"
        />
        <span className="novel-total-words" title="全书字数">
          {totalWords.toLocaleString()} 字
        </span>
        <div className="novel-panel-toolbar">
          {!workingDir && !session?.workingDir && (
            <span className="novel-warning" title="当前会话未设置工作目录，内容无法自动保存到磁盘">
              ⚠ 未设工作目录
            </span>
          )}
          <button
            className={`novel-toolbar-btn${showSynopsis ? ' active' : ''}`}
            onClick={() => setShowSynopsis((v) => !v)}
            title="编辑梗概"
          >
            ☰ 梗概
          </button>
          <button
            className="novel-toolbar-btn"
            onClick={async () => {
              const path = await exportAsMarkdown();
              if (path) alert(`已导出到：${path}`);
              else alert('没有设置工作目录，无法导出');
            }}
            title="导出整本小说为单个 Markdown 文件"
          >
            ↗ 导出
          </button>
          <button
            className="novel-toolbar-btn"
            onClick={() => saveToDisk().catch(() => {})}
            title="立即保存"
          >
            ⬇
          </button>
          <button
            className="novel-toolbar-btn"
            onClick={deactivate}
            title="关闭 Novel 面板"
          >
            ×
          </button>
        </div>
      </div>
      {showSynopsis && (
        <div className="novel-synopsis-editor">
          <textarea
            value={project.synopsis}
            onChange={(e) => setProjectMeta({ synopsis: e.target.value })}
            placeholder="写一段梗概（一句话或一段话概括全书），AI 在续写和改写时会自动参考此处。"
            rows={4}
          />
        </div>
      )}
      <div className="novel-panel-body">
        <NovelSidebar />
        <NovelEditor />
      </div>
    </div>
  );
}
