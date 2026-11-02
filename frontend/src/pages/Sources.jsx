import { useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { useApp } from '../App';
import { api } from '../api';
import { Clearance, Drawer, Empty, Loading, Modal, Spinner, Tabs, useAsync, useToast } from '../components/ui';
import { KIND_LABEL, SENS, fmtDate } from '../format';

function AddSource({ pid, onClose, onAdded }) {
  const toast = useToast();
  const [mode, setMode] = useState('file');
  const [file, setFile] = useState(null);
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [repo, setRepo] = useState('');
  const [sens, setSens] = useState(0);
  const [date, setDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  async function submit() {
    setBusy(true);
    setError('');
    try {
      let r;
      if (mode === 'file') {
        const f = new FormData();
        f.append('file', file);
        f.append('sensitivity', sens);
        if (date) f.append('doc_date', date);
        r = await api.upload(`/projects/${pid}/sources/upload`, f);
      } else if (mode === 'note') {
        r = await api.post(`/projects/${pid}/sources/note`, { name, text, sensitivity: sens, doc_date: date || null });
      } else {
        r = await api.post(`/projects/${pid}/sources/github`, { repo, sensitivity: sens });
      }
      setResult(r);
      onAdded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const items = result ? (result.added || [result]) : [];
  const can = mode === 'file' ? !!file : mode === 'note' ? name.trim() && text.trim() : repo.trim();

  return (
    <Modal title="Add a source" subtitle="Only add material you are authorised to share." onClose={onClose} wide
      footer={result ? <button className="btn primary" onClick={onClose}>Done</button> : (
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!can || busy} onClick={submit}>{busy ? <Spinner /> : 'Add and scan'}</button>
        </>
      )}>
      {result ? (
        <div className="stack">
          {items.map((i) => (
            <div key={i.id} className="panel panel-body">
              <b>{i.name}</b>
              <div className="small muted" style={{ marginTop: 4 }}>Detected as {KIND_LABEL[i.kind] || i.kind}. Split into {i.chunks} passages.</div>
              <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {Object.keys(i.redactions).length ? Object.entries(i.redactions).map(([k, n]) => <span key={k} className="chip red">{n} {k.replace('_', ' ')} masked</span>) : <span className="chip">No secrets found</span>}
                {i.flagged_chunks ? <span className="chip conf">{i.flagged_chunks} passages flagged as sensitive</span> : null}
              </div>
            </div>
          ))}
          <div className="notice info">Run reconstruction to extract claims from the new source.</div>
        </div>
      ) : (
        <>
          <Tabs value={mode} onChange={setMode} tabs={[{ key: 'file', label: 'Upload file' }, { key: 'note', label: 'Paste a note' }, { key: 'github', label: 'GitHub repository' }]} />
          {mode === 'file' && (
            <div className="field">
              <label htmlFor="f">File</label>
              <input id="f" type="file" accept=".txt,.md,.csv,.tsv,.json,.log,text/*" onChange={(e) => setFile(e.target.files[0])} />
              <span className="hint">Text, Markdown, CSV task exports, JSON and WhatsApp-style chat exports. Detected automatically.</span>
            </div>
          )}
          {mode === 'note' && (
            <>
              <div className="field"><label htmlFor="n">Title</label><input id="n" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Handover call, 31 Oct" /></div>
              <div className="field"><label htmlFor="t">Text</label><textarea id="t" value={text} onChange={(e) => setText(e.target.value)} rows={7} /></div>
            </>
          )}
          {mode === 'github' && (
            <div className="field">
              <label htmlFor="r">Public repository</label>
              <input id="r" type="text" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/name or https://github.com/owner/name" />
              <span className="hint">Imports the README and recent issues and pull requests. Private repositories need OAuth, planned for Round 3.</span>
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="field">
              <label htmlFor="s">Sensitivity</label>
              <select id="s" value={sens} onChange={(e) => setSens(Number(e.target.value))}>
                <option value={0}>General: anyone receiving a handover</option>
                <option value={1}>Internal: peers, not restricted volunteers</option>
                <option value={2}>Confidential: approvers only</option>
              </select>
              <span className="hint">Passages with secrets or confidential language are raised automatically.</span>
            </div>
            {mode !== 'github' && (
              <div className="field"><label htmlFor="d">Document date (optional)</label><input id="d" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
            )}
          </div>
          {error && <div className="notice error">{error}</div>}
        </>
      )}
    </Modal>
  );
}

function SourceDrawer({ id, onClose, onChanged }) {
  const { reviewer, user } = useApp();
  const toast = useToast();
  const [s, reload] = useAsync(() => api.get(`/sources/${id}`), [id]);
  async function setSens(v) {
    try { await api.patch(`/sources/${id}`, { sensitivity: Number(v) }); toast('Sensitivity updated. Run reconstruction to refresh claims.'); reload(); onChanged(); } catch (e) { toast(e.message, 'error'); }
  }
  async function del() {
    if (!window.confirm('Delete this source and the claims that depend only on it?')) return;
    try { await api.del(`/sources/${id}`); toast('Source deleted'); onClose(); onChanged(); } catch (e) { toast(e.message, 'error'); }
  }
  return (
    <Drawer title={s.data ? s.data.source.name : 'Source'} eyebrow="Source record" onClose={onClose}>
      {s.loading ? <Loading /> : (
        <>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            <span className="chip">{KIND_LABEL[s.data.source.kind]}</span>
            <Clearance level={s.data.source.sensitivity} />
            {s.data.source.doc_date && <span className="chip">{fmtDate(s.data.source.doc_date)}</span>}
            {Object.entries(s.data.source.redactions).map(([k, n]) => <span key={k} className="chip red">{n} {k.replace('_', ' ')} masked</span>)}
          </div>
          {reviewer && (
            <div className="field" style={{ marginTop: 12 }}>
              <label htmlFor="sv">Base sensitivity</label>
              <select id="sv" value={s.data.source.sensitivity} onChange={(e) => setSens(e.target.value)}>
                {SENS.map((x, i) => <option key={x} value={i}>{x}</option>)}
              </select>
            </div>
          )}
          <h3>Passages ({s.data.chunks.length})</h3>
          <div className="ctx">
            {s.data.chunks.map((c) => (
              c.restricted ? <div key={c.idx} className="ctx-line restricted">Hidden: above your access level.</div> : (
                <div key={c.idx} className="ctx-line">
                  <span className="at">{c.location}{c.speaker ? ` · ${c.speaker}` : ''}{c.sens ? ` · ${SENS[c.sens]}` : ''}</span>{c.text}
                </div>
              )
            ))}
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>Secrets are masked before storage, so the original values cannot be recovered from this system.</p>
          {user.role === 'admin' && <button className="btn danger sm" style={{ marginTop: 16 }} onClick={del}>Delete source</button>}
        </>
      )}
    </Drawer>
  );
}

export default function Sources() {
  const { project } = useApp();
  const toast = useToast();
  const [s, reload] = useAsync(() => api.get(`/projects/${project.id}/sources`), [project.id]);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${project.id}/reconstruct`);
      toast(`Reconstructed: ${r.claims} claims, ${r.conflicts} conflicts${r.unsupported ? `, ${r.unsupported} unverified model outputs rejected` : ''}${r.llm_error ? `. Model error: ${r.llm_error}` : ''}`, r.llm_error ? 'error' : 'ok');
      reload();
    } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Sources</h1><p>Authorised project material. Secrets are masked on the way in and every passage keeps its own access level.</p></div>
        <div className="actions">
          <button className="btn" onClick={run} disabled={busy || !s.data?.length}>{busy ? <Spinner /> : <RefreshCw size={14} />} Run reconstruction</button>
          <button className="btn primary" onClick={() => setAdding(true)}><Plus size={14} /> Add source</button>
        </div>
      </div>
      <div className="panel">
        {s.loading ? <Loading /> : s.error ? <div className="notice error" style={{ margin: 16 }}>{s.error.message}</div> : s.data.length === 0 ? <Empty title="No sources yet">Add a file, a note or a public GitHub repository.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Type</th><th>Access level</th><th className="num">Passages</th><th className="num">Claims</th><th>Protection</th><th>Date</th><th>Added by</th></tr></thead>
              <tbody>
                {s.data.map((x) => {
                  const red = Object.values(x.redactions).reduce((a, b) => a + b, 0);
                  return (
                    <tr key={x.id} className="click" onClick={() => setOpen(x.id)}>
                      <td><b style={{ fontWeight: 550 }}>{x.name}</b></td>
                      <td>{KIND_LABEL[x.kind] || x.kind}</td>
                      <td>{SENS[x.sensitivity]}{x.raised_chunks ? <span className="chip conf" style={{ marginLeft: 6 }}>{x.raised_chunks} raised</span> : null}</td>
                      <td className="num">{x.chunks}</td>
                      <td className="num">{x.claims}</td>
                      <td>{red ? <span className="chip red">{red} masked</span> : <span className="muted">None needed</span>}</td>
                      <td className="muted">{fmtDate(x.doc_date)}</td>
                      <td className="muted">{x.uploaded_by_name}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>Passages flagged "raised" contain confidential language or secrets, so they are hidden from lower access levels even when the rest of the file is visible.</p>
      {adding && <AddSource pid={project.id} onClose={() => setAdding(false)} onAdded={reload} />}
      {open && <SourceDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}
