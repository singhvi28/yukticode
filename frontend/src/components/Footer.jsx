import React from 'react';

const Footer = () => {
  return (
    <footer className="footer">
      <div className="container footer-content">
        <div className="footer-brand">
          <span className="brand-name">YuktiCode</span>
          <p className="brand-tagline">Open Source Competitive Programming Platform</p>
        </div>

        <div className="footer-links">
          <div className="link-group">
            <h4>Platform</h4>
            <a href="/problems">Problems</a>
            <a href="/submissions">Submissions</a>
            <a href="/leaderboard">Leaderboard</a>
          </div>
        </div>
      </div>

      <div className="footer-bottom">
        <p>&copy; {new Date().getFullYear()} YuktiCode Online Judge. All rights reserved.</p>
      </div>

      <style jsx>{`
        .footer {
          margin-top: auto;
          background-color: var(--bg-card);
          border-top: 1px solid var(--border-color);
          padding-top: 3rem;
        }
        
        .footer-content {
          display: flex;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 2rem;
          margin-bottom: 3rem;
        }

        .brand-name {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-primary);
          display: block;
          margin-bottom: 0.5rem;
        }

        .brand-tagline {
          color: var(--text-muted);
        }

        .link-group h4 {
          color: var(--text-primary);
          margin-bottom: 1rem;
          font-size: 1rem;
        }

        .link-group a {
          display: block;
          color: var(--text-secondary);
          margin-bottom: 0.5rem;
          font-size: 0.9rem;
        }

        .link-group a:hover {
          color: var(--accent-primary);
        }

        .footer-bottom {
          text-align: center;
          padding: 1.5rem;
          border-top: 1px solid var(--border-color);
          color: var(--text-muted);
          font-size: 0.875rem;
        }
      `}</style>
    </footer>
  );
};

export default Footer;
