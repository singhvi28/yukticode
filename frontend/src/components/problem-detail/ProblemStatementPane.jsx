import React from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { Clock, Cpu } from 'lucide-react';

export const ProblemStatementPane = ({ problem, contestId }) => {
  if (!problem) return null;

  return (
    <div className="problem-pane glass-card">
      <div className="problem-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {contestId && (
            <>
              <span
                className="contest-mode-badge"
                style={{
                  background: 'var(--success-bg)',
                  color: 'var(--success)',
                  padding: '0.25rem 0.5rem',
                  borderRadius: '4px',
                  fontSize: '0.8rem',
                }}
              >
                Contest mode
              </span>
              <Link to={`/contests/${contestId}`} className="btn btn-ghost btn-sm" style={{ fontSize: '0.85rem' }}>
                Back to contest
              </Link>
            </>
          )}
        </div>
        <h2>{problem.id}. {problem.title}</h2>
        <div className="problem-meta">
          <span className="meta-tag"><Clock size={14} /> {problem.timeLimit}ms</span>
          <span className="meta-tag"><Cpu size={14} /> {problem.memoryLimit}MB</span>
        </div>
      </div>

      <div className="problem-statement">
        <ReactMarkdown>{problem.statement}</ReactMarkdown>
      </div>

      <div className="problem-samples">
        <h3>Examples</h3>
        {problem.samples?.map((sample, i) => (
          <div key={sample.id || i} className="sample-case">
            <div className="sample-block">
              <h4>Input {i + 1}</h4>
              <pre>{sample.input}</pre>
            </div>
            <div className="sample-block">
              <h4>Output {i + 1}</h4>
              <pre>{sample.output}</pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ProblemStatementPane;
