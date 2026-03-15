import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Loader, ArrowLeft } from 'lucide-react';
import api from '../api';
import ContestLeaderboard from '../components/ContestLeaderboard';

const ContestLeaderboardPage = () => {
  const { id } = useParams();
  const [contestTitle, setContestTitle] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchContest = async () => {
      try {
        const res = await api.get(`/contests/${id}`);
        setContestTitle(res.data?.title || 'Leaderboard');
      } catch {
        setContestTitle('Leaderboard');
      } finally {
        setLoading(false);
      }
    };
    if (id) fetchContest();
  }, [id]);

  return (
    <div className="contest-leaderboard-page animate-fade-in">
      <div className="lb-page-header glass-card">
        <Link to={`/contests/${id}`} className="btn btn-ghost back-btn">
          <ArrowLeft size={18} /> Back to contest
        </Link>
        <h1>{loading ? <Loader size={24} className="spin" /> : contestTitle} — Standings</h1>
      </div>
      <div className="lb-page-content">
        <ContestLeaderboard contestId={Number(id)} limit={100} />
      </div>
      <style>{`
        .contest-leaderboard-page { max-width: 700px; margin: 0 auto; padding: 1.5rem; }
        .lb-page-header { padding: 1.5rem; margin-bottom: 1.5rem; }
        .back-btn { display: inline-flex; align-items: center; gap: 0.5rem; color: var(--text-secondary); margin-bottom: 0.75rem; }
        .back-btn:hover { color: var(--text-primary); }
        .lb-page-header h1 { font-size: 1.5rem; margin: 0; }
      `}</style>
    </div>
  );
};

export default ContestLeaderboardPage;
