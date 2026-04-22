/**
 * NovelSidebar — left column of NovelPanel.
 * Four tabs: Chapters / Characters / World / Timeline.
 */
import { useState, useCallback } from 'react';
import { useNovelStore } from '@/stores/novelStore';
import type { Character, WorldEntry, TimelineEvent } from './types';

type Tab = 'chapters' | 'characters' | 'world' | 'timeline';

export default function NovelSidebar() {
  const [tab, setTab] = useState<Tab>('chapters');

  return (
    <div className="novel-sidebar">
      <div className="novel-sidebar-tabs">
        {(['chapters', 'characters', 'world', 'timeline'] as Tab[]).map((t) => (
          <button
            key={t}
            className={`novel-tab${tab === t ? ' active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'chapters' ? '章节' : t === 'characters' ? '人物' : t === 'world' ? '世界观' : '时间线'}
          </button>
        ))}
      </div>
      <div className="novel-sidebar-body">
        {tab === 'chapters' && <ChapterList />}
        {tab === 'characters' && <CharacterList />}
        {tab === 'world' && <WorldList />}
        {tab === 'timeline' && <TimelineList />}
      </div>
    </div>
  );
}

// ─── Chapter list ───

function ChapterList() {
  const chapterOrder = useNovelStore((s) => s.project.chapterOrder);
  const chapters = useNovelStore((s) => s.project.chapters);
  const activeChapterId = useNovelStore((s) => s.activeChapterId);
  const addChapter = useNovelStore((s) => s.addChapter);
  const setActiveChapter = useNovelStore((s) => s.setActiveChapter);
  const deleteChapter = useNovelStore((s) => s.deleteChapter);
  const updateChapter = useNovelStore((s) => s.updateChapter);
  const reorderChapters = useNovelStore((s) => s.reorderChapters);

  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const onDragStart = useCallback((e: React.DragEvent, id: string) => {
    e.dataTransfer.setData('text/plain', id);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent, targetId: string) => {
      e.preventDefault();
      const dragged = e.dataTransfer.getData('text/plain');
      if (!dragged || dragged === targetId) return;
      const next = chapterOrder.filter((x) => x !== dragged);
      const idx = next.indexOf(targetId);
      next.splice(idx, 0, dragged);
      reorderChapters(next);
    },
    [chapterOrder, reorderChapters],
  );

  return (
    <>
      <div className="novel-list-header">
        <span>共 {chapterOrder.length} 章</span>
        <button className="novel-add-btn" onClick={() => addChapter()} title="新增章节">+</button>
      </div>
      <div className="novel-list">
        {chapterOrder.length === 0 && (
          <div className="novel-empty">还没有章节。点击 + 新建第一章。</div>
        )}
        {chapterOrder.map((id) => {
          const ch = chapters[id];
          if (!ch) return null;
          const isActive = id === activeChapterId;
          const isRenaming = renamingId === id;
          return (
            <div
              key={id}
              className={`novel-chapter-item${isActive ? ' active' : ''}`}
              onClick={() => !isRenaming && setActiveChapter(id)}
              draggable={!isRenaming}
              onDragStart={(e) => onDragStart(e, id)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(e, id)}
            >
              <div className="novel-chapter-main">
                {isRenaming ? (
                  <input
                    type="text"
                    className="novel-rename-input"
                    value={renameValue}
                    autoFocus
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => {
                      if (renameValue.trim()) updateChapter(id, { title: renameValue.trim() });
                      setRenamingId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        if (renameValue.trim()) updateChapter(id, { title: renameValue.trim() });
                        setRenamingId(null);
                      } else if (e.key === 'Escape') {
                        setRenamingId(null);
                      }
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <div
                    className="novel-chapter-title"
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(id);
                      setRenameValue(ch.title);
                    }}
                  >
                    {ch.title}
                  </div>
                )}
                <div className="novel-chapter-meta">
                  <span className={`novel-status novel-status-${ch.status}`}>{ch.status}</span>
                  <span>·</span>
                  <span>{ch.wordCount} 字</span>
                </div>
              </div>
              <button
                className="novel-item-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`删除「${ch.title}」？`)) deleteChapter(id);
                }}
                title="删除"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

// ─── Character list ───

function CharacterList() {
  const characters = useNovelStore((s) => s.project.characters);
  const upsert = useNovelStore((s) => s.upsertCharacter);
  const del = useNovelStore((s) => s.deleteCharacter);
  const names = Object.keys(characters);
  const [editing, setEditing] = useState<Character | null>(null);

  return (
    <>
      <div className="novel-list-header">
        <span>共 {names.length} 人</span>
        <button
          className="novel-add-btn"
          onClick={() => setEditing({ name: '', role: '', appearance: '', motivation: '', arc: '', notes: '' })}
        >
          +
        </button>
      </div>
      <div className="novel-list">
        {names.length === 0 && !editing && (
          <div className="novel-empty">暂无人物。AI 可以在对话中帮你创建。</div>
        )}
        {names.map((n) => {
          const c = characters[n];
          return (
            <div key={n} className="novel-card" onClick={() => setEditing({ ...c })}>
              <div className="novel-card-title">{c.name}</div>
              {c.role && <div className="novel-card-sub">{c.role}</div>}
              {c.motivation && <div className="novel-card-body">{c.motivation}</div>}
              <button
                className="novel-item-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`删除人物「${n}」？`)) del(n);
                }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      {editing && (
        <CharacterEditor
          value={editing}
          onClose={() => setEditing(null)}
          onSave={(c) => {
            upsert(c);
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function CharacterEditor({
  value,
  onSave,
  onClose,
}: {
  value: Character;
  onSave: (c: Character) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState(value);
  const field = (k: keyof Character) => ({
    value: (form[k] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm({ ...form, [k]: e.target.value }),
  });
  return (
    <div className="novel-modal-backdrop" onClick={onClose}>
      <div className="novel-modal" onClick={(e) => e.stopPropagation()}>
        <div className="novel-modal-title">人物卡</div>
        <label>姓名<input {...field('name')} /></label>
        <label>身份<input {...field('role')} placeholder="如：侦探 / 反派 / 师妹" /></label>
        <label>外貌<textarea {...field('appearance')} rows={2} /></label>
        <label>动机<textarea {...field('motivation')} rows={2} /></label>
        <label>成长弧<textarea {...field('arc')} rows={2} /></label>
        <label>备注<textarea {...field('notes')} rows={2} /></label>
        <div className="novel-modal-actions">
          <button onClick={onClose}>取消</button>
          <button
            className="primary"
            disabled={!form.name.trim()}
            onClick={() => onSave({ ...form, name: form.name.trim() })}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── World list ───

function WorldList() {
  const worldbuilding = useNovelStore((s) => s.project.worldbuilding);
  const upsert = useNovelStore((s) => s.upsertWorldEntry);
  const del = useNovelStore((s) => s.deleteWorldEntry);
  const topics = Object.keys(worldbuilding);
  const [editing, setEditing] = useState<WorldEntry | null>(null);

  return (
    <>
      <div className="novel-list-header">
        <span>共 {topics.length} 条</span>
        <button
          className="novel-add-btn"
          onClick={() => setEditing({ topic: '', content: '' })}
        >
          +
        </button>
      </div>
      <div className="novel-list">
        {topics.length === 0 && !editing && (
          <div className="novel-empty">世界观条目（魔法体系 / 势力 / 地点 …）</div>
        )}
        {topics.map((t) => {
          const e = worldbuilding[t];
          return (
            <div key={t} className="novel-card" onClick={() => setEditing({ ...e })}>
              <div className="novel-card-title">{e.topic}</div>
              <div className="novel-card-body">{e.content}</div>
              <button
                className="novel-item-delete"
                onClick={(ev) => {
                  ev.stopPropagation();
                  if (confirm(`删除条目「${t}」？`)) del(t);
                }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      {editing && (
        <div className="novel-modal-backdrop" onClick={() => setEditing(null)}>
          <div className="novel-modal" onClick={(e) => e.stopPropagation()}>
            <div className="novel-modal-title">世界观条目</div>
            <label>主题<input
              value={editing.topic}
              onChange={(e) => setEditing({ ...editing, topic: e.target.value })}
            /></label>
            <label>内容<textarea
              value={editing.content}
              rows={6}
              onChange={(e) => setEditing({ ...editing, content: e.target.value })}
            /></label>
            <div className="novel-modal-actions">
              <button onClick={() => setEditing(null)}>取消</button>
              <button
                className="primary"
                disabled={!editing.topic.trim()}
                onClick={() => {
                  upsert({ topic: editing.topic.trim(), content: editing.content });
                  setEditing(null);
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Timeline list ───

function TimelineList() {
  const timeline = useNovelStore((s) => s.project.timeline);
  const chapters = useNovelStore((s) => s.project.chapters);
  const upsert = useNovelStore((s) => s.upsertTimelineEvent);
  const del = useNovelStore((s) => s.deleteTimelineEvent);
  const [editing, setEditing] = useState<TimelineEvent | null>(null);

  return (
    <>
      <div className="novel-list-header">
        <span>共 {timeline.length} 个事件</span>
        <button
          className="novel-add-btn"
          onClick={() => setEditing({ id: `tl-${Date.now()}`, when: '', description: '' })}
        >
          +
        </button>
      </div>
      <div className="novel-list">
        {timeline.length === 0 && !editing && (
          <div className="novel-empty">按时间顺序记录事件，帮助保持前后一致。</div>
        )}
        {timeline.map((e) => (
          <div key={e.id} className="novel-card" onClick={() => setEditing({ ...e })}>
            <div className="novel-card-sub">{e.when || '未定时间'}</div>
            <div className="novel-card-body">{e.description}</div>
            {e.chapterId && chapters[e.chapterId] && (
              <div className="novel-card-meta">↳ {chapters[e.chapterId].title}</div>
            )}
            <button
              className="novel-item-delete"
              onClick={(ev) => {
                ev.stopPropagation();
                if (confirm('删除此事件？')) del(e.id);
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      {editing && (
        <div className="novel-modal-backdrop" onClick={() => setEditing(null)}>
          <div className="novel-modal" onClick={(e) => e.stopPropagation()}>
            <div className="novel-modal-title">时间线事件</div>
            <label>时间<input
              value={editing.when}
              placeholder="2024/01/15 或 第三纪元"
              onChange={(e) => setEditing({ ...editing, when: e.target.value })}
            /></label>
            <label>描述<textarea
              value={editing.description}
              rows={4}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
            /></label>
            <label>关联章节
              <select
                value={editing.chapterId || ''}
                onChange={(e) => setEditing({ ...editing, chapterId: e.target.value || undefined })}
              >
                <option value="">（无）</option>
                {Object.values(chapters).map((c) => (
                  <option key={c.id} value={c.id}>{c.title}</option>
                ))}
              </select>
            </label>
            <div className="novel-modal-actions">
              <button onClick={() => setEditing(null)}>取消</button>
              <button
                className="primary"
                disabled={!editing.description.trim()}
                onClick={() => {
                  upsert(editing);
                  setEditing(null);
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
