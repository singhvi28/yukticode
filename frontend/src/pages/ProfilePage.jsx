import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { User, Calendar, Activity, Code2, Loader } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../api';

const ProfilePage = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState({ solved: 0, total: 0, loading: true });

  useEffect(() => {
    if (!user) return;
    const load = async () => {
      try {
        const res = await api.get('/submissions');
        const subs = res.data || [];
        const solvedIds = new Set(
          subs.filter((s) => s.status === 'AC').map((s) => s.problem_id)
        );
        setStats({ solved: solvedIds.size, total: subs.length, loading: false });
      } catch {
        setStats({ solved: 0, total: 0, loading: false });
      }
    };
    load();
  }, [user]);

  if (!user) {
    return (
      <div className="container empty-state-container animate-fade-in">
        <div className="glass-card text-center p-8">
          <h2>Please login to view your profile</h2>
          <Link to="/login" className="btn btn-primary mt-4">Login</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container profile-page animate-fade-in">
      <div className="profile-grid">
        <div className="profile-sidebar glass-card">
          <div className="avatar">{user.username.charAt(0).toUpperCase()}</div>
          <h2 className="username">{user.username}</h2>
          <p className="email">{user.email}</p>
          <div className="user-details">
            <div className="detail-item">
              <Activity size={16} />
              <span>{user.is_active ? 'Active' : 'Inactive'}</span>
            </div>
            {user.is_admin && (
              <div className="detail-item admin-badge">Admin</div>
            )}
          </div>
        </div>

        <div className="profile-content">
          <div className="stats-cards">
            <div className="stat-card glass-card border-green">
              <div className="stat-icon bg-green">
                <Code2 size={24} />
              </div>
              <div className="stat-info">
                <h3>Problems Solved</h3>
                <div className="stat-value text-green">
                  {stats.loading ? <Loader size={20} className="spin" /> : stats.solved}
                </div>
              </div>
            </div>
            <div className="stat-card glass-card border-blue">
              <div className="stat-icon bg-blue">
                <User size={24} />
              </div>
              <div className="stat-info">
                <h3>Total Submissions</h3>
                <div className="stat-value text-blue">
                  {stats.loading ? <Loader size={20} className="spin" /> : stats.total}
                </div>
              </div>
            </div>
          </div>

          <div className="glass-card recent-card">
            <h3>Quick links</h3>
            <div className="quick-links">
              <Link to="/submissions" className="btn btn-secondary">My Submissions</Link>
              <Link to="/problems" className="btn btn-primary">Solve Problems</Link>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        .profile-page, .empty-state-container { padding: 3rem 1.5rem; }
        .p-8 { padding: 4rem 2rem; }
        .mt-4 { margin-top: 1rem; }
        .text-center { text-align: center; }
        .profile-grid { display: grid; grid-template-columns: 280px 1fr; gap: 1.5rem; }
        @media (max-width: 800px) { .profile-grid { grid-template-columns: 1fr; } }
        .profile-sidebar { padding: 2rem; text-align: center; }
        .avatar {
          width: 72px; height: 72px; margin: 0 auto 1rem;
          border-radius: 50%; background: var(--accent-glow);
          display: flex; align-items: center; justify-content: center;
          font-size: 1.75rem; font-weight: 700; color: var(--accent-primary);
        }
        .username { font-size: 1.35rem; margin-bottom: 0.25rem; }
        .email { color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1.25rem; }
        .user-details { display: flex; flex-direction: column; gap: 0.5rem; align-items: center; }
        .detail-item { display: flex; align-items: center; gap: 0.4rem; color: var(--text-secondary); font-size: 0.9rem; }
        .admin-badge { color: var(--accent-primary); font-weight: 600; }
        .stats-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
        @media (max-width: 600px) { .stats-cards { grid-template-columns: 1fr; } }
        .stat-card { padding: 1.25rem; display: flex; gap: 1rem; align-items: center; }
        .stat-icon { width: 48px; height: 48px; border-radius: 0.75rem; display: flex; align-items: center; justify-content: center; }
        .bg-green { background: var(--success-bg); color: var(--success); }
        .bg-blue { background: rgba(59,130,246,0.15); color: var(--accent-primary); }
        .border-green { border: 1px solid rgba(16,185,129,0.2); }
        .border-blue { border: 1px solid rgba(59,130,246,0.2); }
        .stat-info h3 { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.35rem; }
        .stat-value { font-size: 1.75rem; font-weight: 700; }
        .text-green { color: var(--success); }
        .text-blue { color: var(--accent-primary); }
        .recent-card { padding: 1.5rem; }
        .recent-card h3 { margin-bottom: 1rem; }
        .quick-links { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

export default ProfilePage;
