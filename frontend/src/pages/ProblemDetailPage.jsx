import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { Loader } from 'lucide-react';

import api from '../api';
import { useAuth } from '../context/AuthContext';
import { useMonacoEditor } from '../hooks/useMonacoEditor';
import { useSubmission } from '../hooks/useSubmission';
import { useRunBatch } from '../hooks/useRunBatch';

import { ProblemStatementPane } from '../components/problem-detail/ProblemStatementPane';
import { EditorToolbar } from '../components/problem-detail/EditorToolbar';
import { SubmissionConsole } from '../components/problem-detail/SubmissionConsole';
import { TestRunnerPane } from '../components/problem-detail/TestRunnerPane';
import '../components/problem-detail/ProblemDetail.css';

const ProblemDetailPage = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const contestId = searchParams.get('contest_id');
  const { user } = useAuth();

  const [problem, setProblem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lockedMessage, setLockedMessage] = useState(null);
  const [loadError, setLoadError] = useState(null);

  // Custom Hooks encapsulating modular state
  const {
    language,
    setLanguage,
    code,
    setCode,
    handleEditorWillMount,
  } = useMonacoEditor('python');

  const {
    submitting,
    result,
    handleSubmit: triggerSubmit,
  } = useSubmission();

  const {
    activeTab,
    setActiveTab,
    customTests,
    runResults,
    runningTests,
    addCustomTest,
    updateCustomTest,
    deleteCustomTest,
    handleRunTests: triggerRunTests,
  } = useRunBatch();

  useEffect(() => {
    const fetchProblem = async () => {
      setLockedMessage(null);
      setLoadError(null);
      try {
        const response = await api.get(`/problems/${id}`);
        setProblem(response.data);
      } catch (err) {
        console.error('Failed to fetch problem', err);
        setProblem(null);
        if (err.response?.status === 403 && err.response?.data?.detail) {
          setLockedMessage(
            err.response.data.detail === 'This problem is locked until the contest starts.'
              ? 'This problem is locked until the contest starts.'
              : err.response.data.detail
          );
        } else if (err.response?.status === 404) {
          setLoadError('Problem not found.');
        } else {
          setLoadError('Failed to load this problem.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchProblem();
  }, [id]);

  const onRunCode = () => {
    triggerRunTests({ problem, language, code, user });
  };

  const onSubmitCode = () => {
    triggerSubmit({ problemId: id, language, code, contestId, user });
  };

  if (loading) {
    return (
      <div className="loading-screen">
        <Loader size={40} className="spinner" />
      </div>
    );
  }

  if (lockedMessage) {
    return (
      <div className="problem-detail-container">
        <div className="error-screen glass-card" style={{ padding: '2rem', maxWidth: '500px', margin: '2rem auto' }}>
          <p style={{ color: 'var(--warning)', marginBottom: '1rem' }}>{lockedMessage}</p>
          {contestId && (
            <Link to={`/contests/${contestId}`} className="btn btn-primary">
              Back to contest
            </Link>
          )}
        </div>
      </div>
    );
  }

  if (!problem) {
    return <div className="error-screen">{loadError || 'Problem not found'}</div>;
  }

  return (
    <div className="problem-detail-container">
      {/* Left Pane: Problem Description & Markdown */}
      <ProblemStatementPane problem={problem} contestId={contestId} />

      {/* Right Pane: Code Editor & Test Runner */}
      <div className="editor-pane glass-card">
        <EditorToolbar
          language={language}
          setLanguage={setLanguage}
          onRun={onRunCode}
          onSubmit={onSubmitCode}
          runningTests={runningTests}
          submitting={submitting}
        />

        <div className="editor-wrapper">
          <Editor
            height="100%"
            language={language}
            theme="pitch-black"
            beforeMount={handleEditorWillMount}
            value={code}
            onChange={(val) => setCode(val || '')}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              fontFamily: "'JetBrains Mono', monospace",
              padding: { top: 16 },
              scrollBeyondLastLine: false,
            }}
          />
        </div>

        {/* Verdict console banner */}
        <SubmissionConsole result={result} />

        {/* Multi-tab test runner */}
        <TestRunnerPane
          problem={problem}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          customTests={customTests}
          runResults={runResults}
          onAddTest={addCustomTest}
          onUpdateTest={updateCustomTest}
          onDeleteTest={deleteCustomTest}
        />
      </div>
    </div>
  );
};

export default ProblemDetailPage;
