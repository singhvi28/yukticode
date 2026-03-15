import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Loader, Calendar, Clock, Trophy, ArrowLeft, CheckCircle, XCircle } from 'lucide-react';
import api from '../api';
import ContestLeaderboard from '../components/ContestLeaderboard';

const ContestArenaPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [contest, setContest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const fetchContest = async () => {
      try {
        const res = await api.get(`/contests/${id}`);
        setContest(res.data);
      } catch (err) {
        console.error('Failed to load contest', err);
      } finally {
        setLoading(false);
      }
    };
    if (id) fetchContest();
  }, [id]);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const getStatus = () => {
    if (!contest?.start_time || !contest?.end_time)
      return { status: 'UNKNOWN', text: '—', color: 'var(--text-muted)' };
    const startTime = new Date(contest.start_time);
    const endTime = new Date(contest.end_time);
    if (now < startTime) {
      const diff = startTime - now;
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const mins = Math.floor((diff / (1000 * 60)) % 60);
      return { status: 'UPCOMING', text: `Starts in ${hours}h ${mins}m`, color: 'var(--text-secondary)' };
    }
    if (now >= startTime && now <= endTime) {
      const diff = endTime - now;
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const mins = Math.floor((diff / (1000 * 60)) % 60);
      return { status: 'ACTIVE', text: `Ends in ${hours}h ${mins}m`, color: 'var(--success)' };
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

  if (!contest) {
    return (
      <div className="contest-arena animate-fade-in">
        <p className="empty-state">Contest not found.</p>
        <button className="btn btn-secondary" onClick={() => navigate('/contests')}>
          Back to contests
        </button>
      </div>
    );
  }

  const { status, text, color } = getStatus();
  const problems = contest.problems || [];
  const canOpenProblems = status === 'ACTIVE' || status === 'ENDED';

  return (
    <div className="contest-arena animate-fade-in">
      <div className="arena-header glass-card">
        <button
          type="button"
          className="btn btn-ghost back-btn"
          onClick={() => navigate('/contests')}
          aria-label="Back to contests"
        >
          <ArrowLeft size={18} /> Back
        </button>
        <h1>{contest.title}</h1>
        {contest.description && <p className="arena-desc">{contest.description}</p>}
        <div className="arena-meta">
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
        {status === 'ENDED' && (
          <Link to={`/contests/${id}/leaderboard`} className="btn btn-primary">
            Final Standings
          </Link>
        )}
      </div>

      <div className="arena-body">
        <div className="arena-problems">
          <h2 className="problems-heading">Problems</h2>
          {problems.length === 0 ? (
            <p className="empty-state">No problems in this contest.</p>
          ) : (
            <ul className="problem-list">
              {problems.map((p) => (
                <li key={p.id}>
                  <Link
                    to={canOpenProblems ? `/problems/${p.id}?contest_id=${id}` : '#'}
                    className={`problem-link glass-card ${!canOpenProblems ? 'disabled' : ''}`}
                    onClick={(e) => !canOpenProblems && e.preventDefault()}
                  >
                    <span className="problem-title">{p.title}</span>
                    <div className="problem-right">
                      {(p.solved || (p.attempts != null && p.attempts > 0)) && (
                        <span className={`problem-status ${p.solved ? 'solved' : 'attempted'}`}>
                          {p.solved ? <><CheckCircle size={14} /> AC</> : <><XCircle size={14} /> {p.attempts} attempt{p.attempts !== 1 ? 's' : ''}</>}
                        </span>
                      )}
                      <span className="problem-score">{p.score} pts</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="arena-sidebar">
          <ContestLeaderboard contestId={Number(id)} limit={50} />
        </div>
      </div>

      <style>{`
        .contest-arena { max-width: 1100px; margin: 0 auto; padding: 1.5rem; }
        .arena-header { padding: 1.5rem; margin-bottom: 1.5rem; position: relative; }
        .back-btn { position: absolute; top: 1rem; left: 1rem; color: var(--text-secondary); }
        .back-btn:hover { color: var(--text-primary); }
        .arena-header h1 { font-size: 1.75rem; margin-bottom: 0.5rem; padding-top: 0.5rem; }
        .arena-desc { color: var(--text-secondary); margin-bottom: 1rem; font-size: 0.95rem; }
        .arena-meta { display: flex; gap: 1.5rem; font-size: 0.85rem; color: var(--text-muted); font-weight: 500; flex-wrap: wrap; }
        .arena-meta span { display: flex; align-items: center; gap: 0.4rem; }
        .status-badge { font-weight: 700; background: rgba(255,255,255,0.05); padding: 0.25rem 0.6rem; border-radius: 1rem; }
        .live-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; margin-right: 0.25rem; animation: pulse 1.5s infinite; }
        .arena-body { display: grid; grid-template-columns: 1fr 320px; gap: 1.5rem; }
        .arena-problems { min-width: 0; }
        .problems-heading { font-size: 1.1rem; margin-bottom: 1rem; }
        .problem-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }
        .problem-link { display: flex; justify-content: space-between; align-items: center; padding: 1rem; text-decoration: none; color: inherit; transition: background 0.2s; }
        .problem-link:hover:not(.disabled) { background: var(--bg-card-hover); }
        .problem-link.disabled { opacity: 0.7; cursor: not-allowed; }
        .problem-right { display: flex; align-items: center; gap: 0.75rem; }
        .problem-status { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; font-weight: 600; }
        .problem-status.solved { color: var(--success); }
        .problem-status.attempted { color: var(--warning); }
        .problem-score { color: var(--accent-primary); font-weight: 600; }
        .arena-sidebar { position: sticky; top: 6rem; height: fit-content; }
        .loading-center { display: flex; justify-content: center; align-items: center; min-height: 200px; }
        @keyframes pulse { 0% { opacity: 1; } 70% { opacity: 0.6; } 100% { opacity: 1; } }
        @media (max-width: 900px) {
          .arena-body { grid-template-columns: 1fr; }
          .arena-sidebar { position: static; }
        }
      `}</style>
    </div>
  );
};

export default ContestArenaPage;
