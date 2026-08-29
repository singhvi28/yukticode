import { useState, useRef, useEffect, useCallback } from 'react';
import api, { getWsUrl } from '../api';

export const useRunBatch = () => {
  const [activeTab, setActiveTab] = useState('sample-0');
  const [customTests, setCustomTests] = useState([]);
  const [runResults, setRunResults] = useState({});
  const [runningTests, setRunningTests] = useState(false);

  const activeWsRef = useRef(null);
  const safetyTimeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      clearTimeout(safetyTimeoutRef.current);
      if (activeWsRef.current) {
        activeWsRef.current.close();
      }
    };
  }, []);

  const addCustomTest = useCallback(() => {
    if (customTests.length < 4) {
      const newId = `custom-${customTests.length}`;
      setCustomTests(prev => [...prev, { input: '', expectedOutput: '' }]);
      setActiveTab(newId);
    }
  }, [customTests.length]);

  const updateCustomTest = useCallback((index, field, value) => {
    setCustomTests(prev => {
      const copy = [...prev];
      if (copy[index]) {
        copy[index] = { ...copy[index], [field]: value };
      }
      return copy;
    });
  }, []);

  const deleteCustomTest = useCallback((index) => {
    const tabId = `custom-${index}`;
    setCustomTests(prev => prev.filter((_, idx) => idx !== index));
    setActiveTab(curr => (curr === tabId ? 'sample-0' : curr));
  }, []);

  const handleRunTests = useCallback(async ({ problem, language, code, user }) => {
    if (!user) {
      alert("Please login to run code.");
      return;
    }

    if (!problem) return;

    setRunningTests(true);
    setRunResults({});

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

    if (allTests.length === 0) {
      setRunningTests(false);
      return;
    }

    const initialResults = {};
    allTests.forEach(t => { initialResults[t.tabId] = { status: 'RUNNING' }; });
    setRunResults(initialResults);

    try {
      const response = await api.post('/run_batch', {
        language: language === 'python' ? 'py' : language,
        time_limit: problem.timeLimit || 2000,
        memory_limit: problem.memoryLimit || 256,
        src_code: code,
        tests: allTests.map(t => ({
          input: t.input || " ",
          expected_output: t.expected || null
        }))
      });

      const batchId = response.data.batch_id;
      const wsUrl = getWsUrl();
      const ws = new WebSocket(`${wsUrl}/ws/runs/${batchId}`);
      activeWsRef.current = ws;
      let resolved = false;

      const accumulated = Array(allTests.length).fill(null);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Streaming format: single test result with test_index
          if (typeof data.test_index === 'number') {
            const r = {
              status: data.status || 'Error',
              std_out: data.std_out ?? '',
              message: data.message || '',
              execution_time_ms: data.execution_time_ms,
              peak_memory_mb: data.peak_memory_mb
            };
            accumulated[data.test_index] = r;
            const tab = allTests[data.test_index];
            if (tab) {
              setRunResults(prev => ({
                ...prev,
                [tab.tabId]: {
                  status: r.status,
                  output: r.std_out,
                  message: r.message || '',
                  expectedOutput: tab.expected,
                  time: r.execution_time_ms ? `${r.execution_time_ms.toFixed(1)}ms` : '-',
                  memory: r.peak_memory_mb ? `${r.peak_memory_mb.toFixed(1)}MB` : '-'
                }
              }));
            }
            return;
          }

          // Batch complete signal (streaming)
          if (data._batch_complete) {
            resolved = true;
            clearTimeout(safetyTimeoutRef.current);
            const updatedResults = {};
            allTests.forEach((t, i) => {
              const r = accumulated[i] || { status: 'Error', std_out: '', message: '' };
              updatedResults[t.tabId] = {
                status: r.status,
                output: r.std_out,
                message: r.message || '',
                expectedOutput: t.expected,
                time: r.execution_time_ms ? `${r.execution_time_ms.toFixed(1)}ms` : '-',
                memory: r.peak_memory_mb ? `${r.peak_memory_mb.toFixed(1)}MB` : '-'
              };
            });
            setRunResults(updatedResults);
            ws.close();
            setRunningTests(false);
            return;
          }

          // Legacy format: single message with data.results array
          const perTestResults = data.results || [];
          resolved = true;
          clearTimeout(safetyTimeoutRef.current);
          const updatedResults = {};
          allTests.forEach((t, i) => {
            const r = perTestResults[i] || { status: 'Error' };
            updatedResults[t.tabId] = {
              status: r.status,
              output: r.std_out,
              message: r.message || '',
              expectedOutput: t.expected,
              time: r.execution_time_ms ? `${r.execution_time_ms.toFixed(1)}ms` : '-',
              memory: r.peak_memory_mb ? `${r.peak_memory_mb.toFixed(1)}MB` : '-'
            };
          });
          setRunResults(updatedResults);
          ws.close();
          setRunningTests(false);
        } catch (e) {
          console.error("Failed to parse batch WS message:", e);
          const errResults = {};
          allTests.forEach(t => { errResults[t.tabId] = { status: 'Error' }; });
          setRunResults(errResults);
          resolved = true;
          ws.close();
          setRunningTests(false);
        }
      };

      const handleFail = () => {
        if (!resolved) {
          resolved = true;
          clearTimeout(safetyTimeoutRef.current);
          const errResults = {};
          allTests.forEach(t => { errResults[t.tabId] = { status: 'Error' }; });
          setRunResults(errResults);
          setRunningTests(false);
        }
      };

      ws.onerror = handleFail;
      ws.onclose = handleFail;

      safetyTimeoutRef.current = setTimeout(() => {
        if (!resolved) {
          ws.close();
          handleFail();
        }
      }, 60000);

    } catch (err) {
      console.error("Batch run failed", err);
      const errResults = {};
      allTests.forEach(t => { errResults[t.tabId] = { status: 'Error' }; });
      setRunResults(errResults);
      setRunningTests(false);
    }
  }, [customTests]);

  return {
    activeTab,
    setActiveTab,
    customTests,
    setCustomTests,
    runResults,
    runningTests,
    addCustomTest,
    updateCustomTest,
    deleteCustomTest,
    handleRunTests,
  };
};

export default useRunBatch;
