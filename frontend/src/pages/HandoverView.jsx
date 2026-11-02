import { useMemo, useState } from 'react';
import { Download, Lock } from 'lucide-react';
import { useApp, go } from '../App';
import { api, download } from '../api';
import { Badge, Clearance, Drawer, Empty, Loading, Modal, Spinner, Tabs, useAsync, useToast } from '../components/ui';
import { EvidenceBody } from '../components/Evidence';
import { TYPE_LABEL, fmtDate, fmtDateTime } from '../format';

const GROUPS = [
  ['decisions', 'Decisions and state', ['decision', 'state']],
  ['risks', 'Risks and dependencies', ['risk', 'dependency']],
  ['work', 'Actions and ownership', ['action', 'owner']],
  ['open', 'Gaps and questions', ['gap', 'question']],
  ['contacts', 'Contacts', ['contact']],
];
const PREVIEW_ROLES = [['incoming_restricted', 'Incoming (restricted)'], ['incoming_peer', 'Incoming (peer)'], ['approver', 'Approver']];

function RequestAccess({ vid, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  async function send() {
    setBusy(true);
    try { await api.post(`/versions/${vid}/access-requests`, { reason }); toast('Request sent to the approver'); onDone(); onClose(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }
  return (
    <Modal title="Request more access" subtitle="An approver decides. If approved, you move up one access level for this handover only." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={reason.trim().length < 5 || busy} onClick={send}>{busy ? <Spinner /> : 'Send request'}</button></>}>
      <div className="field"><label htmlFor="rr">Why do you need it?</label><textarea id="rr" rows={4} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="For example: I am taking over event registrations and need the vendor contacts." /></div>
    </Modal>
  );
}

function ClaimLine({ c, onOpen }) {
  return (
    <div className="claim">
      <div><Badge label={c.label} /><div className="type-tag">{TYPE_LABEL[c.type]}</div></div>
      <div>
        <div className="stmt">{c.statement}</div>
        <div className="meta">
          {c.owner && <span>Owner: <b style={{ fontWeight: 550, color: 'var(--ink-700)' }}>{c.owner}</b></span>}
          {c.due && <span>Due {fmtDate(c.due)}</span>}
          {c.severity && <span className={`sev-${c.severity}`}>{c.severity}</span>}
          {c.recurring ? <span className="chip warn">Recurring</span> : null}
          <button className="link" onClick={() => onOpen(c)}>Evidence</button>
          <span>{c.sources?.[0] || c.evidence?.[0]?.source_name}</span>
        </div>
        {c.answer && <div className="small" style={{ marginTop: 6 }}><b style={{ fontWeight: 600 }}>{c.answered_by_name}:</b> {c.answer}</div>}
      </div>
      <span />
    </div>
  );
}

export default function HandoverView({ versionId, previewAs }) {
  const { user, reviewer } = useApp();
  const toast = useToast();
  const [s, reload] = useAsync(() => api.get(`/versions/${versionId}/view${previewAs ? `?preview_as=${previewAs}` : ''}`), [versionId, previewAs]);
  const [tab, setTab] = useState('plan');
  const [open, setOpen] = useState(null);
  const [requesting, setRequesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const claims = s.data?.claims || [];
  const byId = useMemo(() => Object.fromEntries(claims.map((c) => [c.id, c])), [claims]);

  if (s.loading) return <Loading />;
  if (s.error) return <div className="page"><div className="notice error">{s.error.message}</div></div>;
  const v = s.data;

  async function ack() {
    setBusy(true);
    try { await api.post(`/versions/${versionId}/acknowledge`); toast('Receipt acknowledged'); reload(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }
  const exp = async (fmt) => { try { await download(`/versions/${versionId}/export?format=${fmt}`, `handover-v${v.version.number}.${fmt}`); } catch (e) { toast(e.message, 'error'); } };

  const tabs = [{ key: 'plan', label: 'Continuation plan' }, ...GROUPS.map(([k, label, types]) => ({ key: k, label, count: claims.filter((c) => types.includes(c.type)).length })).filter((t) => t.count), { key: 'conflicts', label: 'Conflicting information', count: v.conflicts.length }];
  const group = GROUPS.find(([k]) => k === tab);
  const openClaim = byId[open];

  return (
    <div className="page">
      {v.preview && (
        <div className="notice info" style={{ marginBottom: 14, alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Previewing exactly what <b>{v.role_label}</b> receives. Withheld content is removed on the server, not hidden by the page.</span>
          <button className="btn sm" onClick={() => go('view/' + versionId)}>Exit preview</button>
        </div>
      )}
      <div className="page-head">
        <div>
          <h1>{v.project.name} handover</h1>
          <p>Version {v.version.number}, approved by {v.version.approved_by} on {fmtDateTime(v.version.created_at)}.{v.version.note ? ` "${v.version.note}"` : ''}</p>
          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <span className="chip">Prepared for: {v.role_label}</span><Clearance level={v.clearance} />{v.clearance === 0 && <span className="chip">General access</span>}
            <span className="chip">{claims.length} items shown</span>
          </div>
        </div>
        <div className="actions">
          {reviewer && !v.preview && (
            <select aria-label="Preview as role" value="" onChange={(e) => e.target.value && go(`view/${versionId}/${e.target.value}`)} style={{ width: 190 }}>
              <option value="">Preview as role...</option>
              {PREVIEW_ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          )}
          <button className="btn" onClick={() => exp('md')}><Download size={14} /> Markdown</button>
          <button className="btn" onClick={() => exp('json')}><Download size={14} /> JSON</button>
        </div>
      </div>

      {v.can_acknowledge && !v.acknowledged_at && (
        <div className="notice warn" style={{ marginBottom: 14, alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Read the plan and the evidence behind anything that surprises you. Then confirm that you have received this handover.</span>
          <button className="btn primary" disabled={busy} onClick={ack}>{busy ? <Spinner /> : 'Acknowledge receipt'}</button>
        </div>
      )}
      {v.acknowledged_at && <div className="notice info" style={{ marginBottom: 14 }}>You acknowledged this handover on {fmtDateTime(v.acknowledged_at)}.</div>}

      {v.hidden.total > 0 && (
        <div className="notice" style={{ marginBottom: 14, alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Lock size={16} /> <span><b>{v.hidden.total} item{v.hidden.total > 1 ? 's are' : ' is'} withheld</b> at your access level ({Object.entries(v.hidden.by_type).map(([t, n]) => `${n} ${TYPE_LABEL[t].toLowerCase()}`).join(', ')}). Their content was not sent to this page.</span></span>
          {v.can_acknowledge && !v.preview && (v.access_request === 'pending' ? <span className="chip warn">Request pending</span> : <button className="btn sm" onClick={() => setRequesting(true)}>Request access</button>)}
        </div>
      )}
      {v.access_request === 'approved' && <div className="notice info" style={{ marginBottom: 14 }}>An approver raised your access level for this handover.</div>}
      {v.access_request === 'denied' && <div className="notice warn" style={{ marginBottom: 14 }}>Your last access request was declined.</div>}

      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'plan' && (
        <div className="grid2">
          <div className="stack">
            {v.plan.length === 0 && <div className="panel"><Empty title="No actions in this handover">Nothing in the plan is visible at your access level.</Empty></div>}
            {v.plan.map((b) => (
              <div key={b.key} className="panel plan-sec">
                <div className="panel-head"><div><h2>{b.title}</h2></div><span className="chip">{b.items.length}</span></div>
                <div style={{ padding: '0 16px' }}>
                  {b.items.map((it, i) => (
                    <div key={i} className="plan-item" style={i === 0 ? { borderTop: 0 } : undefined}>
                      <div>
                        <div className="t">{it.text}</div>
                        <div className="small muted" style={{ marginTop: 3 }}>{it.kind} · Owner: {it.owner}{it.due ? ` · due ${fmtDate(it.due)}` : ''} · <button className="link" onClick={() => setOpen(it.claim_id)}>Evidence</button></div>
                      </div>
                      <Badge label={it.label} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="panel">
            <div className="panel-head"><h2>How to read this</h2></div>
            <div className="panel-body small">
              <p style={{ marginBottom: 10 }}>The plan is built only from items you are allowed to see. It is ordered by due date, then by risk.</p>
              <p style={{ marginBottom: 10 }}><Badge label="verified" /> was confirmed against a source by a person.</p>
              <p style={{ marginBottom: 10 }}><Badge label="supported" /> has a matching quote in a source but nobody has reviewed it.</p>
              <p style={{ marginBottom: 10 }}><Badge label="conflicting" /> means sources disagree. Check before acting.</p>
              <p><Badge label="missing" /> means nobody wrote this down. Ask the team.</p>
            </div>
          </div>
        </div>
      )}
      {group && (
        <div className="panel">
          {claims.filter((c) => group[2].includes(c.type)).map((c) => <ClaimLine key={c.id} c={c} onOpen={(x) => setOpen(x.id)} />)}
        </div>
      )}
      {tab === 'conflicts' && (
        v.conflicts.length === 0 ? <div className="panel"><Empty title="No conflicting information">At your access level, the sources agree.</Empty></div> :
          v.conflicts.map((x) => (
            <div key={x.id} className="conflict">
              <header><b>{x.status === 'resolved' ? 'Resolved by a reviewer' : 'Still unresolved'}</b> · {x.reason}</header>
              <div className="sides">
                {[x.claim_a, x.claim_b].map((id) => (
                  <div key={id} className="side">
                    <div style={{ lineHeight: 1.5 }}>{byId[id]?.statement}</div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}><Badge label={byId[id]?.label} /><button className="link" onClick={() => setOpen(id)}>Evidence</button></div>
                  </div>
                ))}
              </div>
              {x.note && <footer><span className="small muted">Reviewer note: {x.note}</span></footer>}
            </div>
          ))
      )}
      {openClaim && <Drawer title={TYPE_LABEL[openClaim.type]} eyebrow="Evidence" onClose={() => setOpen(null)}><EvidenceBody claim={openClaim} /></Drawer>}
      {requesting && <RequestAccess vid={versionId} onClose={() => setRequesting(false)} onDone={reload} />}
    </div>
  );
}
