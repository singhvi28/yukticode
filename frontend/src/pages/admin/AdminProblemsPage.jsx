import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Plus, Pencil, Trash2, Eye, EyeOff, Loader, AlertCircle, CheckCircle } from 'lucide-react';
import api from '../../api';

const AdminProblemsPage = () => {
    const [problems, setProblems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ title: '', statement: '', time_limit_ms: 2000, memory_limit_mb: 256 });
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState(null);
    const navigate = useNavigate();

    const fetchProblems = async () => {
        try {
            setLoading(true);
            const r = await api.get('/admin/problems');
            setProblems(r.data);
        } catch (e) {
            setError('Failed to load problems. Are you an admin?');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchProblems(); }, []);

    const showToast = (msg, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 3000);
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post('/admin/problems', form);
            showToast('Problem created!');
            setShowForm(false);
            setForm({ title: '', statement: '', time_limit_ms: 2000, memory_limit_mb: 256 });
            fetchProblems();
        } catch (e) {
            showToast(e.response?.data?.detail || 'Failed to create', false);
        } finally {
            setSaving(false);
        }
    };

    const togglePublish = async (p) => {
        try {
            await api.patch(`/admin/problems/${p.id}`, { is_published: !p.is_published });
            showToast(p.is_published ? 'Unpublished' : 'Published!');
            fetchProblems();
        } catch {
            showToast('Update failed', false);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Delete this problem permanently?')) return;
        try {
            await api.delete(`/admin/problems/${id}`);
            showToast('Deleted');
            fetchProblems();
        } catch {
            showToast('Delete failed', false);
        }
    };

    return (
        <div className="admin-problems animate-fade-in">
            {toast && (
                <div className={`toast ${toast.ok ? 'toast-ok' : 'toast-err'}`}>
                    {toast.ok ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                    {toast.msg}
                </div>
            )}

            <div className="ap-header">
                <div>
                    <h1 className="ap-title">Problems</h1>
                    <p className="ap-subtitle">Create, edit and publish problems</p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowForm(v => !v)} id="new-problem-btn">
                    <Plus size={16} /> New Problem
                </button>
            </div>

            {showForm && (
                <form className="create-form glass-card" onSubmit={handleCreate} id="create-problem-form">
                    <h3>New Problem</h3>
                    <div className="form-row">
                        <label>Title</label>
                        <input required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Two Sum" id="problem-title-input" />
                    </div>
                    <div className="form-row">
                        <label>Statement (Markdown)</label>
                        <textarea rows={5} value={form.statement} onChange={e => setForm(f => ({ ...f, statement: e.target.value }))} placeholder="## Problem statement..." id="problem-statement-input" />
                    </div>
                    <div className="form-grid-2">
                        <div className="form-row">
                            <label>Time Limit (ms)</label>
                            <input type="number" value={form.time_limit_ms} onChange={e => setForm(f => ({ ...f, time_limit_ms: +e.target.value }))} id="time-limit-input" />
                        </div>
                        <div className="form-row">
                            <label>Memory Limit (MB)</label>
                            <input type="number" value={form.memory_limit_mb} onChange={e => setForm(f => ({ ...f, memory_limit_mb: +e.target.value }))} id="memory-limit-input" />
                        </div>
                    </div>
                    <div className="form-actions">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={saving} id="create-problem-submit">
                            {saving ? <Loader size={14} className="spin" /> : <Plus size={14} />} Create
                        </button>
                    </div>
                </form>
            )}

            {loading ? (
                <div className="loading-center"><Loader size={28} className="spin" /> Loading...</div>
            ) : error ? (
                <div className="error-banner"><AlertCircle size={16} /> {error}</div>
            ) : (
                <div className="glass-card overflow-card">
                    <table className="admin-table" id="problems-table">
                        <thead>
                            <tr>
                                <th>#</th><th>Title</th><th>Status</th><th>Created</th><th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {problems.map(p => (
                                <tr key={p.id} id={`problem-row-${p.id}`}>
                                    <td className="muted">{p.id}</td>
                                    <td><span className="problem-name">{p.title}</span></td>
                                    <td>
                                        <span className={`status-badge ${p.is_published ? 'published' : 'draft'}`}>
                                            {p.is_published ? 'Published' : 'Draft'}
                                        </span>
                                    </td>
                                    <td className="muted">{p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</td>
                                    <td>
                                        <div className="action-btns">
                                            <button className="icon-btn edit" title="Edit" onClick={() => navigate(`/admin/problems/${p.id}`)} id={`edit-problem-${p.id}`}>
                                                <Pencil size={14} />
                                            </button>
                                            <button className="icon-btn pub" title={p.is_published ? 'Unpublish' : 'Publish'} onClick={() => togglePublish(p)} id={`toggle-publish-${p.id}`}>
                                                {p.is_published ? <EyeOff size={14} /> : <Eye size={14} />}
                                            </button>
                                            <button className="icon-btn del" title="Delete" onClick={() => handleDelete(p.id)} id={`delete-problem-${p.id}`}>
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {problems.length === 0 && (
                                <tr><td colSpan={5} className="empty-row">No problems yet. Create one above.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            <style>{`
        .admin-problems { max-width: 1000px; }
        .ap-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2rem; gap: 1rem; flex-wrap: wrap; }
        .ap-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }
        .ap-subtitle { color: var(--text-secondary); }

        .toast {
          position: fixed; top: 1.5rem; right: 1.5rem; z-index: 9999;
          display: flex; align-items: center; gap: 0.5rem;
          padding: 0.75rem 1.25rem; border-radius: 0.75rem;
          font-weight: 500; font-size: 0.9rem;
          animation: fadeIn 0.3s ease;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }
        .toast-ok { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.4); color: var(--success); }
        .toast-err { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.4); color: var(--error); }

        .create-form {
          padding: 1.5rem; margin-bottom: 2rem;
          display: flex; flex-direction: column; gap: 1rem;
        }
        .create-form h3 { font-size: 1.1rem; margin-bottom: 0.25rem; }
        .form-row { display: flex; flex-direction: column; gap: 0.4rem; }
        .form-row label { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
        .form-row input, .form-row textarea {
          background: rgba(15,23,42,0.6); border: 1px solid var(--border-color);
          border-radius: 0.5rem; color: var(--text-primary); padding: 0.6rem 0.875rem;
          font-family: inherit; font-size: 0.9rem; transition: border-color 0.2s; resize: vertical;
        }
        .form-row input:focus, .form-row textarea:focus { outline: none; border-color: var(--accent-primary); }
        .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .form-actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 0.5rem; }

        .loading-center {
          display: flex; align-items: center; justify-content: center;
          gap: 0.75rem; padding: 4rem; color: var(--text-secondary);
        }
        .error-banner {
          display: flex; align-items: center; gap: 0.5rem;
          padding: 1rem 1.5rem; background: var(--error-bg); color: var(--error);
          border: 1px solid rgba(239,68,68,0.3); border-radius: 0.75rem;
        }

        .overflow-card { overflow-x: auto; }
        .admin-table { width: 100%; border-collapse: collapse; text-align: left; }
        .admin-table th { padding: 1rem 1.25rem; background: rgba(0,0,0,0.2); color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border-color); }
        .admin-table td { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-color); font-size: 0.9rem; }
        .admin-table tbody tr:hover { background: rgba(255,255,255,0.02); }
        .admin-table tr:last-child td { border-bottom: none; }

        .muted { color: var(--text-secondary); font-size: 0.85rem; }
        .problem-name { font-weight: 500; }
        .empty-row { text-align: center; color: var(--text-muted); padding: 3rem 1rem; }

        .status-badge { padding: 0.2rem 0.65rem; border-radius: 1rem; font-size: 0.75rem; font-weight: 600; }
        .status-badge.published { background: var(--success-bg); color: var(--success); }
        .status-badge.draft { background: rgba(100,116,139,0.15); color: var(--text-secondary); }

        .action-btns { display: flex; gap: 0.4rem; }
        .icon-btn { width: 30px; height: 30px; border-radius: 0.4rem; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; background: transparent; }
        .icon-btn.edit { color: var(--accent-primary); border-color: rgba(59,130,246,0.2); }
        .icon-btn.edit:hover { background: rgba(59,130,246,0.1); }
        .icon-btn.pub { color: var(--text-secondary); border-color: var(--border-color); }
        .icon-btn.pub:hover { background: rgba(255,255,255,0.05); color: var(--text-primary); }
        .icon-btn.del { color: var(--error); border-color: rgba(239,68,68,0.2); }
        .icon-btn.del:hover { background: rgba(239,68,68,0.1); }

        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
        </div>
    );
};

export default AdminProblemsPage;
