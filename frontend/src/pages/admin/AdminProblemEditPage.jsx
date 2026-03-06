import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, Play, Loader, Save, AlertCircle, CheckCircle, FlaskConical } from 'lucide-react';
import api from '../../api';

const VERDICTS = {
    AC: { label: 'Accepted', color: 'var(--success)' },
    WA: { label: 'Wrong Answer', color: 'var(--error)' },
    TLE: { label: 'Time Limit Exceeded', color: 'var(--warning)' },
    CE: { label: 'Compile Error', color: 'var(--warning)' },
    RE: { label: 'Runtime Error', color: 'var(--error)' },
    SYSTEM_ERROR: { label: 'System Error', color: 'var(--text-muted)' },
    pending: { label: 'Running…', color: 'var(--accent-primary)' },
};

const AdminProblemEditPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();

    const [meta, setMeta] = useState({ title: '', time_limit_ms: 2000, memory_limit_mb: 256 });
    const [statement, setStatement] = useState('');
    const [testCases, setTestCases] = useState([]);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [toast, setToast] = useState(null);

    // New test case form
    const [newTc, setNewTc] = useState({ input_data: '', expected_output: '', is_sample: false, score: 10 });

    // Dry-run state per test-case row
    const [runState, setRunState] = useState({}); // tc_id -> { lang, src_code, runId, verdict }

    const showToast = (msg, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 3500);
    };

    useEffect(() => {
        const init = async () => {
            try {
                const [probR, tcR] = await Promise.all([
                    api.get(`/problems/${id}`),
                    api.get(`/admin/problems/${id}/testcases`),
                ]);
                const prob = probR.data;
                setMeta({ title: prob.title, time_limit_ms: prob.timeLimit || 2000, memory_limit_mb: prob.memoryLimit || 256 });
                setStatement(prob.statement || '');
                setTestCases(tcR.data);
            } catch {
                showToast('Failed to load problem', false);
            } finally {
                setLoading(false);
            }
        };
        init();
    }, [id]);

    const saveMeta = async () => {
        setSaving(true);
        try {
            await api.patch(`/admin/problems/${id}`, { ...meta, statement });
            showToast('Saved!');
        } catch {
            showToast('Save failed', false);
        } finally {
            setSaving(false);
        }
    };

    const addTestCase = async (e) => {
        e.preventDefault();
        try {
            await api.post(`/admin/problems/${id}/testcases`, newTc);
            showToast('Test case added');
            setNewTc({ input_data: '', expected_output: '', is_sample: false, score: 10 });
            const r = await api.get(`/admin/problems/${id}/testcases`);
            setTestCases(r.data);
        } catch {
            showToast('Failed to add test case', false);
        }
    };

    const deleteTestCase = async (tcId) => {
        if (!window.confirm('Delete test case?')) return;
        try {
            await api.delete(`/admin/problems/${id}/testcases/${tcId}`);
            showToast('Deleted');
            setTestCases(prev => prev.filter(t => t.id !== tcId));
        } catch {
            showToast('Delete failed', false);
        }
    };

    const runTestCase = async (tc) => {
        const state = runState[tc.id] || {};
        if (!state.src_code) {
            showToast('Enter source code for this test case first', false);
            return;
        }
        setRunState(prev => ({ ...prev, [tc.id]: { ...prev[tc.id], verdict: 'pending', runId: null } }));
        try {
            const r = await api.post(`/admin/problems/${id}/testcases/${tc.id}/run`, {
                language: state.lang || 'py',
                src_code: state.src_code,
            });
            const runId = r.data.run_id;
            setRunState(prev => ({ ...prev, [tc.id]: { ...prev[tc.id], runId } }));
            // Poll for result
            let attempts = 0;
            const poll = setInterval(async () => {
                attempts++;
                try {
                    const res = await api.get(`/admin/run-result/${runId}`);
                    if (res.data.status !== 'pending') {
                        clearInterval(poll);
                        setRunState(prev => ({
                            ...prev,
                            [tc.id]: { ...prev[tc.id], verdict: res.data.verdict || res.data.worker_status, std_out: res.data.std_out }
                        }));
                    }
                } catch {
                    clearInterval(poll);
                    setRunState(prev => ({ ...prev, [tc.id]: { ...prev[tc.id], verdict: 'SYSTEM_ERROR' } }));
                }
                if (attempts > 20) { clearInterval(poll); setRunState(prev => ({ ...prev, [tc.id]: { ...prev[tc.id], verdict: 'TLE' } })); }
            }, 1500);
        } catch (e) {
            setRunState(prev => ({ ...prev, [tc.id]: { ...prev[tc.id], verdict: 'SYSTEM_ERROR' } }));
        }
    };

    if (loading) return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '4rem', color: 'var(--text-secondary)' }}>
            <Loader size={24} className="spin" /> Loading...
            <style>{`.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
    );

    return (
        <div className="edit-page animate-fade-in">
            {toast && (
                <div className={`toast ${toast.ok ? 'tok' : 'terr'}`}>
                    {toast.ok ? <CheckCircle size={15} /> : <AlertCircle size={15} />} {toast.msg}
                </div>
            )}

            <div className="edit-header">
                <button className="back-btn" onClick={() => navigate('/admin/problems')}>
                    <ArrowLeft size={16} /> Problems
                </button>
                <h1 className="edit-title">Edit: <span>{meta.title}</span></h1>
                <button className="btn btn-primary" onClick={saveMeta} disabled={saving} id="save-problem-btn">
                    {saving ? <Loader size={14} className="spin" /> : <Save size={14} />} Save Changes
                </button>
            </div>

            {/* Meta section */}
            <section className="glass-card edit-section">
                <h2 className="section-title">Details & Limits</h2>
                <div className="meta-grid">
                    <div className="form-row">
                        <label>Title</label>
                        <input value={meta.title} onChange={e => setMeta(m => ({ ...m, title: e.target.value }))} id="edit-title" />
                    </div>
                    <div className="form-row">
                        <label>Time Limit (ms)</label>
                        <input type="number" value={meta.time_limit_ms} onChange={e => setMeta(m => ({ ...m, time_limit_ms: +e.target.value }))} id="edit-time" />
                    </div>
                    <div className="form-row">
                        <label>Memory Limit (MB)</label>
                        <input type="number" value={meta.memory_limit_mb} onChange={e => setMeta(m => ({ ...m, memory_limit_mb: +e.target.value }))} id="edit-mem" />
                    </div>
                </div>
                <div className="form-row" style={{ marginTop: '1rem' }}>
                    <label>Statement (Markdown)</label>
                    <textarea rows={8} value={statement} onChange={e => setStatement(e.target.value)} id="edit-statement" />
                </div>
            </section>

            {/* Test cases */}
            <section className="edit-section">
                <h2 className="section-title">Test Cases</h2>

                {/* Add test case form */}
                <form className="glass-card tc-form" onSubmit={addTestCase} id="add-testcase-form">
                    <h3>Add Test Case</h3>
                    <div className="tc-grid">
                        <div className="form-row">
                            <label>Input</label>
                            <textarea rows={4} value={newTc.input_data} onChange={e => setNewTc(t => ({ ...t, input_data: e.target.value }))} placeholder="3&#10;3 2 4&#10;6" id="tc-input" />
                        </div>
                        <div className="form-row">
                            <label>Expected Output</label>
                            <textarea rows={4} value={newTc.expected_output} onChange={e => setNewTc(t => ({ ...t, expected_output: e.target.value }))} placeholder="1 2" id="tc-expected" />
                        </div>
                    </div>
                    <div className="tc-meta-row">
                        <label className="checkbox-label">
                            <input type="checkbox" checked={newTc.is_sample} onChange={e => setNewTc(t => ({ ...t, is_sample: e.target.checked }))} id="tc-sample" />
                            Sample (visible to users)
                        </label>
                        <div className="form-row inline">
                            <label>Score</label>
                            <input type="number" value={newTc.score} onChange={e => setNewTc(t => ({ ...t, score: +e.target.value }))} style={{ width: '80px' }} id="tc-score" />
                        </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button type="submit" className="btn btn-primary" id="add-tc-btn"><Plus size={14} /> Add</button>
                    </div>
                </form>

                {/* Test cases list */}
                {testCases.length === 0 ? (
                    <p className="empty-msg">No test cases yet. Add one above.</p>
                ) : (
                    testCases.map((tc, idx) => {
                        const rs = runState[tc.id] || {};
                        const verdict = rs.verdict;
                        const verdictInfo = verdict ? VERDICTS[verdict] || VERDICTS.SYSTEM_ERROR : null;
                        return (
                            <div className="tc-card glass-card" key={tc.id} id={`tc-card-${tc.id}`}>
                                <div className="tc-card-header">
                                    <div className="tc-card-title">
                                        <span className="tc-num">#{idx + 1}</span>
                                        {tc.is_sample && <span className="sample-badge">Sample</span>}
                                        <span className="tc-score">{tc.score}pts</span>
                                    </div>
                                    <div className="tc-header-actions">
                                        {verdictInfo && (
                                            <span className="verdict-badge" style={{ color: verdictInfo.color, borderColor: verdictInfo.color }}>
                                                {verdict === 'pending' && <Loader size={12} className="spin" />}
                                                {verdictInfo.label}
                                            </span>
                                        )}
                                        <button className="icon-btn del" onClick={() => deleteTestCase(tc.id)} title="Delete" id={`del-tc-${tc.id}`}>
                                            <Trash2 size={13} />
                                        </button>
                                    </div>
                                </div>

                                <div className="tc-io">
                                    <div className="io-block">
                                        <span className="io-label">Input</span>
                                        <pre className="io-pre">{tc.input_data || '(empty)'}</pre>
                                    </div>
                                    <div className="io-block">
                                        <span className="io-label">Expected Output</span>
                                        <pre className="io-pre">{tc.expected_output || '(empty)'}</pre>
                                    </div>
                                </div>

                                {/* Dry-run panel */}
                                <div className="dry-run-panel">
                                    <FlaskConical size={14} style={{ color: 'var(--accent-primary)' }} />
                                    <span className="dry-run-label">Dry Run</span>
                                    <select
                                        value={rs.lang || 'py'}
                                        onChange={e => setRunState(p => ({ ...p, [tc.id]: { ...p[tc.id], lang: e.target.value } }))}
                                        className="lang-select"
                                        id={`lang-select-${tc.id}`}
                                    >
                                        <option value="py">Python</option>
                                        <option value="cpp">C++</option>
                                    </select>
                                    <textarea
                                        placeholder="Paste solution code here…"
                                        value={rs.src_code || ''}
                                        onChange={e => setRunState(p => ({ ...p, [tc.id]: { ...p[tc.id], src_code: e.target.value } }))}
                                        rows={3}
                                        className="run-code-input"
                                        id={`run-code-${tc.id}`}
                                    />
                                    <button
                                        className="btn run-btn"
                                        onClick={() => runTestCase(tc)}
                                        disabled={verdict === 'pending'}
                                        id={`run-tc-${tc.id}`}
                                    >
                                        {verdict === 'pending' ? <Loader size={13} className="spin" /> : <Play size={13} />}
                                        Run
                                    </button>
                                </div>

                                {rs.std_out !== undefined && (
                                    <div className="actual-output">
                                        <span className="io-label">Actual Output</span>
                                        <pre className="io-pre">{rs.std_out || '(empty)'}</pre>
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}
            </section>

            <style>{`
        .edit-page { max-width: 960px; }
        .edit-header { display: flex; align-items: center; gap: 1.5rem; margin-bottom: 2rem; flex-wrap: wrap; }
        .back-btn { display: flex; align-items: center; gap: 0.4rem; background: transparent; color: var(--text-secondary); font-family: inherit; font-size: 0.875rem; cursor: pointer; padding: 0.4rem 0.75rem; border: 1px solid var(--border-color); border-radius: 0.5rem; transition: all 0.15s; }
        .back-btn:hover { color: var(--text-primary); border-color: var(--text-secondary); }
        .edit-title { flex: 1; font-size: 1.5rem; font-weight: 700; }
        .edit-title span { color: var(--accent-primary); }

        .edit-section { margin-bottom: 2rem; }
        .edit-section.glass-card { padding: 1.5rem; }
        .section-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 1.25rem; color: var(--text-primary); }

        .meta-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 1rem; }
        .form-row { display: flex; flex-direction: column; gap: 0.35rem; }
        .form-row label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); font-weight: 600; }
        .form-row.inline { flex-direction: row; align-items: center; gap: 0.5rem; }
        .form-row input, .form-row textarea, .tc-form input, .tc-form textarea {
          background: rgba(15,23,42,0.6); border: 1px solid var(--border-color);
          border-radius: 0.5rem; color: var(--text-primary); padding: 0.55rem 0.8rem;
          font-family: var(--font-mono); font-size: 0.875rem; transition: border-color 0.2s; resize: vertical;
        }
        .form-row input:focus, .form-row textarea:focus { outline: none; border-color: var(--accent-primary); }

        .tc-form { padding: 1.25rem; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 0.85rem; }
        .tc-form h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-secondary); }
        .tc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .tc-meta-row { display: flex; align-items: center; gap: 1.5rem; }
        .checkbox-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-secondary); cursor: pointer; }
        .checkbox-label input { accent-color: var(--accent-primary); width: 15px; height: 15px; }

        .empty-msg { color: var(--text-muted); text-align: center; padding: 2rem; font-size: 0.9rem; }

        .tc-card { padding: 1.25rem; margin-bottom: 0.85rem; display: flex; flex-direction: column; gap: 0.85rem; }
        .tc-card-header { display: flex; align-items: center; justify-content: space-between; }
        .tc-card-title { display: flex; align-items: center; gap: 0.6rem; }
        .tc-num { font-weight: 700; color: var(--text-secondary); font-size: 0.85rem; }
        .sample-badge { padding: 0.15rem 0.5rem; background: rgba(59,130,246,0.1); color: var(--accent-primary); border-radius: 1rem; font-size: 0.7rem; font-weight: 700; }
        .tc-score { padding: 0.15rem 0.5rem; background: rgba(245,158,11,0.1); color: var(--warning); border-radius: 1rem; font-size: 0.7rem; font-weight: 700; }
        .tc-header-actions { display: flex; align-items: center; gap: 0.5rem; }
        .verdict-badge { padding: 0.2rem 0.65rem; border: 1px solid; border-radius: 1rem; font-size: 0.75rem; font-weight: 700; display: flex; align-items: center; gap: 0.35rem; }

        .tc-io { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .io-block { display: flex; flex-direction: column; gap: 0.35rem; }
        .io-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); font-weight: 700; }
        .io-pre { background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 0.6rem 0.8rem; font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; margin: 0; max-height: 120px; overflow-y: auto; }

        .dry-run-panel { display: flex; flex-direction: column; gap: 0.5rem; padding: 0.85rem; background: rgba(59,130,246,0.04); border: 1px solid rgba(59,130,246,0.15); border-radius: 0.6rem; }
        .dry-run-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent-primary); }
        .lang-select { background: rgba(15,23,42,0.7); border: 1px solid var(--border-color); border-radius: 0.4rem; color: var(--text-primary); padding: 0.3rem 0.5rem; font-family: inherit; font-size: 0.8rem; width: fit-content; }
        .run-code-input { background: rgba(15,23,42,0.6); border: 1px solid var(--border-color); border-radius: 0.4rem; color: var(--text-primary); padding: 0.5rem; font-family: var(--font-mono); font-size: 0.8rem; resize: vertical; }
        .run-code-input:focus { outline: none; border-color: var(--accent-primary); }
        .run-btn { background: rgba(59,130,246,0.12); color: var(--accent-primary); border: 1px solid rgba(59,130,246,0.25); padding: 0.4rem 0.85rem; border-radius: 0.4rem; font-size: 0.8rem; gap: 0.4rem; align-self: flex-start; transition: all 0.15s; }
        .run-btn:hover { background: rgba(59,130,246,0.2); }
        .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .actual-output { display: flex; flex-direction: column; gap: 0.35rem; }

        .toast { position: fixed; top: 1.5rem; right: 1.5rem; z-index: 9999; display: flex; align-items: center; gap: 0.5rem; padding: 0.7rem 1.15rem; border-radius: 0.65rem; font-size: 0.88rem; font-weight: 500; animation: fadeIn 0.2s ease; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
        .tok { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.35); color: var(--success); }
        .terr { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: var(--error); }

        .icon-btn { width: 28px; height: 28px; border-radius: 0.35rem; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; background: transparent; }
        .icon-btn.del { color: var(--error); border-color: rgba(239,68,68,0.2); }
        .icon-btn.del:hover { background: rgba(239,68,68,0.1); }

        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        @media (max-width: 640px) {
          .meta-grid { grid-template-columns: 1fr; }
          .tc-grid { grid-template-columns: 1fr; }
          .tc-io { grid-template-columns: 1fr; }
        }
      `}</style>
        </div>
    );
};

export default AdminProblemEditPage;
