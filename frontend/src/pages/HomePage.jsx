import React from 'react';
import { Link } from 'react-router-dom';
import { Terminal, Zap, Trophy, Code } from 'lucide-react';

const HomePage = () => {
  return (
    <div className="home-page animate-fade-in">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-bg-glow"></div>
        <div className="container hero-content">
          <h1 className="hero-title">
            Master Competitive <br />
            <span className="text-gradient">Programming</span>
          </h1>
          <p className="hero-subtitle">
            An open-source, high-performance online judge for algorithmic problem solving.
            Practice coding challenges and compete on the leaderboard.
          </p>
          <div className="hero-actions">
            <Link to="/problems" className="btn btn-primary btn-lg">
              Start Solving
            </Link>
            <Link to="/register" className="btn btn-secondary btn-lg">
              Create Account
            </Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="features container">
        <div className="features-grid">
          <div className="feature-card glass-card">
            <div className="feature-icon bg-blue">
              <Zap size={24} />
            </div>
            <h3>Lightning Fast Execution</h3>
            <p>Code is judged asynchronously using independent RabbitMQ workers, providing instant feedback on submissions.</p>
          </div>

          <div className="feature-card glass-card">
            <div className="feature-icon bg-green">
              <Terminal size={24} />
            </div>
            <h3>Multiple Languages</h3>
            <p>Submit your solutions in C++, Python, Java, and and Javascript with secure, isolated Docker environments.</p>
          </div>

          <div className="feature-card glass-card">
            <div className="feature-icon bg-amber">
              <Code size={24} />
            </div>
            <h3>Rich Code Editor</h3>
            <p>Write standard code with syntax highlighting using the integrated Monaco Editor directly in your browser.</p>
          </div>
        </div>
      </section>

      {/* Styles */}
      <style jsx>{`
        .home-page {
          flex: 1;
          display: flex;
          flex-direction: column;
        }

        .hero {
          position: relative;
          padding: 8rem 0 6rem;
          text-align: center;
          overflow: hidden;
        }

        .hero-bg-glow {
          position: absolute;
          top: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 800px;
          height: 800px;
          background: radial-gradient(circle, var(--accent-glow) 0%, transparent 60%);
          opacity: 0.15;
          z-index: -1;
          pointer-events: none;
        }

        .hero-title {
          font-size: 4rem;
          font-weight: 800;
          line-height: 1.1;
          margin-bottom: 1.5rem;
          letter-spacing: -0.02em;
        }

        .text-gradient {
          background: linear-gradient(135deg, #475569 0%, #94a3b8 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .hero-subtitle {
          font-size: 1.25rem;
          color: var(--text-secondary);
          max-width: 600px;
          margin: 0 auto 3rem;
          line-height: 1.6;
        }

        .hero-actions {
          display: flex;
          justify-content: center;
          gap: 1rem;
        }

        .btn-lg {
          padding: 0.75rem 2rem;
          font-size: 1.125rem;
        }

        .features {
          padding: 4rem 0 8rem;
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 2rem;
        }

        .feature-card {
          padding: 2rem;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .feature-card:hover {
          transform: translateY(-5px);
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
          border-color: var(--accent-primary);
        }

        .feature-icon {
          width: 3rem;
          height: 3rem;
          border-radius: 0.75rem;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 1.5rem;
          color: white;
        }

        .bg-blue { background: rgba(71, 85, 105, 0.2); color: #94a3b8; }
        .bg-green { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .bg-amber { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

        .feature-card h3 {
          font-size: 1.25rem;
          margin-bottom: 1rem;
          color: var(--text-primary);
        }

        .feature-card p {
          color: var(--text-secondary);
          line-height: 1.6;
        }

        @media (max-width: 768px) {
          .hero-title {
            font-size: 3rem;
          }
          .hero {
            padding: 4rem 0 3rem;
          }
        }
      `}</style>
    </div>
  );
};

export default HomePage;
