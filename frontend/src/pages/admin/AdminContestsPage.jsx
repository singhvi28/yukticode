import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Eye, EyeOff, ChevronRight, Loader, AlertCircle, CheckCircle, Trophy, X } from 'lucide-react';
import api from '../../api';

const AdminContestsPage = () => {
    const [contests, setContests] = useState([]);
    const [allProblems, setAllProblems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [toast, setToast] = useState(null);
    const [showForm, setShowForm] = useState(false);
    const [editId, setEditId] = useState(null); // expanded contest id
    const [form, setForm] = useState({ title: '', description: '', start_time: '', end_time: '' });
    const [saving, setSaving] = useState(false);
    const [addProblemMap, setAddProblemMap] = useState({}); // contest_id -> { problem_id, score, display_order }
    const navigate = useNavigate();

    const showToast = (msg, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3000); };

    const fetchAll = async () => {
        try {
            setLoading(true);
            const [cr, pr] = await Promise.all([
                api.get('/admin/contests'),
                api.get('/admin/problems'),
            ]);
            setContests(cr.data);
            setAllProblems(pr.data);
        } catch { showToast('Failed to load', false); }
        finally { setLoading(false); }
    };

    useEffect(() => { fetchAll(); }, []);

    const handleCreate = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const payload = {
                title: form.title,
                description: form.description,
                start_time: form.start_time ? new Date(form.start_time).toISOString() : null,
                end_time: form.end_time ? new Date(form.end_time).toISOString() : null,
            };
            await api.post('/admin/contests', payload);
            showToast('Contest created!');
            setShowForm(false);
            setForm({ title: '', description: '', start_time: '', end_time: '' });
            fetchAll();
        } catch (e) {
            showToast(e.response?.data?.detail || 'Failed', false);
        } finally { setSaving(false); }
    };

    const togglePublish = async (c) => {
        try {
            await api.patch(`/admin/contests/${c.id}`, { is_published: !c.is_published });
            showToast(c.is_published ? 'Unpublished' : 'Published!');
            fetchAll();
        } catch { showToast('Failed', false); }
    };

    const deleteContest = async (id) => {
        if (!window.confirm('Delete this contest?')) return;
        try {
            await api.delete(`/admin/contests/${id}`);
            showToast('Deleted');
            fetchAll();
        } catch { showToast('Delete failed', false); }
    };

    const expandContest = async (id) => {
        if (editId === id) { setEditId(null); return; }
        setEditId(id);
        // Fetch fresh detail — already in list so this just refreshes
    };

    const addProblemToContest = async (contestId) => {
        const opts = addProblemMap[contestId] || { problem_id: '', score: 100, display_order: 0 };
        if (!opts.problem_id) { showToast('Select a problem first', false); return; }
        try {
            await api.post(`/admin/contests/${contestId}/problems`, { problem_id: +opts.problem_id, score: +opts.score, display_order: +opts.display_order });
            showToast('Problem added to contest');
            fetchAll();
        } catch (e) { showToast(e.response?.data?.detail || 'Failed', false); }
    };

    const removeProblemFromContest = async (contestId, problemId) => {
        try {
            await api.delete(`/admin/contests/${contestId}/problems/${problemId}`);
            showToast('Removed');
            fetchAll();
        } catch { showToast('Failed', false); }
    };

    const fmt = (dt) => dt ? new Date(dt).toLocaleString() : '—';
    const getStatus = (c) => {
        if (!c.is_published) return { label: 'Draft', cls: 'draft' };
        const now = new Date();
        if (c.start_time && new Date(c.start_time) > now) return { label: 'Upcoming', cls: 'upcoming' };
        if (c.end_time && new Date(c.end_time) < now) return { label: 'Ended', cls: 'ended' };
        return { label: 'Live', cls: 'live' };
    };

    return (
        <div className="contests-page animate-fade-in">
            {toast && (
                <div className={`toast ${toast.ok ? 'tok' : 'terr'}`}>
                    {toast.ok ? <CheckCircle size={15} /> : <AlertCircle size={15} />} {toast.msg}
                </div>
            )}

            <div className="cp-header">
                <div>
                    <h1 className="cp-title">Contests</h1>
                    <p className="cp-sub">Schedule and manage competitive contests</p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowForm(v => !v)} id="new-contest-btn">
                    <Plus size={15} /> New Contest
                </button>
            </div>

            {showForm && (
                <form className="glass-card create-form" onSubmit={handleCreate} id="create-contest-form">
                    <h3>New Contest</h3>
                    <div className="form-grid-2">
                        <div className="form-row full">
                            <label>Title</label>
                            <input required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Codeforces Round #500" id="contest-title" />
                        </div>
                        <div className="form-row full">
                            <label>Description</label>
                            <textarea rows={3} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Brief contest description..." id="contest-description" />
                        </div>
                        <div className="form-row">
                            <label>Start Time</label>
                            <input type="datetime-local" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} id="contest-start" />
                        </div>
                        <div className="form-row">
                            <label>End Time</label>
                            <input type="datetime-local" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} id="contest-end" />
                        </div>
                    </div>
                    <div className="form-actions">
                        <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={saving} id="create-contest-submit">
                            {saving ? <Loader size={13} className="spin" /> : <Plus size={13} />} Create
                        </button>
                    </div>
                </form>
            )}

            {loading ? (
                <div className="loading-c"><Loader size={26} className="spin" /> Loading...</div>
            ) : contests.length === 0 ? (
                <div className="glass-card empty-state-card">
                    <Trophy size={48} style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }} />
                    <p>No contests yet. Create one above!</p>
                </div>
            ) : (
                <div className="contest-list">
                    {contests.map(c => {
                        const { label, cls } = getStatus(c);
                        const isExpanded = editId === c.id;
                        const pMap = addProblemMap[c.id] || {};
                        return (
                            <div className="glass-card contest-card" key={c.id} id={`contest-card-${c.id}`}>
                                <div className="contest-row">
                                    <div className="contest-info">
                                        <div className="contest-meta">
                                            <span className={`status-badge ${cls}`}>{label}</span>
                                            <h3 className="contest-title">{c.title}</h3>
                                        </div>
                                        {c.description && <p className="contest-desc">{c.description}</p>}
                                        <div className="contest-times">
                                            <span>🕐 {fmt(c.start_time)}</span>
                                            <span>→</span>
                                            <span>🕑 {fmt(c.end_time)}</span>
                                        </div>
                                    </div>
                                    <div className="contest-actions">
                                        <button className="icon-btn pub" title={c.is_published ? 'Unpublish' : 'Publish'} onClick={() => togglePublish(c)} id={`toggle-publish-${c.id}`}>
                                            {c.is_published ? <EyeOff size={14} /> : <Eye size={14} />}
                                        </button>
                                        <button className="icon-btn del" onClick={() => deleteContest(c.id)} id={`del-contest-${c.id}`}><Trash2 size={14} /></button>
                                        <button className={`icon-btn expand ${isExpanded ? 'active' : ''}`} onClick={() => expandContest(c.id)} id={`expand-contest-${c.id}`}>
                                            <ChevronRight size={15} style={{ transform: isExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                                        </button>
                                    </div>
                                </div>

                                {isExpanded && (
                                    <div className="contest-detail">
                                        <div className="detail-divider" />
                                        <h4 className="detail-title">Problems in this contest</h4>

                                        {/* Current problems */}
                                        <div className="problems-in-contest">
                                            {(c.contest_problems || []).length === 0 && (
                                                <p className="empty-msg">No problems assigned yet.</p>
                                            )}
                                        </div>

                                        {/* Add problem form */}
                                        <div className="add-prob-row">
                                            <select
                                                value={pMap.problem_id || ''}
                                                onChange={e => setAddProblemMap(m => ({ ...m, [c.id]: { ...m[c.id], problem_id: e.target.value } }))}
                                                className="prob-select"
                                                id={`prob-select-${c.id}`}
                                            >
                                                <option value="">— Select problem —</option>
                                                {allProblems.map(p => (
                                                    <option key={p.id} value={p.id}>{p.title}</option>
                                                ))}
                                            </select>
                                            <input
                                                type="number"
                                                placeholder="Score"
                                                value={pMap.score ?? 100}
                                                onChange={e => setAddProblemMap(m => ({ ...m, [c.id]: { ...m[c.id], score: e.target.value } }))}
                                                className="score-input"
                                                id={`score-input-${c.id}`}
                                            />
                                            <input
                                                type="number"
                                                placeholder="Order"
                                                value={pMap.display_order ?? 0}
                                                onChange={e => setAddProblemMap(m => ({ ...m, [c.id]: { ...m[c.id], display_order: e.target.value } }))}
                                                className="order-input"
                                                id={`order-input-${c.id}`}
                                            />
                                            <button className="btn btn-primary" style={{ fontSize: '0.8rem', padding: '0.45rem 0.9rem' }} onClick={() => addProblemToContest(c.id)} id={`add-prob-${c.id}`}>
                                                <Plus size={13} /> Add
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            <style>{`
        .contests-page { max-width: 900px; }
        .cp-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2rem; gap: 1rem; flex-wrap: wrap; }
        .cp-title { font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem; }
        .cp-sub { color: var(--text-secondary); }

        .toast { position: fixed; top: 1.5rem; right: 1.5rem; z-index: 9999; display: flex; align-items: center; gap: 0.45rem; padding: 0.7rem 1.1rem; border-radius: 0.65rem; font-size: 0.875rem; font-weight: 500; box-shadow: 0 8px 24px rgba(0,0,0,0.4); animation: fadeIn 0.2s ease; }
        .tok { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: var(--success); }
        .terr { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: var(--error); }

        .create-form { padding: 1.5rem; margin-bottom: 2rem; display: flex; flex-direction: column; gap:0.85rem; }
        .create-form h3 { font-size: 1rem; font-weight: 600; color: var(--text-secondary); }
        .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem; }
        .form-row { display: flex; flex-direction: column; gap: 0.35rem; }
        .form-row.full { grid-column: 1 / -1; }
        .form-row label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); font-weight: 600; }
        .form-row input, .form-row textarea { background: rgba(15,23,42,0.6); border: 1px solid var(--border-color); border-radius: 0.5rem; color: var(--text-primary); padding: 0.55rem 0.8rem; font-family: inherit; font-size: 0.875rem; transition: border-color 0.2s; resize: vertical; }
        .form-row input:focus, .form-row textarea:focus { outline: none; border-color: var(--accent-primary); }
        .form-actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 0.25rem; }

        .loading-c { display: flex; align-items: center; gap: 0.75rem; padding: 4rem; color: var(--text-secondary); }
        .empty-state-card { padding: 4rem; text-align: center; color: var(--text-secondary); display: flex; flex-direction: column; align-items: center; }

        .contest-list { display: flex; flex-direction: column; gap: 1rem; }
        .contest-card { padding: 1.25rem; }
        .contest-row { display: flex; align-items: flex-start; gap: 1rem; }
        .contest-info { flex: 1; display: flex; flex-direction: column; gap: 0.4rem; }
        .contest-meta { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
        .contest-title { font-size: 1.05rem; font-weight: 700; }
        .contest-desc { font-size: 0.875rem; color: var(--text-secondary); }
        .contest-times { display: flex; gap: 0.5rem; font-size: 0.78rem; color: var(--text-muted); flex-wrap: wrap; }
        .contest-actions { display: flex; gap: 0.35rem; flex-shrink: 0; }

        .status-badge { padding: 0.2rem 0.6rem; border-radius: 1rem; font-size: 0.72rem; font-weight: 700; }
        .status-badge.draft { background: rgba(100,116,139,0.15); color: var(--text-secondary); }
        .status-badge.upcoming { background: rgba(59,130,246,0.12); color: var(--accent-primary); }
        .status-badge.live { background: var(--success-bg); color: var(--success); }
        .status-badge.ended { background: rgba(100,116,139,0.15); color: var(--text-muted); }

        .icon-btn { width: 30px; height: 30px; border-radius: 0.4rem; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; background: transparent; }
        .icon-btn.pub { color: var(--text-secondary); border-color: var(--border-color); }
        .icon-btn.pub:hover { background: rgba(255,255,255,0.05); color: var(--text-primary); }
        .icon-btn.del { color: var(--error); border-color: rgba(239,68,68,0.2); }
        .icon-btn.del:hover { background: rgba(239,68,68,0.1); }
        .icon-btn.expand { color: var(--text-secondary); border-color: var(--border-color); }
        .icon-btn.expand:hover, .icon-btn.expand.active { background: rgba(59,130,246,0.08); color: var(--accent-primary); border-color: rgba(59,130,246,0.2); }

        .contest-detail { display: flex; flex-direction: column; gap: 0.85rem; }
        .detail-divider { border: none; border-top: 1px solid var(--border-color); margin: 0; }
        .detail-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
        .empty-msg { color: var(--text-muted); font-size: 0.85rem; }

        .add-prob-row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
        .prob-select { background: rgba(15,23,42,0.7); border: 1px solid var(--border-color); border-radius: 0.45rem; color: var(--text-primary); padding: 0.4rem 0.6rem; font-family: inherit; font-size: 0.85rem; flex: 1; min-width: 160px; }
        .score-input, .order-input { background: rgba(15,23,42,0.7); border: 1px solid var(--border-color); border-radius: 0.45rem; color: var(--text-primary); padding: 0.4rem 0.6rem; font-family: inherit; font-size: 0.85rem; width: 72px; }
        .prob-select:focus, .score-input:focus, .order-input:focus { outline: none; border-color: var(--accent-primary); }

        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
        </div>
    );
};

export default AdminContestsPage;
