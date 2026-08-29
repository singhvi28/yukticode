import { useState, useRef, useEffect, useCallback } from 'react';
import api, { getWsUrl } from '../api';

export const useSubmission = () => {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const activeWsRef = useRef(null);
  const judgingTimerRef = useRef(null);
  const pollTimerRef = useRef(null);
  const safetyTimeoutRef = useRef(null);
  const wsResolvedRef = useRef(false);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(judgingTimerRef.current);
      clearTimeout(pollTimerRef.current);
      clearTimeout(safetyTimeoutRef.current);
      if (activeWsRef.current) {
        activeWsRef.current.close();
      }
    };
  }, []);

  const handleSubmit = useCallback(async ({ problemId, language, code, contestId, user }) => {
    if (!user) {
      alert("Please login to submit code");
      return;
    }

    setSubmitting(true);
    setResult(null);
    wsResolvedRef.current = false;

    let submissionId;
    const payload = {
      problem_id: Number(problemId),
      language: language === 'python' ? 'py' : language,
      src_code: code
    };
    if (contestId) payload.contest_id = Number(contestId);

    try {
      const response = await api.post('/submit', payload);
      submissionId = response.data.submission_id;
    } catch (err) {
      console.error("Submission failed", err);
      setResult({ status: 'Error', message: 'Failed to submit code' });
      setSubmitting(false);
      return;
    }

    // Show "Judging" state after a 200ms delay to avoid flash when fast cached results arrive
    clearTimeout(judgingTimerRef.current);
    judgingTimerRef.current = setTimeout(() => {
      setResult({ status: 'JUDGING' });
    }, 200);

    const applyResult = (data) => {
      wsResolvedRef.current = true;
      clearTimeout(judgingTimerRef.current);
      clearTimeout(pollTimerRef.current);
      clearTimeout(safetyTimeoutRef.current);

      setResult({
        status: data.status,
        time: data.execution_time_ms ? `${data.execution_time_ms.toFixed(1)}ms` : '-',
        memory: data.peak_memory_mb ? `${data.peak_memory_mb.toFixed(1)}MB` : '-',
        message: data.message || (data.status !== 'AC' ? `Verdict: ${data.status}` : '')
      });
      setSubmitting(false);
    };

    // Polling fallback if WebSocket closes or fails
    const startPolling = () => {
      if (wsResolvedRef.current) return;
      const pollStatus = async () => {
        if (wsResolvedRef.current) return;
        try {
          const res = await api.get(`/submissions/${submissionId}`);
          const { status, execution_time_ms, peak_memory_mb } = res.data;
          if (status === 'PENDING') {
            pollTimerRef.current = setTimeout(pollStatus, 1000);
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

    const wsUrl = getWsUrl();
    try {
      const ws = new WebSocket(`${wsUrl}/ws/submissions/${submissionId}`);
      activeWsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          applyResult(data);
        } catch {
          startPolling();
        }
        ws.close();
      };

      ws.onerror = () => {
        console.warn("WebSocket error — falling back to polling");
        startPolling();
      };

      ws.onclose = () => {
        if (!wsResolvedRef.current) startPolling();
      };

      // 30s fallback timeout
      safetyTimeoutRef.current = setTimeout(() => {
        if (!wsResolvedRef.current) {
          ws.close();
          startPolling();
        }
      }, 30000);

    } catch (wsErr) {
      console.warn("Unable to open WebSocket, using polling:", wsErr);
      startPolling();
    }
  }, []);

  return {
    submitting,
    result,
    setResult,
    handleSubmit,
  };
};

export default useSubmission;
