import { useCallback } from 'react';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function PlanModeIndicator() {
  const planModeActive = useUIStore((s) => s.planModeActive);

  return (
    <div
      className={`plan-mode-indicator${planModeActive ? ' visible' : ''}`}
      id="plan-mode-indicator"
    >
      <span className="icon">Plan</span>
      <span>Plan Mode</span>
    </div>
  );
}

export default function PlanApprovalModal() {
  const planApprovalData = useUIStore((s) => s.planApprovalData);
  const hidePlanApproval = useUIStore((s) => s.hidePlanApproval);

  const handleApprove = useCallback(() => {
    hidePlanApproval();
    // Send approval message
    const sessionId = useSessionStore.getState().currentSessionId;
    if (sessionId) {
      useChatStore.getState().sendMessage(sessionId, 'APPROVE_PLAN');
    }
  }, [hidePlanApproval]);

  const handleReject = useCallback(() => {
    hidePlanApproval();
    // Send rejection message
    const sessionId = useSessionStore.getState().currentSessionId;
    if (sessionId) {
      useChatStore.getState().sendMessage(sessionId, 'REJECT_PLAN');
    }
  }, [hidePlanApproval]);

  if (!planApprovalData) return null;

  return (
    <div className="plan-approval-modal active" id="plan-approval-modal">
      <div className="plan-approval-content">
        <div className="plan-approval-header">
          <span className="icon">Plan</span>
          <h3>Review Plan</h3>
        </div>
        <div className="plan-approval-body">
          <div className="plan-summary">{planApprovalData.summary}</div>
          {planApprovalData.steps.length > 0 && (
            <div className="plan-steps">
              <h4>Steps</h4>
              <ol>
                {planApprovalData.steps.map((step, i) => (
                  <li key={i}>{escapeHtml(step)}</li>
                ))}
              </ol>
            </div>
          )}
          {planApprovalData.files.length > 0 && (
            <div className="plan-files">
              <h4>Files</h4>
              <ul>
                {planApprovalData.files.map((file, i) => (
                  <li key={i}><code>{escapeHtml(file)}</code></li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="plan-approval-footer">
          <button className="plan-reject-btn" onClick={handleReject}>
            Reject
          </button>
          <button className="plan-approve-btn" onClick={handleApprove}>
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
