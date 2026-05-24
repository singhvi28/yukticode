import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Loader, Calendar, Clock, CheckCircle, ChevronRight, Trophy } from 'lucide-react';
import api from '../api';
import { useAuth } from '../context/AuthContext';

const ContestListPage = () => {
  const [contests, setContests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [registeringId, setRegisteringId] = useState(null);
  const [now, setNow] = useState(new Date());
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    const fetchContests = async () => {
      try {
        const res = await api.get('/contests');
        setContests(res.data || []);
        setNeedsAuth(false);
      } catch (err) {
        console.error('Failed to load contests', err);
        if (err.response?.status === 401) {
          setNeedsAuth(true);
          setContests([]);
        }
      } finally {
        setLoading(false);
      }
    };
    fetchContests();
  }, [user]);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleRegister = async (contestId) => {
    setRegisteringId(contestId);
    try {
      await api.post(`/contests/${contestId}/register`);
      setContests((prev) =>
        prev.map((c) => (c.id === contestId ? { ...c, is_registered: true } : c))
      );
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to register.');
    } finally {
      setRegisteringId(null);
    }
  };

  const getContestStatus = (start, end) => {
    if (!start || !end) return { status: 'UNKNOWN', text: '—', color: 'var(--text-muted)' };
    const startTime = new Date(start);
    const endTime = new Date(end);

    if (now < startTime) {
      const diff = startTime - now;
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const mins = Math.floor((diff / (1000 * 60)) % 60);
      return { status: 'UPCOMING', text: `Starts in ${hours}h ${mins}m`, color: 'var(--text-secondary)' };
    }
    if (now >= startTime && now <= endTime) {
      return { status: 'ACTIVE', text: 'Live Now', color: 'var(--success)' };
    }
    return { status: 'ENDED', text: 'Ended', color: 'var(--error)' };
  };

  if (loading) {
    return (
      <div className="loading-center">
        <Loader className="spin" size={32} />
      </div>
    );
  }

  if (needsAuth) {
    return (
      <div className="contest-hub animate-fade-in">
        <div className="hub-header">
          <h1>
            <Trophy size={28} style={{ color: 'var(--accent-primary)' }} /> Contest Arena
          </h1>
          <p>Please <Link to="/login?next=/contests">log in</Link> to browse and register for contests.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="contest-hub animate-fade-in">
      <div className="hub-header">
        <h1>
          <Trophy size={28} style={{ color: 'var(--accent-primary)' }} /> Contest Arena
        </h1>
        <p>Compete against others in real-time coding challenges.</p>
      </div>

      <div className="contest-list">
        {contests.length === 0 ? (
          <div className="empty-state">No contests available right now.</div>
        ) : (
          contests.map((contest) => {
            const { status, text, color } = getContestStatus(contest.start_time, contest.end_time);
            const isRegistering = registeringId === contest.id;

            return (
              <div
                key={contest.id}
                className={`contest-card glass-card ${status === 'ACTIVE' ? 'active-border' : ''}`}
              >
                <div className="contest-info">
                  <h2>{contest.title}</h2>
                  <p className="contest-desc">{contest.description}</p>
                  <div className="contest-meta">
                    <span style={{ color }} className="status-badge">
                      {status === 'ACTIVE' && <span className="live-dot" />}
                      {text}
                    </span>
                    <span>
                      <Calendar size={14} />
                      {contest.start_time ? new Date(contest.start_time).toLocaleDateString() : '—'}
                    </span>
                    <span>
                      <Clock size={14} />
                      {contest.start_time
                        ? new Date(contest.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : '—'}
                    </span>
                  </div>
                </div>

                <div className="contest-actions">
                  {status === 'ENDED' ? (
                    <button
                      className="btn btn-secondary"
                      onClick={() => navigate(`/contests/${contest.id}/leaderboard`)}
                    >
                      Final Standings
                    </button>
                  ) : contest.is_registered ? (
                    <button
                      className="btn btn-primary"
                      disabled={status === 'UPCOMING'}
                      onClick={() => navigate(`/contests/${contest.id}`)}
                    >
                      {status === 'UPCOMING' ? (
                        <>
                          <CheckCircle size={16} /> Registered
                        </>
                      ) : (
                        <>
                          Enter Contest <ChevronRight size={16} />
                        </>
                      )}
                    </button>
                  ) : (
                    <button
                      className="btn btn-primary outline"
                      onClick={() => handleRegister(contest.id)}
                      disabled={isRegistering}
                    >
                      {isRegistering ? <Loader size={16} className="spin" /> : 'Register Now'}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <style>{`
        .contest-hub { max-width: 900px; margin: 0 auto; padding: 2rem; }
        .hub-header { margin-bottom: 2rem; text-align: center; }
        .hub-header h1 { display: flex; align-items: center; justify-content: center; gap: 0.75rem; font-size: 2.5rem; margin-bottom: 0.5rem; }
        .hub-header p { color: var(--text-secondary); font-size: 1.1rem; }
        .contest-list { display: flex; flex-direction: column; gap: 1rem; }
        .contest-card { display: flex; justify-content: space-between; align-items: center; padding: 1.5rem; transition: transform 0.2s; }
        .contest-card:hover { transform: translateY(-2px); }
        .active-border { border-color: rgba(16, 185, 129, 0.4); box-shadow: 0 0 15px rgba(16, 185, 129, 0.1); }
        .contest-info h2 { font-size: 1.4rem; margin-bottom: 0.25rem; }
        .contest-desc { color: var(--text-secondary); margin-bottom: 1rem; font-size: 0.95rem; }
        .contest-meta { display: flex; gap: 1.5rem; font-size: 0.85rem; color: var(--text-muted); font-weight: 500; }
        .contest-meta span { display: flex; align-items: center; gap: 0.4rem; }
        .status-badge { font-weight: 700; background: rgba(255,255,255,0.05); padding: 0.25rem 0.6rem; border-radius: 1rem; }
        .live-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 1.5s infinite; margin-right: 0.25rem; }
        .contest-actions .btn { min-width: 140px; justify-content: center; }
        .btn.outline { background: transparent; border: 1px solid var(--accent-primary); color: var(--accent-primary); }
        .btn.outline:hover { background: rgba(71, 85, 105, 0.2); }
        .loading-center { display: flex; justify-content: center; align-items: center; min-height: 200px; }
        .empty-state { text-align: center; color: var(--text-muted); padding: 2rem; }
        @keyframes pulse {
          0% { transform: scale(0.95); opacity: 1; }
          70% { transform: scale(1); opacity: 0.8; }
          100% { transform: scale(0.95); opacity: 1; }
        }
        @media (max-width: 640px) {
          .contest-card { flex-direction: column; align-items: flex-start; gap: 1.5rem; }
          .contest-actions { width: 100%; }
          .contest-actions .btn { width: 100%; }
        }
      `}</style>
    </div>
  );
};

export default ContestListPage;
