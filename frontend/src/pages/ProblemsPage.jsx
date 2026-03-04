import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, Loader } from 'lucide-react';
import api from '../api';

const ProblemsPage = () => {
    const [problems, setProblems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        const fetchProblems = async () => {
            try {
                const response = await api.get('/problems');
                setProblems(response.data);
            } catch (error) {
                console.error("Failed to fetch problems", error);
                // Fallback dummy data for UI development before backend is ready
                setProblems([
                    { id: 1, title: 'Two Sum', difficulty: 'Easy', acceptance: 65.4, tags: ['Array', 'Hash Table'] },
                    { id: 2, title: 'Add Two Numbers', difficulty: 'Medium', acceptance: 42.1, tags: ['Linked List', 'Math'] },
                    { id: 3, title: 'Longest Substring Without Repeating Characters', difficulty: 'Medium', acceptance: 34.2, tags: ['String', 'Sliding Window'] },
                    { id: 4, title: 'Median of Two Sorted Arrays', difficulty: 'Hard', acceptance: 38.6, tags: ['Array', 'Binary Search'] },
                    { id: 5, title: 'Longest Palindromic Substring', difficulty: 'Medium', acceptance: 33.1, tags: ['String', 'Dynamic Programming'] },
                ]);
            } finally {
                setLoading(false);
            }
        };

        fetchProblems();
    }, []);

    const filteredProblems = problems.filter(p =>
        p.title.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="container problems-page animate-fade-in">
            <div className="page-header">
                <h1>Problem Set</h1>
                <p>Browse and practice our collection of algorithmic challenges</p>
            </div>

            <div className="controls-bar glass-card">
                <div className="search-box">
                    <Search size={18} className="search-icon" />
                    <input
                        type="text"
                        placeholder="Search problems..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>
                <button className="btn btn-secondary">
                    <Filter size={18} /> Filters
                </button>
            </div>

            <div className="table-container glass-card">
                {loading ? (
                    <div className="loading-state">
                        <Loader size={32} className="spinner" />
                        <p>Loading problems...</p>
                    </div>
                ) : (
                    <table className="problems-table">
                        <thead>
                            <tr>
                                <th width="8%">#</th>
                                <th width="45%">Title</th>
                                <th width="15%">Difficulty</th>
                                <th width="12%">Acceptance</th>
                                <th width="20%">Tags</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredProblems.map((problem) => (
                                <tr key={problem.id}>
                                    <td>{problem.id}</td>
                                    <td>
                                        <Link to={`/problems/${problem.id}`} className="problem-link">
                                            {problem.title}
                                        </Link>
                                    </td>
                                    <td>
                                        <span className={`difficulty ${problem.difficulty?.toLowerCase() || 'medium'}`}>
                                            {problem.difficulty || 'Medium'}
                                        </span>
                                    </td>
                                    <td>{problem.acceptance?.toFixed(1) || '0.0'}%</td>
                                    <td>
                                        <div className="tags">
                                            {(problem.tags || []).slice(0, 2).map((tag, i) => (
                                                <span key={i} className="tag">{tag}</span>
                                            ))}
                                            {(problem.tags?.length || 0) > 2 && (
                                                <span className="tag tag-more">+{problem.tags.length - 2}</span>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {filteredProblems.length === 0 && (
                                <tr>
                                    <td colSpan="5" className="empty-state">No problems match your search</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>

            <style jsx>{`
        .problems-page {
          padding: 3rem 1.5rem;
        }

        .page-header {
          margin-bottom: 2rem;
        }

        .page-header h1 {
          font-size: 2.5rem;
          margin-bottom: 0.5rem;
        }

        .page-header p {
          color: var(--text-secondary);
          font-size: 1.125rem;
        }

        .controls-bar {
          display: flex;
          justify-content: space-between;
          padding: 1rem;
          margin-bottom: 2rem;
          gap: 1rem;
        }

        .search-box {
          position: relative;
          flex: 1;
          max-width: 400px;
        }

        .search-icon {
          position: absolute;
          left: 1rem;
          top: 50%;
          transform: translateY(-50%);
          color: var(--text-muted);
        }

        .search-box input {
          width: 100%;
          padding: 0.75rem 1rem 0.75rem 3rem;
          background: rgba(15, 23, 42, 0.5);
          border: 1px solid var(--border-color);
          border-radius: 0.5rem;
          color: var(--text-primary);
          font-family: inherit;
          transition: all 0.2s;
        }

        .search-box input:focus {
          outline: none;
          border-color: var(--accent-primary);
          box-shadow: 0 0 0 2px var(--accent-glow);
        }

        .table-container {
          overflow-x: auto;
        }

        .problems-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
        }

        .problems-table th {
          background: rgba(0, 0, 0, 0.2);
          padding: 1.25rem 1.5rem;
          font-weight: 600;
          color: var(--text-secondary);
          border-bottom: 1px solid var(--border-color);
        }

        .problems-table td {
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid var(--border-color);
        }

        .problems-table tbody tr {
          transition: background-color 0.2s;
        }

        .problems-table tbody tr:hover {
          background-color: rgba(255, 255, 255, 0.03);
        }

        .problem-link {
          font-weight: 500;
          color: var(--text-primary);
        }

        .problem-link:hover {
          color: var(--accent-primary);
        }

        .difficulty {
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.875rem;
          font-weight: 500;
        }

        .difficulty.easy { color: var(--success); background: var(--success-bg); }
        .difficulty.medium { color: var(--warning); background: var(--warning-bg); }
        .difficulty.hard { color: var(--error); background: var(--error-bg); }

        .tags {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .tag {
          padding: 0.25rem 0.5rem;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 0.25rem;
          font-size: 0.75rem;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .tag-more {
          background: rgba(59, 130, 246, 0.1);
          color: var(--accent-primary);
        }

        .loading-state, .empty-state {
          padding: 4rem 2rem;
          text-align: center;
          color: var(--text-secondary);
        }

        .spinner {
          animation: spin 1s linear infinite;
          margin-bottom: 1rem;
          color: var(--accent-primary);
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
        </div>
    );
};

export default ProblemsPage;
