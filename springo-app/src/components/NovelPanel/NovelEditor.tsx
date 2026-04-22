/**
 * NovelEditor — center column. Textarea + word count + AI action buttons.
 * Selection-based actions prefill the chat input via uiStore.pendingPrompt.
 */
import { useRef, useCallback, useEffect, useState } from 'react';
import { useNovelStore } from '@/stores/novelStore';
import { useUIStore } from '@/stores/uiStore';
import Markdown from '@/components/common/Markdown';

export default function NovelEditor() {
  const activeChapterId = useNovelStore((s) => s.activeChapterId);
  const chapter = useNovelStore((s) =>
    s.activeChapterId ? s.project.chapters[s.activeChapterId] : null,
  );
  const updateChapter = useNovelStore((s) => s.updateChapter);
  const setSelection = useNovelStore((s) => s.setSelection);
  const saveToDisk = useNovelStore((s) => s.saveToDisk);
  const isSaving = useNovelStore((s) => s.isSaving);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [preview, setPreview] = useState(false);
  const [selectionText, setSelectionText] = useState('');

  // Keep selection in store whenever textarea selection changes
  const onSelect = useCallback(() => {
    const el = textareaRef.current;
    if (!el || !activeChapterId) return;
    const { selectionStart: start, selectionEnd: end } = el;
    if (start !== end) {
      setSelection({ chapterId: activeChapterId, start, end });
      setSelectionText(el.value.slice(start, end));
    } else {
      setSelection(null);
      setSelectionText('');
    }
  }, [activeChapterId, setSelection]);

  // Clear selection-text when switching chapter
  useEffect(() => {
    setSelectionText('');
    setSelection(null);
  }, [activeChapterId, setSelection]);

  const handleContinue = useCallback(() => {
    if (!chapter) return;
    const prev = chapter.content.slice(-400);
    const prompt =
      `请继续写「${chapter.title}」。请调用 novel_write_chapter 工具 (chapter_id="${chapter.id}", mode="append") 将新段落写入。\n\n` +
      `目前章节结尾：\n\n${prev || '(空章节，请从头开始)'}`;
    useUIStore.getState().setPendingPrompt(prompt);
  }, [chapter]);

  const handleRewrite = useCallback(() => {
    if (!chapter || !selectionText) return;
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end } = el;
    const prompt =
      `请改写下面这段文字（选区位于章节「${chapter.title}」的 [${start}, ${end}]）。` +
      `请调用 novel_rewrite_selection 工具 (chapter_id="${chapter.id}", start=${start}, end=${end}, new_text=...)。\n\n` +
      `原文：\n${selectionText}\n\n` +
      `改写方向：（在这里说明你想要的风格，例如"更紧张"/"第一人称"/"更凝练"）`;
    useUIStore.getState().setPendingPrompt(prompt);
  }, [chapter, selectionText]);

  if (!chapter) {
    return (
      <div className="novel-editor-empty">
        <div>选择一个章节开始写作</div>
        <div className="novel-editor-empty-hint">左侧点击章节，或点击 + 新建第一章。</div>
      </div>
    );
  }

  return (
    <div className="novel-editor">
      <div className="novel-editor-header">
        <input
          type="text"
          className="novel-editor-title"
          value={chapter.title}
          onChange={(e) => updateChapter(chapter.id, { title: e.target.value })}
          placeholder="章节标题"
        />
        <div className="novel-editor-actions">
          <select
            value={chapter.status}
            onChange={(e) => updateChapter(chapter.id, { status: e.target.value as any })}
            className="novel-status-select"
          >
            <option value="draft">草稿</option>
            <option value="revising">修订中</option>
            <option value="done">已完成</option>
          </select>
          <button
            className={`novel-mode-toggle${preview ? ' active' : ''}`}
            onClick={() => setPreview((p) => !p)}
            title="切换预览"
          >
            {preview ? '✎ 编辑' : '👁 预览'}
          </button>
        </div>
      </div>

      {preview ? (
        <div className="novel-editor-preview">
          <Markdown content={chapter.content || '*（空章节）*'} />
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          className="novel-editor-textarea"
          value={chapter.content}
          onChange={(e) => updateChapter(chapter.id, { content: e.target.value })}
          onSelect={onSelect}
          onKeyUp={onSelect}
          onMouseUp={onSelect}
          placeholder="在这里开始你的故事……&#10;&#10;提示：&#10;• 选中一段文字后点击「改写选区」让 AI 润色&#10;• 点「续写」从此处继续&#10;• 支持 Markdown 语法"
          spellCheck={false}
        />
      )}

      <div className="novel-editor-footer">
        <div className="novel-editor-stats">
          <span>{chapter.wordCount} 字</span>
          {selectionText && <span>· 选中 {selectionText.length} 字符</span>}
          <span className={`novel-save-indicator${isSaving ? ' saving' : ''}`}>
            {isSaving ? '● 保存中' : '● 已保存'}
          </span>
        </div>
        <div className="novel-editor-ai-actions">
          <button
            className="novel-ai-btn"
            onClick={handleRewrite}
            disabled={!selectionText}
            title={selectionText ? '让 AI 改写选中段落' : '先在正文中选中一段文字'}
          >
            ✎ 改写选区
          </button>
          <button
            className="novel-ai-btn primary"
            onClick={handleContinue}
            title="从当前位置让 AI 续写"
          >
            ▶ 续写
          </button>
          <button
            className="novel-ai-btn"
            onClick={() => saveToDisk().catch(() => {})}
            title="立即保存到磁盘"
          >
            ⬇ 保存
          </button>
        </div>
      </div>
    </div>
  );
}
