/**
 * NovelPanel — right-side panel for novel-writing mode.
 * Two-column layout: NovelSidebar (chapters/characters/world/timeline) + NovelEditor (textarea).
 * Visibility is driven by novelStore.active, mirroring DesignPanel / PlanPanel pattern.
 */
import { useEffect, useRef } from 'react';
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
  const deactivate = useNovelStore((s) => s.deactivateNovelMode);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));

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
        <div className="novel-panel-toolbar">
          {!workingDir && !session?.workingDir && (
            <span className="novel-warning" title="当前会话未设置工作目录，内容无法自动保存到磁盘">
              ⚠ 未设工作目录
            </span>
          )}
          <button
            className="novel-toolbar-btn"
            onClick={() => saveToDisk().catch(() => {})}
            title="保存"
          >
            ⬇
          </button>
          <button
            className="novel-toolbar-btn"
            onClick={deactivate}
            title="关闭 Novel 模式"
          >
            ×
          </button>
        </div>
      </div>
      <div className="novel-panel-body">
        <NovelSidebar />
        <NovelEditor />
      </div>
    </div>
  );
}
