import { useMemo, useState } from 'react';
import { Check, Pencil, RefreshCw, X, MessageSquarePlus, RotateCcw } from 'lucide-react';
import { useApp, go } from '../App';
import { api } from '../api';
import { Badge, Clearance, Drawer, Empty, Loading, Modal, Spinner, Tabs, useAsync, useToast } from '../components/ui';
import { EvidenceBody } from '../components/Evidence';
import { TYPE_LABEL, TYPE_PLURAL, fmtDate } from '../format';

const TAB_TYPES = ['decision', 'action', 'risk', 'dependency', 'owner', 'state', 'contact'];

function EditModal({ claim, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ statement: claim.statement, owner: claim.owner || '', due: claim.due || '', severity: claim.severity || '' });
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api.patch(`/claims/${claim.id}`, { action: 'edit', statement: f.statement, owner: f.owner || null, due: f.due || null, severity: f.severity || null });
      toast('Claim corrected');
      onSaved();
      onClose();
    } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }
  return (
    <Modal title="Correct this claim" subtitle="Your edit is recorded and the claim becomes Verified. The original extraction stays visible." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || !f.statement.trim()} onClick={save}>{busy ? <Spinner /> : 'Save correction'}</button></>}>
      <div className="field"><label htmlFor="es">Statement</label><textarea id="es" rows={4} value={f.statement} onChange={(e) => setF({ ...f, statement: e.target.value })} /></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
        <div className="field"><label htmlFor="eo">Owner</label><input id="eo" type="text" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} /></div>
        <div className="field"><label htmlFor="ed">Due date</label><input id="ed" type="date" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} /></div>
        <div className="field"><label htmlFor="ev">Severity</label>
          <select id="ev" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}><option value="">None</option><option>High</option><option>Medium</option><option>Low</option></select></div>
      </div>
    </Modal>
  );
}

function AnswerBox({ claim, onSaved }) {
  const toast = useToast();
  const [text, setText] = useState(claim.answer || '');
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try { await api.post(`/claims/${claim.id}/answer`, { text }); toast('Answer recorded'); onSaved(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }
  return (
    <>
      <h3>{claim.answer ? 'Update the answer' : 'Close this gap'}</h3>
      <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write what you know. It will be attributed to you and labelled as having no document evidence." aria-label="Answer" />
      <div style={{ marginTop: 8 }}><button className="btn primary sm" disabled={busy || text.trim().length < 3} onClick={save}>{busy ? <Spinner /> : 'Save answer'}</button></div>
    </>
  );
}

function ClaimDrawer({ claim, onClose, reload, canReview, canAnswer, onEdit }) {
  const toast = useToast();
  async function act(action) {
    try { await api.patch(`/claims/${claim.id}`, { action }); reload(); onClose(); } catch (e) { toast(e.message, 'error'); }
  }
  return (
    <Drawer title={TYPE_LABEL[claim.type]} eyebrow={`Claim #${claim.id}`} onClose={onClose}>
      <EvidenceBody claim={claim} />
      {canAnswer && ['gap', 'question'].includes(claim.type) && <AnswerBox claim={claim} onSaved={() => { reload(); onClose(); }} />}
      {canReview && (
        <>
          <h3>Review</h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {claim.review_status !== 'unsupported' && claim.label !== 'verified' && <button className="btn primary sm" onClick={() => act('confirm')}><Check size={14} /> Confirm against source</button>}
            {claim.review_status !== 'unsupported' && <button className="btn sm" onClick={() => { onClose(); onEdit(claim); }}><Pencil size={14} /> Correct</button>}
            {claim.label !== 'rejected' ? <button className="btn sm danger" onClick={() => act('reject')}><X size={14} /> Reject</button> : <button className="btn sm" onClick={() => act('restore')}><RotateCcw size={14} /> Restore</button>}
          </div>
          {claim.reviewed_by_name && <p className="small muted" style={{ marginTop: 8 }}>Last reviewed by {claim.reviewed_by_name}.</p>}
        </>
      )}
    </Drawer>
  );
}

function ClaimRow({ c, onOpen, onAct, onEdit, canReview, canAnswer }) {
  const dim = c.label === 'rejected' || c.label === 'unsupported';
  return (
    <div className={`claim ${dim ? 'dim' : ''}`}>
      <div>
        <Badge label={c.label} />
        <div className="type-tag">{TYPE_LABEL[c.type]}</div>
      </div>
      <div>
        <div className="stmt">{c.statement}</div>
        <div className="meta">
          {c.owner && <span>Owner: <b style={{ fontWeight: 550, color: 'var(--ink-700)' }}>{c.owner}</b></span>}
          {c.due && <span>Due {fmtDate(c.due)}</span>}
          {c.severity && <span className={`sev-${c.severity}`}>{c.severity}</span>}
          {c.recurring ? <span className="chip warn">Recurring</span> : null}
          <Clearance level={c.clearance} />
          <button className="link" onClick={() => onOpen(c)}>Evidence{c.source_count > 1 ? ` (${c.source_count} sources)` : ''}</button>
          <span>{c.sources[0]}{c.sources.length > 1 ? ` +${c.sources.length - 1}` : ''}</span>
        </div>
        {c.answer && <div className="small" style={{ marginTop: 6 }}><b style={{ fontWeight: 600 }}>{c.answered_by_name}:</b> {c.answer}</div>}
      </div>
      <div className="row-actions">
        {canAnswer && ['gap', 'question'].includes(c.type) && c.label !== 'rejected' && <button className="btn sm" onClick={() => onOpen(c)}><MessageSquarePlus size={13} /> {c.answer ? 'Edit answer' : 'Answer'}</button>}
        {canReview && !dim && c.label !== 'verified' && c.label !== 'stated' && <button className="icon-btn" title="Confirm against source" aria-label="Confirm" onClick={() => onAct(c, 'confirm')}><Check size={17} /></button>}
        {canReview && !dim && <button className="icon-btn" title="Correct" aria-label="Correct" onClick={() => onEdit(c)}><Pencil size={16} /></button>}
        {canReview && !dim && <button className="icon-btn" title="Reject" aria-label="Reject" onClick={() => onAct(c, 'reject')}><X size={17} /></button>}
        {canReview && c.label === 'rejected' && <button className="icon-btn" title="Restore" aria-label="Restore" onClick={() => onAct(c, 'restore')}><RotateCcw size={16} /></button>}
      </div>
    </div>
  );
}

function ConflictCard({ x, canReview, reload, onOpen }) {
  const toast = useToast();
  const [note, setNote] = useState('');
  async function resolve(resolution) {
    try { await api.post(`/conflicts/${x.id}/resolve`, { resolution, note }); toast('Conflict recorded'); reload(); } catch (e) { toast(e.message, 'error'); }
  }
  const done = x.status !== 'open';
  const Side = ({ c, tag }) => (
    <div className="side">
      <div className="small muted" style={{ marginBottom: 6 }}>Claim {tag}</div>
      <div style={{ lineHeight: 1.5 }}>{c.statement}</div>
      <div className="small muted" style={{ marginTop: 6 }}>{c.sources[0]}</div>
      <div style={{ marginTop: 6, display: 'flex', gap: 8, alignItems: 'center' }}><Badge label={c.label} /><button className="link" onClick={() => onOpen(c)}>Evidence</button></div>
    </div>
  );
  return (
    <div className={`conflict ${done ? 'done' : ''}`}>
      <header><b>{done ? (x.status === 'accepted' ? 'Accepted as unresolved' : 'Resolved') : 'Needs a decision'}</b> · {x.reason}</header>
      <div className="sides"><Side c={x.a} tag="A" /><Side c={x.b} tag="B" /></div>
      {canReview && !done && (
        <footer>
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (optional)" aria-label="Reason" style={{ flex: 1, minWidth: 160 }} />
          <button className="btn sm" onClick={() => resolve('a')}>A is current</button>
          <button className="btn sm" onClick={() => resolve('b')}>B is current</button>
          <button className="btn sm" onClick={() => resolve('unresolved')}>Keep both, unresolved</button>
        </footer>
      )}
      {done && x.note && <footer><span className="small muted">Note: {x.note}</span></footer>}
    </div>
  );
}

function ApproveModal({ pid, onClose, onDone }) {
  const toast = useToast();
  const [note, setNote] = useState('');
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ov] = useAsync(() => api.get(`/projects/${pid}/overview`), [pid]);
  const ready = ov.data?.readiness;
  async function approve() {
    setBusy(true);
    setError('');
    try {
      const v = await api.post(`/projects/${pid}/versions/approve`, { note, accept_unreviewed: accept });
      toast(`Version ${v.number} approved`);
      onDone(v);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return (
    <Modal title="Approve handover" subtitle="This freezes a version. Nothing is shared until you choose recipients." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || !ready || ready.open_conflicts > 0 || (ready.unreviewed > 0 && !accept)} onClick={approve}>{busy ? <Spinner /> : 'Approve version'}</button></>}>
      {!ready ? <Loading /> : (
        <>
          <div className="kv"><span>Readiness</span><b>{ready.score} / 100</b></div>
          <div className="kv"><span>Claims reviewed</span><span>{ready.reviewed} of {ready.claims}</span></div>
          <div className="kv"><span>Open conflicts</span><span style={{ color: ready.open_conflicts ? 'var(--red-700)' : undefined }}>{ready.open_conflicts}</span></div>
          <div className="kv"><span>Unanswered gaps</span><span>{ready.open_gaps}</span></div>
          {ready.open_conflicts > 0 && <div className="notice warn" style={{ margin: '12px 0' }}>Resolve each conflict, or keep both sides and mark them unresolved, before approving.</div>}
          {ready.unreviewed > 0 && ready.open_conflicts === 0 && (
            <label className="notice warn" style={{ margin: '12px 0', cursor: 'pointer' }}>
              <input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} style={{ marginTop: 3 }} />
              <span>Approve with {ready.unreviewed} unreviewed claims. They will be labelled <b>Supported</b>, never Verified.</span>
            </label>
          )}
          <div className="field" style={{ marginTop: 12 }}><label htmlFor="an">Approval note (optional)</label><textarea id="an" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
          {error && <div className="notice error">{error}</div>}
        </>
      )}
    </Modal>
  );
}

export default function Review() {
  const { project, user, reviewer } = useApp();
  const toast = useToast();
  const [claims, reloadC] = useAsync(() => api.get(`/projects/${project.id}/claims`), [project.id]);
  const [conf, reloadF] = useAsync(() => api.get(`/projects/${project.id}/conflicts`), [project.id]);
  const [tab, setTab] = useState('all');
  const [label, setLabel] = useState('');
  const [q, setQ] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState(null);
  const [edit, setEdit] = useState(null);
  const [approving, setApproving] = useState(false);
  const [busy, setBusy] = useState('');
  const reload = () => { reloadC(); reloadF(); };
  const canAnswer = true;

  const live = useMemo(() => (claims.data || []).filter((c) => !['rejected', 'unsupported'].includes(c.label)), [claims.data]);
  const counts = useMemo(() => {
    const m = { all: live.length, gaps: live.filter((c) => ['gap', 'question'].includes(c.type)).length, conflicts: (conf.data || []).length };
    TAB_TYPES.forEach((t) => { m[t] = live.filter((c) => c.type === t).length; });
    return m;
  }, [live, conf.data]);
  const hidden = (claims.data || []).filter((c) => ['rejected', 'unsupported'].includes(c.label)).length;

  const rows = useMemo(() => {
    let r = showAll ? claims.data || [] : live;
    if (tab === 'gaps') r = r.filter((c) => ['gap', 'question'].includes(c.type));
    else if (tab !== 'all' && tab !== 'conflicts') r = r.filter((c) => c.type === tab);
    if (label) r = r.filter((c) => c.label === label);
    if (q.trim()) r = r.filter((c) => (c.statement + ' ' + (c.owner || '')).toLowerCase().includes(q.toLowerCase()));
    return r;
  }, [claims.data, live, tab, label, q, showAll]);

  async function act(c, action) {
    try { await api.patch(`/claims/${c.id}`, { action }); reload(); } catch (e) { toast(e.message, 'error'); }
  }
  async function run() {
    setBusy('run');
    try {
      const r = await api.post(`/projects/${project.id}/reconstruct`);
      toast(`Reconstructed: ${r.claims} claims, ${r.conflicts} conflicts. Your earlier review decisions were kept.`);
      reload();
    } catch (e) { toast(e.message, 'error'); } finally { setBusy(''); }
  }
  async function bulk() {
    setBusy('bulk');
    try { const r = await api.post(`/projects/${project.id}/claims/confirm-supported`); toast(`${r.confirmed} claims confirmed`); reload(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(''); }
  }
  const openClaim = (c) => setOpen(c.id);
  const openObj = (claims.data || []).find((c) => c.id === open);

  const tabs = [
    { key: 'all', label: 'All', count: counts.all },
    ...TAB_TYPES.map((t) => ({ key: t, label: TYPE_PLURAL[t], count: counts[t] })).filter((t) => t.count),
    { key: 'gaps', label: 'Gaps and questions', count: counts.gaps },
    { key: 'conflicts', label: 'Conflicts', count: counts.conflicts },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Review and approve</h1>
          <p>Every claim below links to the passage it came from. Confirm what is right, correct what is not, and close gaps. {reviewer ? '' : 'You can answer gaps; approvers confirm and approve.'}</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={run} disabled={!!busy}>{busy === 'run' ? <Spinner /> : <RefreshCw size={14} />} Re-run reconstruction</button>
          {reviewer && <button className="btn" onClick={bulk} disabled={!!busy}>{busy === 'bulk' ? <Spinner /> : <Check size={14} />} Confirm all supported</button>}
          {reviewer && <button className="btn primary" onClick={() => setApproving(true)}>Approve handover</button>}
        </div>
      </div>

      {claims.loading || conf.loading ? <Loading /> : claims.error ? <div className="notice error">{claims.error.message}</div> : (
        <>
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
          {tab === 'conflicts' ? (
            (conf.data.length === 0 ? <div className="panel"><Empty title="No conflicts detected">Sources agree on deployment region, database, provider, deadlines and owners.</Empty></div> :
              conf.data.map((x) => <ConflictCard key={x.id} x={x} canReview={reviewer} reload={reload} onOpen={openClaim} />))
          ) : (
            <>
              <div className="toolbar">
                <input className="search" type="text" placeholder="Search claims or owners" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search claims" />
                <select value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Filter by label" style={{ width: 170 }}>
                  <option value="">All labels</option>
                  {['verified', 'supported', 'conflicting', 'missing', 'stated', 'inferred'].map((l) => <option key={l} value={l}>{l[0].toUpperCase() + l.slice(1)}</option>)}
                </select>
                {hidden > 0 && <label className="small muted" style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show {hidden} rejected or unverified</label>}
              </div>
              <div className="panel">
                {rows.length === 0 ? <Empty title="Nothing matches">Try another tab or clear the filters.</Empty> :
                  rows.map((c) => <ClaimRow key={c.id} c={c} onOpen={openClaim} onAct={act} onEdit={setEdit} canReview={reviewer} canAnswer={canAnswer} />)}
              </div>
            </>
          )}
        </>
      )}
      {openObj && <ClaimDrawer claim={openObj} onClose={() => setOpen(null)} reload={reload} canReview={reviewer} canAnswer={canAnswer} onEdit={setEdit} />}
      {edit && <EditModal claim={edit} onClose={() => setEdit(null)} onSaved={reload} />}
      {approving && <ApproveModal pid={project.id} onClose={() => setApproving(false)} onDone={(v) => { setApproving(false); reload(); go('handovers'); }} />}
    </div>
  );
}
