import React from 'react';
import { Play, Send, Loader } from 'lucide-react';

export const EditorToolbar = ({
  language,
  setLanguage,
  onRun,
  onSubmit,
  runningTests,
  submitting,
}) => {
  return (
    <div className="editor-toolbar">
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        className="language-select"
        aria-label="Select programming language"
      >
        <option value="python">Python 3</option>
        <option value="cpp">C++ 17</option>
        <option value="java">Java 11</option>
      </select>

      <div className="toolbar-actions">
        <button
          className="btn btn-secondary btn-sm"
          onClick={onRun}
          disabled={submitting || runningTests}
        >
          {runningTests ? <Loader size={16} className="spinner" /> : <Play size={16} />}
          Run Code
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={onSubmit}
          disabled={submitting}
        >
          {submitting ? <Loader size={16} className="spinner" /> : <Send size={16} />}
          Submit
        </button>
      </div>
    </div>
  );
};

export default EditorToolbar;
