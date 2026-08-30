import React from 'react';
import { CheckCircle, XCircle, Zap } from 'lucide-react';

export const SubmissionConsole = ({ result }) => {
  if (!result) return null;

  if (result.status === 'JUDGING') {
    return (
      <div className="console-pane judging animate-fade-in">
        <div className="console-header">
          <h3>
            <Zap size={18} className="zap-pulse" />
            Judging via WebSocket…
          </h3>
        </div>
        <div className="judging-dots">
          <span /><span /><span />
        </div>
      </div>
    );
  }

  const isAc = result.status === 'AC';

  return (
    <div className={`console-pane animate-fade-in ${isAc ? 'success' : 'error'}`}>
      <div className="console-header">
        <h3>
          {isAc ? <CheckCircle size={18} /> : <XCircle size={18} />}
          {isAc ? 'Accepted' : result.status}
        </h3>
      </div>
      {isAc && (
        <div className="console-stats">
          <div className="stat"><span>Time:</span> {result.time}</div>
          <div className="stat"><span>Memory:</span> {result.memory}</div>
        </div>
      )}
      {result.message && (
        <pre
          className="console-message"
          style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            background: 'rgba(0,0,0,0.3)',
            padding: '12px',
            borderRadius: '6px',
            margin: '8px 0 0',
            maxHeight: '200px',
            overflow: 'auto',
          }}
        >
          {result.message}
        </pre>
      )}
    </div>
  );
};

export default SubmissionConsole;
