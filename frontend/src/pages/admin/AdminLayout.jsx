import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, FileText, Trophy, LogOut, ChevronRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

const NAV_ITEMS = [
    { to: '/admin/problems', icon: FileText, label: 'Problems' },
    { to: '/admin/contests', icon: Trophy, label: 'Contests' },
];

const AdminLayout = () => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate('/');
    };

    return (
        <div className="admin-shell">
            {/* Sidebar */}
            <aside className="admin-sidebar glass-card">
                <div className="sidebar-brand">
                    <LayoutDashboard size={20} />
                    <span>Admin Panel</span>
                </div>

                <div className="sidebar-user">
                    <div className="user-avatar">{user?.username?.[0]?.toUpperCase() ?? 'A'}</div>
                    <div>
                        <p className="user-name">{user?.username}</p>
                        <p className="user-role">Administrator</p>
                    </div>
                </div>

                <nav className="sidebar-nav">
                    {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
                        <NavLink
                            key={to}
                            to={to}
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                        >
                            <Icon size={18} />
                            <span>{label}</span>
                            <ChevronRight size={14} className="nav-arrow" />
                        </NavLink>
                    ))}
                </nav>

                <button className="logout-btn" onClick={handleLogout}>
                    <LogOut size={16} />
                    Logout
                </button>
            </aside>

            {/* Main content */}
            <main className="admin-content">
                <Outlet />
            </main>

            <style>{`
        .admin-shell {
          display: flex;
          min-height: calc(100vh - 64px);
          background: var(--bg-darker);
        }

        .admin-sidebar {
          width: 260px;
          min-width: 260px;
          display: flex;
          flex-direction: column;
          padding: 1.5rem;
          border-radius: 0;
          border-top: none;
          border-bottom: none;
          border-left: none;
          gap: 1.5rem;
          position: sticky;
          top: 64px;
          height: calc(100vh - 64px);
          overflow-y: auto;
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          font-size: 1.1rem;
          font-weight: 700;
          color: var(--accent-primary);
          padding-bottom: 1rem;
          border-bottom: 1px solid var(--border-color);
        }

        .sidebar-user {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem;
          background: rgba(255,255,255,0.03);
          border-radius: 0.75rem;
        }

        .user-avatar {
          width: 38px;
          height: 38px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--accent-primary), #7c3aed);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.95rem;
          flex-shrink: 0;
        }

        .user-name {
          font-weight: 600;
          font-size: 0.9rem;
          color: var(--text-primary);
        }

        .user-role {
          font-size: 0.75rem;
          color: var(--accent-primary);
          font-weight: 500;
        }

        .sidebar-nav {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          flex: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          border-radius: 0.6rem;
          color: var(--text-secondary);
          font-weight: 500;
          font-size: 0.9rem;
          transition: all 0.2s;
          text-decoration: none;
        }

        .nav-arrow {
          margin-left: auto;
          opacity: 0;
          transition: opacity 0.2s, transform 0.2s;
        }

        .nav-item:hover {
          background: rgba(59, 130, 246, 0.1);
          color: var(--text-primary);
        }

        .nav-item:hover .nav-arrow {
          opacity: 1;
          transform: translateX(2px);
        }

        .nav-item.active {
          background: rgba(59, 130, 246, 0.15);
          color: var(--accent-primary);
          border: 1px solid rgba(59, 130, 246, 0.2);
        }

        .nav-item.active .nav-arrow {
          opacity: 1;
          color: var(--accent-primary);
        }

        .logout-btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.6rem 0.75rem;
          background: rgba(239, 68, 68, 0.08);
          color: var(--error);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 0.6rem;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
          width: 100%;
          font-family: inherit;
        }

        .logout-btn:hover {
          background: rgba(239, 68, 68, 0.15);
        }

        .admin-content {
          flex: 1;
          padding: 2rem;
          overflow-y: auto;
          min-height: 100%;
        }

        @media (max-width: 768px) {
          .admin-shell { flex-direction: column; }
          .admin-sidebar {
            width: 100%;
            height: auto;
            position: static;
            border-radius: 0;
            border: none;
            border-bottom: 1px solid var(--border-color);
          }
        }
      `}</style>
        </div>
    );
};

export default AdminLayout;
