import React from 'react';
import { useAuth } from '../context/AuthContext';
import { Trophy, Code2, Activity, Calendar } from 'lucide-react';
import { Link } from 'react-router-dom';

const ProfilePage = () => {
  const { user } = useAuth();

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

  // Derived mock stats (In a real app, these come from backend)
  const stats = {
    rating: user.rating || 1500,
    solved: user.total_submissions || 42,
    rank: 'Specialist',
    joinDate: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  };

  return (
    <div className="container profile-page animate-fade-in">
      <div className="profile-grid">
        {/* Left Column: User Info Card */}
        <div className="profile-sidebar glass-card">
          <div className="avatar">
            {user.username.charAt(0).toUpperCase()}
          </div>
          <h2 className="username">{user.username}</h2>
          <p className="rank-title">{stats.rank}</p>

          <div className="user-details">
            <div className="detail-item">
              <Calendar size={16} />
              <span>Joined {stats.joinDate}</span>
            </div>
            <div className="detail-item">
              <Activity size={16} />
              <span>{user.is_active ? 'Active' : 'Inactive'}</span>
            </div>
            {user.is_admin && (
              <div className="detail-item admin-badge">
                Admin
              </div>
            )}
          </div>

          <Link to="/settings" className="btn btn-secondary w-full mt-6 justify-center">
            Edit Profile
          </Link>
        </div>

        {/* Right Column: Statistics */}
        <div className="profile-content">
          <div className="stats-cards">
            <div className="stat-card glass-card border-blue">
              <div className="stat-icon bg-blue">
                <Trophy size={24} />
              </div>
              <div className="stat-info">
                <h3>Contest Rating</h3>
                <div className="stat-value text-blue">{stats.rating}</div>
              </div>
            </div>

            <div className="stat-card glass-card border-green">
              <div className="stat-icon bg-green">
                <Code2 size={24} />
              </div>
              <div className="stat-info">
                <h3>Problems Solved</h3>
                <div className="stat-value text-green">{stats.solved}</div>
              </div>
            </div>

            <div className="stat-card glass-card border-amber">
              <div className="stat-icon bg-amber">
                <Activity size={24} />
              </div>
              <div className="stat-info">
                <h3>Total Submissions</h3>
                <div className="stat-value text-amber">{stats.solved * 3}</div>
              </div>
            </div>
          </div>

          {/* Activity Heatmap Mock */}
          <div className="activity-section glass-card mt-6">
            <h3>Recent Activity</h3>
            <div className="activity-placeholder">
              <p className="text-muted">Activity heatmap will be displayed here.</p>
              <Link to="/submissions" className="btn btn-secondary btn-sm mt-4">View Submissions</Link>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        .profile-page {
          padding: 3rem 1.5rem;
        }

        .profile-grid {
          display: grid;
          grid-template-columns: 300px 1fr;
          gap: 2rem;
        }

        @media (max-width: 768px) {
          .profile-grid {
            grid-template-columns: 1fr;
          }
        }

        .profile-sidebar {
          padding: 2.5rem 2rem;
          text-align: center;
          height: fit-content;
        }

        .avatar {
          width: 120px;
          height: 120px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--accent-primary), var(--accent-hover));
          color: white;
          font-size: 3rem;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 1.5rem;
          box-shadow: 0 8px 16px rgba(71, 85, 105, 0.3);
        }

        .username {
          font-size: 1.75rem;
          margin-bottom: 0.25rem;
        }

        .rank-title {
          color: var(--warning);
          font-weight: 600;
          margin-bottom: 2rem;
        }

        .user-details {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          text-align: left;
          padding-top: 1.5rem;
          border-top: 1px solid var(--border-color);
        }

        .detail-item {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          color: var(--text-secondary);
          font-size: 0.95rem;
        }

        .admin-badge {
          background: var(--error-bg);
          color: var(--error);
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.75rem;
          font-weight: 600;
          width: fit-content;
        }

        .stats-cards {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 1.5rem;
        }

        .stat-card {
          padding: 1.5rem;
          display: flex;
          align-items: center;
          gap: 1.5rem;
        }

        .border-blue { border-left: 4px solid #475569; }
        .border-green { border-left: 4px solid #10b981; }
        .border-amber { border-left: 4px solid #f59e0b; }

        .stat-icon {
          width: 3.5rem;
          height: 3.5rem;
          border-radius: 1rem;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .bg-blue { background: rgba(71, 85, 105, 0.2); color: #94a3b8; }
        .bg-green { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .bg-amber { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

        .stat-info h3 {
          font-size: 0.875rem;
          color: var(--text-secondary);
          margin-bottom: 0.25rem;
        }

        .stat-value {
          font-size: 1.75rem;
          font-weight: 700;
        }

        .text-blue { color: #94a3b8; }
        .text-green { color: #34d399; }
        .text-amber { color: #fbbf24; }

        .activity-section {
          padding: 2rem;
        }

        .activity-section h3 {
          margin-bottom: 1.5rem;
          font-size: 1.25rem;
        }

        .activity-placeholder {
          height: 200px;
          border: 1px dashed var(--border-color);
          border-radius: 0.5rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: rgba(0,0,0,0.1);
        }

        /* Utils */
        .w-full { width: 100%; }
        .mt-6 { margin-top: 1.5rem; }
        .mt-4 { margin-top: 1rem; }
        .justify-center { justify-content: center; }
        .text-center { text-align: center; }
        .text-muted { color: var(--text-muted); }
        .p-8 { padding: 4rem 2rem; }
      `}</style>
    </div>
  );
};

export default ProfilePage;
