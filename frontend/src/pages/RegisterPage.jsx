import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Code2, ArrowRight, Loader } from 'lucide-react';

const RegisterPage = () => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setIsSubmitting(true);

    try {
      await register(username, email, password);
      // Optional: Auto login after register, or just redirect to login
      navigate('/login');
    } catch (err) {
      // Check FastAPI validation errors
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          setError(err.response.data.detail[0].msg);
        } else {
          setError(err.response.data.detail);
        }
      } else {
        setError('Failed to create account. Please try again later.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-container animate-fade-in">
      <div className="auth-card glass-card shadow-premium">
        <div className="auth-header">
          <Code2 size={40} className="auth-logo" />
          <h2>Join YuktiCode</h2>
          <p>Create an account to start your journey</p>
        </div>

        {error && <div className="auth-error">{error}</div>}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              className="form-control"
              placeholder="Choose a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
            />
          </div>

          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              className="form-control"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-control"
              placeholder="Create a password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              className="form-control"
              placeholder="Confirm your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary auth-submit mx-auto mt-2"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <><Loader size={18} className="spinner" /> Creating Account...</>
            ) : (
              <>Sign Up <ArrowRight size={18} /></>
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>Already have an account? <Link to="/login">Sign in</Link></p>
        </div>
      </div>

      <style jsx>{`
        /* Styles are shared with LoginPage intentionally for consistency */
        .auth-container {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
        }

        .auth-card {
          width: 100%;
          max-width: 440px;
          padding: 2.5rem;
          box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }

        .auth-header {
          text-align: center;
          margin-bottom: 2rem;
        }

        .auth-logo {
          color: var(--accent-primary);
          margin-bottom: 1rem;
        }

        .auth-header h2 {
          font-size: 1.75rem;
          margin-bottom: 0.5rem;
        }

        .auth-header p {
          color: var(--text-secondary);
        }

        .auth-error {
          background-color: var(--error-bg);
          color: var(--error);
          padding: 0.75rem;
          border-radius: 0.5rem;
          margin-bottom: 1.5rem;
          font-size: 0.875rem;
          text-align: center;
          border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .form-group {
          margin-bottom: 1.25rem;
        }

        .form-group label {
          display: block;
          margin-bottom: 0.5rem;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .form-control {
          width: 100%;
          padding: 0.75rem 1rem;
          background-color: rgba(15, 23, 42, 0.5);
          border: 1px solid var(--border-color);
          border-radius: 0.5rem;
          color: var(--text-primary);
          font-family: var(--font-sans);
          transition: all 0.2s ease;
        }

        .form-control:focus {
          outline: none;
          border-color: var(--accent-primary);
          box-shadow: 0 0 0 2px var(--accent-glow);
        }

        .auth-submit {
          width: 100%;
          justify-content: center;
          padding: 0.875rem;
          font-size: 1rem;
          margin-top: 1.5rem;
        }

        .auth-footer {
          margin-top: 2rem;
          text-align: center;
          color: var(--text-secondary);
        }

        .auth-footer a {
          color: var(--accent-primary);
          font-weight: 500;
        }

        .spinner {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default RegisterPage;
