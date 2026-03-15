import React, { useState, useEffect, useRef } from 'react';
import { Loader, Trophy } from 'lucide-react';
import api from '../api';

const SSE_HEARTBEAT_SECONDS = 15;

const ContestLeaderboard = ({ contestId, limit = 100 }) => {
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [nextUpdateInSeconds, setNextUpdateInSeconds] = useState(SSE_HEARTBEAT_SECONDS);
  const [reconnecting, setReconnecting] = useState(false);
  const abortRef = useRef(null);
  const countdownRef = useRef(null);

  useEffect(() => {
    if (!contestId) return;

    const baseURL = api.defaults.baseURL || '';
    const token = localStorage.getItem('access_token');
    const url = `${baseURL}/contests/${contestId}/leaderboard/stream`;

    const resetCountdown = () => {
      setNextUpdateInSeconds(SSE_HEARTBEAT_SECONDS);
    };

    let reader = null;
    let buffer = '';

    const connect = async () => {
      abortRef.current = new AbortController();
      const headers = { Accept: 'text/event-stream' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      try {
        const res = await fetch(url, { headers, signal: abortRef.current.signal });
        if (!res.ok || !res.body) {
          throw new Error('Stream failed');
        }
        setLoading(false);
        setReconnecting(false);
        reader = res.body.getReader();
        const decoder = new TextDecoder();
        buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split('\n\n');
          buffer = events.pop() || '';
          for (const eventBlock of events) {
            const lines = eventBlock.split('\n');
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const payload = JSON.parse(line.slice(6));
                  if (payload.leaderboard) {
                    setLeaderboard(payload.leaderboard);
                    resetCountdown();
                  }
                } catch (_) {}
                break;
              }
            }
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') return;
        console.error('Leaderboard SSE error', err);
        setReconnecting(true);
        setNextUpdateInSeconds(SSE_HEARTBEAT_SECONDS);
        setTimeout(connect, 3000);
      }
    };

    connect();

    // Countdown tick every second
    countdownRef.current = setInterval(() => {
      setNextUpdateInSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (reader) reader.cancel?.();
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [contestId]);

  if (loading) {
    return (
      <div className="leaderboard-loading">
        <Loader className="spinner" size={24} />
      </div>
    );
  }

  return (
    <div className="leaderboard-container glass-card">
      <h3 className="leaderboard-title">
        <Trophy size={18} /> Live Rankings
      </h3>
      <p className="leaderboard-countdown">
        Leaderboard will be updated in {nextUpdateInSeconds} seconds
      </p>
      {reconnecting && (
        <p className="leaderboard-reconnecting">Reconnecting…</p>
      )}
      <table className="leaderboard-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>User</th>
            <th>Score</th>
            <th>Penalty (Mins)</th>
          </tr>
        </thead>
        <tbody>
          {leaderboard.map((row) => (
            <tr key={row.user_id}>
              <td>{row.rank}</td>
              <td className="font-bold">{row.username}</td>
              <td className="text-success">{row.score}</td>
              <td className="text-warning">{row.penalty}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {leaderboard.length === 0 && (
        <p className="leaderboard-empty">No submissions yet.</p>
      )}
      <style>{`
        .leaderboard-container { padding: 1rem; }
        .leaderboard-title { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-size: 1.1rem; }
        .leaderboard-countdown { font-size: 0.8rem; color: var(--text-muted); margin: 0 0 0.75rem 0; }
        .leaderboard-reconnecting { font-size: 0.8rem; color: var(--warning); margin: 0 0 0.5rem 0; }
        .leaderboard-loading { display: flex; justify-content: center; padding: 2rem; }
        .leaderboard-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        .leaderboard-table th, .leaderboard-table td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border-light); }
        .leaderboard-table th { color: var(--text-muted); font-weight: 500; }
        .text-success { color: var(--success); }
        .text-warning { color: var(--warning); }
        .leaderboard-empty { color: var(--text-muted); padding: 1rem; margin: 0; font-size: 0.9rem; }
      `}</style>
    </div>
  );
};

export default ContestLeaderboard;
