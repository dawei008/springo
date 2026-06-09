import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useCallback } from 'react';

export default function PlanCanvasPanel() {
  const planModeActive = useUIStore((s) => s.planModeActive);
  const planApprovalData = useUIStore((s) => s.planApprovalData);
  const hidePlanApproval = useUIStore((s) => s.hidePlanApproval);

  const respondPlan = useCallback((decision: 'APPROVE_PLAN' | 'REJECT_PLAN') => {
    hidePlanApproval();
    const sessionId = useSessionStore.getState().currentSessionId;
    if (sessionId) useChatStore.getState().sendMessage(sessionId, decision);
  }, [hidePlanApproval]);

  return (
    <div className="plan-canvas-panel">
      <div className="plan-canvas-status">
        <span className={`plan-status-dot${planModeActive ? ' active' : ''}`} />
        <span>{planModeActive ? 'Plan Mode Active' : 'Plan Mode'}</span>
      </div>

      {planApprovalData ? (
        <div className="plan-canvas-approval">
          <div className="plan-canvas-summary">{planApprovalData.summary}</div>
          {planApprovalData.steps.length > 0 && (
            <div className="plan-canvas-steps">
              <h4>Steps</h4>
              <ol>
                {planApprovalData.steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>
          )}
          {planApprovalData.files.length > 0 && (
            <div className="plan-canvas-files">
              <h4>Files</h4>
              <ul>
                {planApprovalData.files.map((file, i) => (
                  <li key={i}><code>{file}</code></li>
                ))}
              </ul>
            </div>
          )}
          <div className="plan-canvas-actions">
            <button className="plan-reject-btn" onClick={() => respondPlan('REJECT_PLAN')}>Reject</button>
            <button className="plan-approve-btn" onClick={() => respondPlan('APPROVE_PLAN')}>Approve</button>
          </div>
        </div>
      ) : (
        <div className="plan-canvas-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
            <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
            <rect x="9" y="3" width="6" height="4" rx="1" />
            <path d="M9 12h6M9 16h6" />
          </svg>
          <span>Send a message to generate a plan</span>
        </div>
      )}
    </div>
  );
}
