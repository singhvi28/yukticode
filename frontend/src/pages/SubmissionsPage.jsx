import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Loader, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';
import api from '../api';
import { useAuth } from '../context/AuthContext';

const SubmissionsPage = () => {
    const [submissions, setSubmissions] = useState([]);
    const [loading, setLoading] = useState(true);
    const { user } = useAuth();

    useEffect(() => {
        const fetchSubmissions = async () => {
            try {
                const response = await api.get('/submissions');
                setSubmissions(response.data);
            } catch (error) {
                console.error("Failed to fetch submissions", error);
                // Fallback mock data
                setSubmissions([
                    { id: 1042, problem_id: 1, problem_title: 'Two Sum', status: 'AC', language: 'python', time: '45ms', memory: '14MB', date: new Date().toISOString() },
                    { id: 1041, problem_id: 1, problem_title: 'Two Sum', status: 'WA', language: 'python', time: '12ms', memory: '14MB', date: new Date(Date.now() - 3600000).toISOString() },
                    { id: 1040, problem_id: 3, problem_title: 'Longest Substring...', status: 'TLE', language: 'cpp', time: '2010ms', memory: '8MB', date: new Date(Date.now() - 86400000).toISOString() },
                    { id: 1039, problem_id: 4, problem_title: 'Median of Two...', status: 'AC', language: 'cpp', time: '8ms', memory: '5MB', date: new Date(Date.now() - 172800000).toISOString() },
                ]);
            } finally {
                setLoading(false);
            }
        };

        fetchSubmissions();
    }, []);

    const getStatusBadge = (status) => {
        switch (status) {
            case 'AC':
                return <span className="status-badge ac"><CheckCircle size={14} /> Accepted</span>;
            case 'WA':
                return <span className="status-badge wa"><XCircle size={14} /> Wrong Answer</span>;
            case 'TLE':
                return <span className="status-badge tle"><Clock size={14} /> Time Limit</span>;
            case 'MLE':
            case 'RE':
            case 'CE':
                return <span className="status-badge error"><AlertTriangle size={14} /> {status}</span>;
            default:
                return <span className="status-badge pending"><Loader size={14} className="spinner" /> {status}</span>;
        }
    };

    const formatDate = (isoString) => {
        const d = new Date(isoString);
        return new Intl.DateTimeFormat('en-US', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        }).format(d);
    };

    if (!user && !loading) {
        return (
            <div className="container empty-state-container animate-fade-in">
                <div className="glass-card text-center p-8">
                    <h2>Please login to view your submissions</h2>
                    <Link to="/login" className="btn btn-primary mt-4">Login</Link>
                </div>
            </div>
        );
    }

    return (
        <div className="container submissions-page animate-fade-in">
            <div className="page-header">
                <h1>My Submissions</h1>
                <p>Track your evaluation history and performance</p>
            </div>

            <div className="table-container glass-card">
                {loading ? (
                    <div className="loading-state">
                        <Loader size={32} className="spinner" />
                    </div>
                ) : (
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Time Submitted</th>
                                <th>Problem</th>
                                <th>Language</th>
                                <th>Status</th>
                                <th>Execution Time</th>
                                <th>Memory</th>
                            </tr>
                        </thead>
                        <tbody>
                            {submissions.map((sub) => (
                                <tr key={sub.id}>
                                    <td className="font-mono text-muted">#{sub.id}</td>
                                    <td>{formatDate(sub.date)}</td>
                                    <td>
                                        <Link to={`/problems/${sub.problem_id}`} className="hover-link">
                                            {sub.problem_title}
                                        </Link>
                                    </td>
                                    <td>
                                        <span className="lang-tag">{sub.language}</span>
                                    </td>
                                    <td>{getStatusBadge(sub.status)}</td>
                                    <td className="font-mono">{sub.time}</td>
                                    <td className="font-mono">{sub.memory}</td>
                                </tr>
                            ))}
                            {submissions.length === 0 && (
                                <tr>
                                    <td colSpan="7" className="text-center p-8 text-muted">
                                        You haven't made any submissions yet.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>

            <style jsx>{`
        .submissions-page, .empty-state-container {
          padding: 3rem 1.5rem;
        }
        
        .p-8 { padding: 4rem 2rem; }
        .mt-4 { margin-top: 1rem; }
        .text-center { text-align: center; }
        .text-muted { color: var(--text-muted); }
        .font-mono { font-family: var(--font-mono); }

        .page-header {
          margin-bottom: 2rem;
        }

        .page-header h1 {
          font-size: 2.5rem;
          margin-bottom: 0.5rem;
        }

        .page-header p {
          color: var(--text-secondary);
        }

        .table-container {
          overflow-x: auto;
        }

        .custom-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
        }

        .custom-table th {
          background: rgba(0, 0, 0, 0.2);
          padding: 1rem 1.5rem;
          font-weight: 600;
          color: var(--text-secondary);
          border-bottom: 1px solid var(--border-color);
        }

        .custom-table td {
          padding: 1rem 1.5rem;
          border-bottom: 1px solid var(--border-color);
        }

        .custom-table tbody tr:hover {
          background-color: rgba(255, 255, 255, 0.03);
        }

        .hover-link {
          color: var(--text-primary);
          font-weight: 500;
        }

        .hover-link:hover {
          color: var(--accent-primary);
        }

        .lang-tag {
          background: rgba(255,255,255,0.05);
          padding: 0.25rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.85rem;
          text-transform: capitalize;
        }

        .status-badge {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.35rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.875rem;
          font-weight: 600;
        }

        .status-badge.ac { color: var(--success); background: var(--success-bg); }
        .status-badge.wa { color: var(--error); background: var(--error-bg); }
        .status-badge.tle, .status-badge.error { color: var(--warning); background: var(--warning-bg); }
        .status-badge.pending { color: var(--text-secondary); background: rgba(255,255,255,0.1); }

        .loading-state {
          padding: 4rem;
          display: flex;
          justify-content: center;
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

export default SubmissionsPage;
