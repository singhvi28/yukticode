import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Code2, User, LogOut } from 'lucide-react';

const Navbar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <nav className="navbar glass-card">
      <div className="container nav-content">
        <Link to="/" className="nav-logo">
          <Code2 className="logo-icon" />
          <span>YuktiCode</span>
        </Link>

        <div className="nav-links">
          <Link to="/problems" className="nav-link">Problems</Link>
          <Link to="/submissions" className="nav-link">Submissions</Link>
        </div>

        <div className="nav-auth">
          {user ? (
            <div className="user-menu">
              <span className="user-greeting">
                <User size={16} />
                {user.username}
              </span>
              <button className="btn btn-secondary btn-sm" onClick={handleLogout}>
                <LogOut size={16} /> Logout
              </button>
            </div>
          ) : (
            <>
              <Link to="/login" className="btn btn-secondary">Login</Link>
              <Link to="/register" className="btn btn-primary">Sign Up</Link>
            </>
          )}
        </div>
      </div>

      <style jsx>{`
        .navbar {
          position: sticky;
          top: 0;
          z-index: 100;
          border-radius: 0;
          border-left: none;
          border-right: none;
          border-top: none;
          padding: 1rem 0;
        }
        
        .nav-content {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .nav-logo {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text-primary);
        }

        .logo-icon {
          color: var(--accent-primary);
        }

        .nav-links {
          display: flex;
          gap: 2rem;
        }

        .nav-link {
          font-weight: 500;
          color: var(--text-secondary);
        }

        .nav-link:hover {
          color: var(--text-primary);
        }

        .nav-auth {
          display: flex;
          gap: 1rem;
          align-items: center;
        }

        .btn-sm {
          padding: 0.35rem 0.75rem;
          font-size: 0.875rem;
        }

        .user-menu {
          display: flex;
          align-items: center;
          gap: 1.5rem;
        }

        .user-greeting {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-weight: 500;
          color: var(--accent-primary);
        }
      `}</style>
    </nav>
  );
};

export default Navbar;
