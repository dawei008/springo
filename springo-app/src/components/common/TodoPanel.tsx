import { useUIStore } from '@/stores/uiStore';

export default function TodoPanel() {
  const todos = useUIStore((s) => s.todos);

  if (todos.length === 0) return null;

  const completedCount = todos.filter((t) => t.status === 'completed').length;
  const allDone = completedCount === todos.length;

  return (
    <div className={`todo-panel${todos.length > 0 ? ' visible' : ''}`} id="todo-panel">
      <div className="todo-panel-header">
        <h3>Tasks</h3>
        <span className="todo-panel-progress">
          {completedCount}/{todos.length}
        </span>
      </div>
      {!allDone && (
        <div className="todo-panel-list" id="todo-list">
          {todos.map((todo) => {
            let statusIcon = '\u25CB'; // ○ pending
            let statusClass = 'pending';
            if (todo.status === 'in_progress') {
              statusIcon = '\u25D4'; // ◔ in progress
              statusClass = 'in-progress';
            } else if (todo.status === 'completed') {
              statusIcon = '\u2713'; // ✓ done
              statusClass = 'completed';
            }
            return (
              <div key={todo.id} className={`todo-item ${statusClass}`}>
                <span className="todo-status-icon">{statusIcon}</span>
                <span className="todo-subject">{todo.subject}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
