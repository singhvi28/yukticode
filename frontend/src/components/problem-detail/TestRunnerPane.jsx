import React from 'react';
import { Plus, Trash2, Clock, Cpu } from 'lucide-react';

export const TestRunnerPane = ({
  problem,
  activeTab,
  setActiveTab,
  customTests,
  runResults,
  onAddTest,
  onUpdateTest,
  onDeleteTest,
}) => {
  const samples = problem?.samples || [];

  return (
    <div className="test-runner-pane">
      <div className="test-runner-tabs">
        {samples.map((_, i) => {
          const tabId = `sample-${i}`;
          const tStatus = runResults[tabId]?.status;
          return (
            <button
              key={tabId}
              className={`test-tab ${activeTab === tabId ? 'active' : ''} status-${tStatus?.toLowerCase() || 'none'}`}
              onClick={() => setActiveTab(tabId)}
            >
              <span className="tab-indicator" /> Sample {i + 1}
            </button>
          );
        })}

        {customTests.map((_, i) => {
          const tabId = `custom-${i}`;
          const tStatus = runResults[tabId]?.status;
          return (
            <button
              key={tabId}
              className={`test-tab ${activeTab === tabId ? 'active' : ''} status-${tStatus?.toLowerCase() || 'none'}`}
              onClick={() => setActiveTab(tabId)}
            >
              <span className="tab-indicator" /> Custom {i + 1}
              <Trash2
                size={14}
                className="delete-custom"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteTest(i);
                }}
              />
            </button>
          );
        })}

        <button
          className="test-tab new-custom"
          onClick={onAddTest}
          disabled={customTests.length >= 4}
        >
          <Plus size={16} /> Add Test
        </button>
      </div>

      <div className="test-runner-content">
        {activeTab.startsWith('sample-') && (() => {
          const sampleIdx = parseInt(activeTab.split('-')[1], 10);
          const sample = samples[sampleIdx];
          if (!sample) return null;
          const res = runResults[activeTab];

          return (
            <div className="test-split">
              <div className="test-io">
                <h4>Input</h4>
                <pre className="read-only-io">{sample.input}</pre>
                <h4>Expected Output</h4>
                <pre className="read-only-io">{sample.output}</pre>
              </div>
              <div className="test-result">
                <h4>Actual Output</h4>
                {res ? (
                  <div className="result-card">
                    <div className={`result-badge ${res.status === 'AC' ? 'success' : res.status === 'RUNNING' ? 'running' : 'error'}`}>
                      {res.status === 'RUNNING' ? 'Running...' : res.status}
                    </div>
                    {res.status !== 'RUNNING' && (
                      <>
                        <div className="result-stats">
                          <span><Clock size={12} /> {res.time}</span>
                          <span><Cpu size={12} /> {res.memory}</span>
                        </div>
                        <pre className={`output-block ${res.status === 'AC' ? 'match' : 'mismatch'}`}>
                          {res.output || '<No Output>'}
                        </pre>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="empty-result">Run code to see output</div>
                )}
              </div>
            </div>
          );
        })()}

        {activeTab.startsWith('custom-') && (() => {
          const customIdx = parseInt(activeTab.split('-')[1], 10);
          const custom = customTests[customIdx];
          if (!custom) return null;
          const res = runResults[activeTab];

          return (
            <div className="test-split">
              <div className="test-io">
                <h4>Input</h4>
                <textarea
                  className="custom-textarea"
                  value={custom.input}
                  onChange={(e) => onUpdateTest(customIdx, 'input', e.target.value)}
                  placeholder="Enter test input here..."
                />
                <h4>Expected Output <span className="optional">(Optional)</span></h4>
                <textarea
                  className="custom-textarea optional"
                  value={custom.expectedOutput}
                  onChange={(e) => onUpdateTest(customIdx, 'expectedOutput', e.target.value)}
                  placeholder="Enter expected output..."
                />
              </div>
              <div className="test-result">
                <h4>Actual Output</h4>
                {res ? (
                  <div className="result-card">
                    <div className={`result-badge ${res.status === 'AC' ? 'success' : res.status === 'RUNNING' ? 'running' : 'error'}`}>
                      {res.status === 'RUNNING' ? 'Running...' : res.status}
                    </div>
                    {res.status !== 'RUNNING' && (
                      <>
                        <div className="result-stats">
                          <span><Clock size={12} /> {res.time}</span>
                          <span><Cpu size={12} /> {res.memory}</span>
                        </div>
                        <pre className={`output-block ${res.status === 'AC' ? 'match' : custom.expectedOutput ? 'mismatch' : 'neutral'}`}>
                          {res.output || '<No Output>'}
                        </pre>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="empty-result">Run code to see output</div>
                )}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

export default TestRunnerPane;
