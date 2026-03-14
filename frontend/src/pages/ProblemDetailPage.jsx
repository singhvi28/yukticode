import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { Play, Send, Loader, Clock, Cpu, CheckCircle, XCircle, Zap, Plus, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import api from '../api';
import { useAuth } from '../context/AuthContext';

const ProblemDetailPage = () => {
  const { id } = useParams();
  const { user } = useAuth();

  const [problem, setProblem] = useState(null);
  const [loading, setLoading] = useState(true);

  // Editor State
  const [language, setLanguage] = useState('python');
  const [code, setCode] = useState('');

  // Submission State
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  // Test Runner State
  const [activeTab, setActiveTab] = useState('sample-0'); // 'sample-i' or 'custom-i'
  const [customTests, setCustomTests] = useState([]); // [{ id: 'custom-123', input: '', expectedOutput: '' }]
  const [runResults, setRunResults] = useState({}); // { tabId: { status, output, expectedOutput, time, memory } }
  const [runningTests, setRunningTests] = useState(false);

  const defaultCode = {
    python: 'def solve():\n    # Write your solution here\n    pass\n\nif __name__ == "__main__":\n    solve()',
    cpp: '#include <iostream>\nusing namespace std;\n\nint main() {\n    // Write your solution here\n    return 0;\n}',
    java: 'public class Main {\n    public static void main(String[] args) {\n        // Write your solution here\n    }\n}',
    javascript: 'function solve() {\n    // Write your solution here\n}\n\nsolve();'
  };

  useEffect(() => {
    // Load default code when language changes if current code is empty or matches another language's default
    if (!code || Object.values(defaultCode).includes(code)) {
      setCode(defaultCode[language]);
    }
  }, [language]);

  useEffect(() => {
    const fetchProblem = async () => {
      try {
        const response = await api.get(`/problems/${id}`);
        setProblem(response.data);
      } catch (err) {
        console.error("Failed to fetch problem", err);
        // Fallback mock data
        setProblem({
          id,
          title: "Two Sum",
          timeLimit: 2000,
          memoryLimit: 256,
          statement: "Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input would have exactly one solution, and you may not use the same element twice.\n\nYou can return the answer in any order.",
          samples: [
            { id: 1, input: "4\n2 7 11 15\n9", output: "0 1" },
            { id: 2, input: "3\n3 2 4\n6", output: "1 2" }
          ]
        });
      } finally {
        setLoading(false);
      }
    };
    fetchProblem();
  }, [id]);

  const handleEditorWillMount = (monaco) => {
    monaco.editor.defineTheme('pitch-black', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#010101',
      }
    });
  };

  const WS_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:9000')
    .replace(/^http/, 'ws');

  const handleSubmit = async () => {
    if (!user) {
      alert("Please login to submit code");
      return;
    }

    setSubmitting(true);
    setResult(null);

    let submissionId;
    try {
      const response = await api.post('/submit', {
        problem_id: Number(id),
        language: language === 'python' ? 'py' : language,
        src_code: code
      });
      submissionId = response.data.submission_id;
    } catch (err) {
      console.error("Submission failed", err);
      setResult({ status: 'Error', message: 'Failed to submit code' });
      setSubmitting(false);
      return;
    }

    // Show "Judging" state immediately
    setResult({ status: 'JUDGING' });

    // --- WebSocket first ---
    let wsResolved = false;

    const applyResult = (data) => {
      wsResolved = true;
      setResult({
        status: data.status,
        time: data.execution_time_ms ? `${data.execution_time_ms.toFixed(1)}ms` : '-',
        memory: data.peak_memory_mb ? `${data.peak_memory_mb.toFixed(1)}MB` : '-',
        passed: data.status === 'AC' ? 15 : 0,
        total: 15,
        message: data.status === 'AC' ? '' : `Verdict: ${data.status}`
      });
      setSubmitting(false);
    };

    // --- Polling fallback (fires if WS closes before receiving a result) ---
    const startPolling = () => {
      if (wsResolved) return;
      const pollStatus = async () => {
        if (wsResolved) return;
        try {
          const res = await api.get(`/submissions/${submissionId}`);
          const { status, execution_time_ms, peak_memory_mb } = res.data;
          if (status === 'PENDING') {
            setTimeout(pollStatus, 1000);
          } else {
            applyResult({ status, execution_time_ms, peak_memory_mb });
          }
        } catch (pollErr) {
          console.error("Polling failed", pollErr);
          setResult({ status: 'Error', message: 'Failed to check execution status' });
          setSubmitting(false);
        }
      };
      pollStatus();
    };

    try {
      const ws = new WebSocket(`${WS_URL}/ws/submissions/${submissionId}`);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          applyResult(data);
        } catch {
          // malformed message — fall back to polling
          startPolling();
        }
        ws.close();
      };

      ws.onerror = () => {
        console.warn("WebSocket error — falling back to polling");
        startPolling();
      };

      // Closed without a message (e.g. server restart) — use polling
      ws.onclose = () => {
        if (!wsResolved) startPolling();
      };

      // Safety net: if nothing arrives in 30s, fall back to polling
      setTimeout(() => {
        if (!wsResolved) {
          ws.close();
          startPolling();
        }
      }, 30_000);

    } catch (wsErr) {
      console.warn("Unable to open WebSocket, using polling:", wsErr);
      startPolling();
    }
  };

  const handleRunTests = async () => {
    if (!user) {
      alert("Please login to run code.");
      return;
    }

    setRunningTests(true);
    setRunResults({}); // clear old results

    // Gather all tests to run
    const samplesToRun = (problem.samples || []).map((s, i) => ({
      tabId: `sample-${i}`,
      input: s.input,
      expected: s.output
    }));

    const customToRun = customTests.map((c, i) => ({
      tabId: `custom-${i}`,
      input: c.input,
      expected: c.expectedOutput
    }));

    const allTests = [...samplesToRun, ...customToRun];
    let testsCompleted = 0;

    const checkAllDone = () => {
      testsCompleted += 1;
      if (testsCompleted === allTests.length) {
        setRunningTests(false);
      }
    };

    allTests.forEach(async (testData) => {
      // 1. Mark as running
      setRunResults(prev => ({
        ...prev,
        [testData.tabId]: { status: 'RUNNING' }
      }));

      try {
        // 2. Enqueue the run task
        const response = await api.post('/run', {
          language: language === 'python' ? 'py' : language,
          time_limit: Math.ceil(problem.timeLimit / 1000) || 2,
          memory_limit: problem.memoryLimit || 256,
          src_code: code,
          std_in: testData.input || " " // default to single space to prevent EOF issues if empty
        });

        const runId = response.data.run_id;

        // 3. Listen on the new WebSocket for the result
        const ws = new WebSocket(`${WS_URL}/ws/runs/${runId}`);
        let resolved = false;

        ws.onmessage = (event) => {
          try {
            const resultData = JSON.parse(event.data);
            resolved = true;
            setRunResults(prev => ({
              ...prev,
              [testData.tabId]: {
                status: resultData.status,
                output: resultData.std_out,
                expectedOutput: testData.expected,
                time: resultData.execution_time_ms ? `${resultData.execution_time_ms.toFixed(1)}ms` : '-',
                memory: resultData.peak_memory_mb ? `${resultData.peak_memory_mb.toFixed(1)}MB` : '-'
              }
            }));
          } catch (e) {
            console.error("Failed to parse run WS message:", e);
            setRunResults(prev => ({
              ...prev,
              [testData.tabId]: { status: 'Error' }
            }));
          }
          ws.close();
          checkAllDone();
        };

        ws.onerror = () => {
          if (!resolved) {
            setRunResults(prev => ({
              ...prev,
              [testData.tabId]: { status: 'Error' }
            }));
            checkAllDone();
          }
        };

        ws.onclose = () => {
          if (!resolved) {
            setRunResults(prev => ({
              ...prev,
              [testData.tabId]: { status: 'Error' }
            }));
            checkAllDone();
          }
        };

        // Safety timeout (worker failed silently)
        setTimeout(() => {
          if (!resolved) {
            ws.close();
            // checkAllDone is called in onclose
          }
        }, 30000);

      } catch (err) {
        console.error(`Run failed for ${testData.tabId}`, err);
        setRunResults(prev => ({
          ...prev,
          [testData.tabId]: { status: 'Error' }
        }));
        checkAllDone();
      }
    });

    if (allTests.length === 0) setRunningTests(false);
  };

  if (loading) return <div className="loading-screen"><Loader size={40} className="spinner" /></div>;
  if (!problem) return <div className="error-screen">Problem not found</div>;

  return (
    <div className="problem-detail-container">
      {/* Left Pane: Problem Description */}
      <div className="problem-pane glass-card">
        <div className="problem-header">
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
            <div key={sample.id} className="sample-case">
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

      {/* Right Pane: Code Editor */}
      <div className="editor-pane glass-card">
        <div className="editor-toolbar">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="language-select"
          >
            <option value="python">Python 3</option>
            <option value="cpp">C++ 17</option>
            <option value="java">Java 11</option>
            <option value="javascript">JavaScript (Node)</option>
          </select>

          <div className="toolbar-actions">
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleRunTests}
              disabled={submitting || runningTests}
            >
              {runningTests ? <Loader size={16} className="spinner" /> : <Play size={16} />}
              Run Code
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? <Loader size={16} className="spinner" /> : <Send size={16} />}
              Submit
            </button>
          </div>
        </div>

        <div className="editor-wrapper">
          <Editor
            height="100%"
            language={language}
            theme="pitch-black"
            beforeMount={handleEditorWillMount}
            value={code}
            onChange={(val) => setCode(val)}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              fontFamily: "'JetBrains Mono', monospace",
              padding: { top: 16 },
              scrollBeyondLastLine: false,
            }}
          />
        </div>

        {/* Console / Result Area (for Submission only) */}
        {result && (
          result.status === 'JUDGING' ? (
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
          ) : (
            <div className={`console-pane animate-fade-in ${result.status === 'AC' ? 'success' : 'error'}`}>
              <div className="console-header">
                <h3>
                  {result.status === 'AC' ? <CheckCircle size={18} /> : <XCircle size={18} />}
                  {result.status === 'AC' ? 'Accepted' : result.status}
                </h3>
              </div>
              {result.status === 'AC' && (
                <div className="console-stats">
                  <div className="stat"><span>Time:</span> {result.time}</div>
                  <div className="stat"><span>Memory:</span> {result.memory}</div>
                  <div className="stat"><span>Test Cases:</span> {result.passed}/{result.total}</div>
                </div>
              )}
              {result.message && <div className="console-message">{result.message}</div>}
            </div>
          )
        )}

        {/* Test Runner Pane */}
        <div className="test-runner-pane">
          <div className="test-runner-tabs">
            {(problem.samples || []).map((_, i) => {
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
                      setCustomTests(customTests.filter((_, idx) => idx !== i));
                      if (activeTab === tabId) setActiveTab('sample-0');
                    }}
                  />
                </button>
              );
            })}

            <button
              className="test-tab new-custom"
              onClick={() => {
                if (customTests.length < 4) {
                  const newId = `custom-${customTests.length}`;
                  setCustomTests([...customTests, { input: '', expectedOutput: '' }]);
                  setActiveTab(newId);
                }
              }}
              disabled={customTests.length >= 4}
            >
              <Plus size={16} /> Add Test
            </button>
          </div>

          <div className="test-runner-content">
            {activeTab.startsWith('sample-') && problem.samples?.[parseInt(activeTab.split('-')[1])] && (() => {
              const sampleIdx = parseInt(activeTab.split('-')[1]);
              const sample = problem.samples[sampleIdx];
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

            {activeTab.startsWith('custom-') && typeof customTests[parseInt(activeTab.split('-')[1])] !== 'undefined' && (() => {
              const customIdx = parseInt(activeTab.split('-')[1]);
              const custom = customTests[customIdx];
              const res = runResults[activeTab];
              return (
                <div className="test-split">
                  <div className="test-io">
                    <h4>Input</h4>
                    <textarea
                      className="custom-textarea"
                      value={custom.input}
                      onChange={(e) => {
                        const newCustoms = [...customTests];
                        newCustoms[customIdx].input = e.target.value;
                        setCustomTests(newCustoms);
                      }}
                      placeholder="Enter test input here..."
                    />
                    <h4>Expected Output <span className="optional">(Optional)</span></h4>
                    <textarea
                      className="custom-textarea optional"
                      value={custom.expectedOutput}
                      onChange={(e) => {
                        const newCustoms = [...customTests];
                        newCustoms[customIdx].expectedOutput = e.target.value;
                        setCustomTests(newCustoms);
                      }}
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
      </div>

      <style jsx>{`
        .problem-detail-container {
          flex: 1;
          display: flex;
          height: calc(100vh - 72px); /* Subtract Navbar height */
          gap: 1.5rem;
          padding: 1.5rem;
          max-width: 1600px;
          margin: 0 auto;
          width: 100%;
        }

        .editor-pane {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow: hidden; /* Ensure pane contains children */
        }
        
        .editor-wrapper {
          flex: 1;
          min-height: 200px;
        }
        
        .problem-pane {
          overflow-y: auto;
          padding: 2rem;
          scrollbar-width: thin;
          scrollbar-color: var(--border-color) transparent;
        }
        
        .problem-pane::-webkit-scrollbar {
          width: 6px;
        }
        
        .problem-pane::-webkit-scrollbar-thumb {
          background-color: var(--border-color);
          border-radius: 3px;
        }

        .problem-header {
          margin-bottom: 2rem;
          border-bottom: 1px solid var(--border-color);
          padding-bottom: 1rem;
        }

        .problem-header h2 {
          font-size: 2rem;
          margin-bottom: 1rem;
        }

        .problem-meta {
          display: flex;
          gap: 1rem;
        }

        .meta-tag {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          font-size: 0.875rem;
          color: var(--text-secondary);
          background: rgba(255,255,255,0.05);
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
        }

        .problem-statement {
          font-size: 1.05rem;
          line-height: 1.7;
          color: var(--text-primary);
          margin-bottom: 2rem;
        }

        .problem-statement p {
          margin-bottom: 1rem;
        }

        .problem-samples h3 {
          margin-bottom: 1rem;
          font-size: 1.25rem;
        }

        .sample-case {
          margin-bottom: 1.5rem;
          background: rgba(0,0,0,0.2);
          border: 1px solid var(--border-color);
          border-radius: 0.5rem;
          overflow: hidden;
        }

        .sample-block {
          padding: 1rem;
        }

        .sample-block + .sample-block {
          border-top: 1px solid var(--border-color);
        }

        .sample-block h4 {
          font-size: 0.875rem;
          color: var(--text-secondary);
          margin-bottom: 0.5rem;
        }

        .sample-block pre {
          font-family: var(--font-mono);
          margin: 0;
          white-space: pre-wrap;
          font-size: 0.9rem;
        }

        .editor-pane {
          display: flex;
          flex-direction: column;
        }

        .editor-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.75rem 1rem;
          background: rgba(0,0,0,0.2);
          border-bottom: 1px solid var(--border-color);
        }

        .language-select {
          background: var(--bg-card-hover);
          color: var(--text-primary);
          border: 1px solid var(--border-color);
          padding: 0.5rem 1rem;
          border-radius: 0.5rem;
          font-family: inherit;
          cursor: pointer;
        }
        
        .language-select:focus {
          outline: none;
          border-color: var(--accent-primary);
        }

        .toolbar-actions {
          display: flex;
          gap: 0.75rem;
        }

        .btn-sm {
          padding: 0.5rem 1rem;
          font-size: 0.875rem;
        }

        .editor-wrapper {
          flex: 1;
        }

        .console-pane {
          padding: 1.5rem;
          background: rgba(0,0,0,0.3);
          border-top: 1px solid var(--border-color);
        }

        .console-pane.success { border-top-color: var(--success); }
        .console-pane.error { border-top-color: var(--error); }
        .console-pane.judging { border-top-color: var(--accent-primary); }

        .console-header h3 {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-bottom: 1rem;
        }

        .console-pane.success h3 { color: var(--success); }
        .console-pane.error h3 { color: var(--error); }
        .console-pane.judging h3 { color: var(--accent-primary); }

        /* Pulsing bolt icon during judging */
        @keyframes zap-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.85); }
        }
        .zap-pulse { animation: zap-pulse 1s ease-in-out infinite; }

        /* Animated dots */
        .judging-dots {
          display: flex;
          gap: 6px;
          padding-top: 0.25rem;
        }
        .judging-dots span {
          width: 7px; height: 7px;
          border-radius: 50%;
          background: var(--accent-primary);
          animation: dot-bounce 1.2s ease-in-out infinite;
        }
        .judging-dots span:nth-child(2) { animation-delay: 0.2s; }
        .judging-dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes dot-bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
          40% { transform: translateY(-6px); opacity: 1; }
        }

        .console-stats {
          display: flex;
          gap: 2rem;
          font-family: var(--font-mono);
          font-size: 0.9rem;
        }

        .stat span {
          color: var(--text-secondary);
        }

        .console-message {
          color: var(--error);
          font-family: var(--font-mono);
        }

        .loading-screen, .error-screen {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100vh;
        }

        .spinner {
          animation: spin 1s linear infinite;
          color: var(--accent-primary);
        }

        @media (max-width: 1024px) {
          .problem-detail-container {
            flex-direction: column;
            height: auto;
          }
          .problem-pane, .editor-pane {
            flex: none;
            height: 800px;
          }
        }

        /* Test Runner Styles */
        .test-runner-pane {
          height: 350px;
          display: flex;
          flex-direction: column;
          background: rgba(0,0,0,0.3);
          border-top: 1px solid var(--border-color);
        }

        .test-runner-tabs {
          display: flex;
          overflow-x: auto;
          background: rgba(0,0,0,0.2);
          border-bottom: 1px solid var(--border-color);
        }
        .test-runner-tabs::-webkit-scrollbar { height: 4px; }

        .test-tab {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1.25rem;
          background: transparent;
          border: none;
          color: var(--text-secondary);
          font-family: var(--font-main);
          font-size: 0.875rem;
          cursor: pointer;
          border-bottom: 2px solid transparent;
          white-space: nowrap;
          transition: all 0.2s;
        }

        .test-tab:hover {
          background: rgba(255,255,255,0.05);
          color: var(--text-primary);
        }

        .test-tab.active {
          color: var(--accent-primary);
          border-bottom-color: var(--accent-primary);
          background: rgba(0, 240, 255, 0.05);
        }

        .tab-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: transparent;
        }
        .status-ac .tab-indicator { background: var(--success); }
        .status-wa .tab-indicator, .status-ce .tab-indicator, .status-re .tab-indicator, .status-system_error .tab-indicator { background: var(--error); }
        .status-tle .tab-indicator, .status-mle .tab-indicator { background: var(--warning); }
        .status-running .tab-indicator { 
          background: var(--accent-primary); 
          animation: dot-pulse 1s infinite alternate; 
        }

        @keyframes dot-pulse {
          0% { transform: scale(0.8); opacity: 0.5; }
          100% { transform: scale(1.2); opacity: 1; }
        }

        .delete-custom {
          margin-left: 0.25rem;
          opacity: 0.5;
        }
        .delete-custom:hover { opacity: 1; color: var(--error); }

        .new-custom { opacity: 0.7; }
        .new-custom:hover:not(:disabled) { opacity: 1; color: var(--success); }
        .new-custom:disabled { opacity: 0.3; cursor: not-allowed; }

        .test-runner-content {
          flex: 1;
          overflow-y: auto;
          padding: 1rem;
        }

        .test-split {
          display: flex;
          gap: 2rem;
          height: 100%;
        }

        .test-io, .test-result {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .test-runner-content h4 {
          font-size: 0.85rem;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .optional {
          text-transform: none;
          display: inline-block;
          font-size: 0.75rem;
          opacity: 0.7;
          margin-left: 0.5rem;
        }

        .read-only-io {
          background: rgba(0,0,0,0.2);
          padding: 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid var(--border-color);
          font-family: var(--font-mono);
          font-size: 0.9rem;
          margin: 0;
          white-space: pre-wrap;
          max-height: 100px;
          overflow-y: auto;
        }

        .custom-textarea {
          background: rgba(0,0,0,0.2);
          padding: 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid var(--border-color);
          color: var(--text-primary);
          font-family: var(--font-mono);
          font-size: 0.9rem;
          resize: none;
          flex: 1;
          min-height: 80px;
        }
        
        .custom-textarea:focus {
          outline: none;
          border-color: var(--accent-primary);
        }

        .empty-result {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-secondary);
          border: 1px dashed var(--border-color);
          border-radius: 0.5rem;
          font-size: 0.9rem;
        }

        .result-card {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .result-badge {
          display: inline-block;
          font-weight: 600;
          font-size: 1.1rem;
          padding: 0.25rem 0;
        }
        .result-badge.success { color: var(--success); }
        .result-badge.error { color: var(--error); }
        .result-badge.running { color: var(--accent-primary); animation: pulse 1.5s infinite; }

        .result-stats {
          display: flex;
          gap: 1.5rem;
          font-family: var(--font-mono);
          font-size: 0.85rem;
          color: var(--text-secondary);
        }
        
        .result-stats span {
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }

        .output-block {
          flex: 1;
          background: rgba(0,0,0,0.2);
          padding: 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid var(--border-color);
          font-family: var(--font-mono);
          font-size: 0.9rem;
          margin: 0;
          white-space: pre-wrap;
          overflow-y: auto;
        }
        .output-block.match { border-color: rgba(0, 255, 170, 0.3); background: rgba(0, 255, 170, 0.05); color: var(--success); }
        .output-block.mismatch { border-color: rgba(255, 68, 68, 0.3); background: rgba(255, 68, 68, 0.05); color: var(--error); }
      `}</style>
    </div>
  );
};

export default ProblemDetailPage;
