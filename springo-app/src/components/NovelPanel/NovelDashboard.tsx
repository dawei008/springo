/**
 * NovelDashboard — friendly empty-state shown when a Novel Studio session
 * has no chapters yet. Mirrors the DesignDashboard pattern.
 */
import { useNovelStore } from '@/stores/novelStore';
import { useSessionStore } from '@/stores/sessionStore';

export default function NovelDashboard() {
  const addChapter = useNovelStore((s) => s.addChapter);
  const loadFromDisk = useNovelStore((s) => s.loadFromDisk);
  const workingDir = useNovelStore((s) => s.workingDir);
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));
  const wd = workingDir || session?.workingDir || null;

  const onStart = () => {
    addChapter('第一章');
  };
  const onLoad = async () => {
    if (wd) {
      await loadFromDisk(wd).catch(() => {});
    }
  };

  return (
    <div className="novel-dashboard">
      <div className="novel-dashboard-inner">
        <div className="novel-dashboard-icon">📖</div>
        <h1 className="novel-dashboard-title">Novel Studio</h1>
        <p className="novel-dashboard-subtitle">
          专注的长篇小说写作工作台 · 章节 / 人物 / 世界观 / 时间线<br />
          本地自动保存到 <code>{wd || '<未设工作目录>'}</code>
        </p>
        <div className="novel-dashboard-features">
          <div className="novel-dashboard-feature">
            <div className="novel-dashboard-feature-title">✏️ 纯文本编辑</div>
            <div className="novel-dashboard-feature-desc">Markdown 格式，左侧章节树 + 中间 textarea + 可切换预览。</div>
          </div>
          <div className="novel-dashboard-feature">
            <div className="novel-dashboard-feature-title">🤖 AI 协作</div>
            <div className="novel-dashboard-feature-desc">"续写 / 改写选区" 让 AI 在对话里回复，一键应用到章节。</div>
          </div>
          <div className="novel-dashboard-feature">
            <div className="novel-dashboard-feature-title">🧩 结构化笔记</div>
            <div className="novel-dashboard-feature-desc">人物卡、世界观条目、时间线事件，一份可被 AI 引用的作品圣经。</div>
          </div>
          <div className="novel-dashboard-feature">
            <div className="novel-dashboard-feature-title">💾 本地文件</div>
            <div className="novel-dashboard-feature-desc">
              <code>chapters/*.md</code>、<code>characters.json</code> 等，版本管理交给 git。
            </div>
          </div>
        </div>
        <div className="novel-dashboard-actions">
          <button className="novel-dashboard-btn" onClick={onStart}>
            ▶ 开始写作
          </button>
          {wd && (
            <button className="novel-dashboard-btn secondary" onClick={onLoad}>
              📂 从磁盘载入
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
