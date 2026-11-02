import { useState } from 'react';
import { Download, Share2 } from 'lucide-react';
import { useApp, go } from '../App';
import { api, download } from '../api';
import { Empty, Loading, Modal, Spinner, useAsync, useToast } from '../components/ui';
import { fmtDateTime } from '../format';

function ShareModal({ version, onClose, onDone }) {
  const toast = useToast();
  const [users] = useAsync(() => api.get('/users'), []);
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const already = new Set(version.shared_with.map((s) => s.name));
  const incoming = (users.data || []).filter((u) => u.role.startsWith('incoming'));
  async function share() {
    setBusy(true);
    try { const r = await api.post(`/versions/${version.id}/share`, { user_ids: picked }); toast(`Shared with ${r.shared.join(', ')}`); onDone(); onClose(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  }
  return (
    <Modal title={`Share version ${version.number}`} subtitle="Each recipient sees only what their access level allows. Withheld items are never sent to their browser." onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!picked.length || busy} onClick={share}>{busy ? <Spinner /> : 'Share'}</button></>}>
      {users.loading ? <Loading /> : incoming.map((u) => (
        <label key={u.id} className="kv" style={{ cursor: already.has(u.name) ? 'default' : 'pointer', alignItems: 'center', padding: '10px 0' }}>
          <span style={{ display: 'flex', gap: 10, alignItems: 'center', color: 'var(--ink-900)' }}>
            <input type="checkbox" disabled={already.has(u.name)} checked={already.has(u.name) || picked.includes(u.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, u.id] : picked.filter((x) => x !== u.id))} />
            <span><b style={{ fontWeight: 550 }}>{u.name}</b><br /><span className="small muted">{u.title}</span></span>
          </span>
          <span className="small muted">{already.has(u.name) ? 'Already shared' : `Sees up to: ${u.clearance_label}`}</span>
        </label>
      ))}
    </Modal>
  );
}

function Diff({ id }) {
  const [d] = useAsync(() => api.get(`/versions/${id}/diff`), [id]);
  if (d.loading) return <span className="small muted">Comparing</span>;
  if (!d.data.against) return <span className="small muted">First version.</span>;
  const x = d.data;
  return <span className="small muted">Since v{x.against}: {x.added.length} added, {x.removed.length} removed, {x.relabelled.length} relabelled.</span>;
}

export default function Handovers() {
  const { project, reviewer } = useApp();
  const [v, reload] = useAsync(() => api.get(`/projects/${project.id}/versions`), [project.id]);
  const [sharing, setSharing] = useState(null);
  const toast = useToast();
  const exp = async (id, n, fmt) => { try { await download(`/versions/${id}/export?format=${fmt}`, `handover-v${n}.${fmt}`); } catch (e) { toast(e.message, 'error'); } };
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Handovers</h1><p>Each approval freezes a version. Versions never change after approval, so what a recipient saw can always be shown.</p></div>
        <div className="actions"><button className="btn primary" onClick={() => go('review')}>Go to review</button></div>
      </div>
      <div className="panel">
        {v.loading ? <Loading /> : v.error ? <div className="notice error" style={{ margin: 16 }}>{v.error.message}</div> : v.data.length === 0 ? <Empty title="No approved handover yet">Review the claims and approve to create version 1.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Version</th><th>Approved by</th><th>Readiness</th><th className="num">Claims</th><th>Shared with</th><th /></tr></thead>
              <tbody>
                {v.data.map((x) => (
                  <tr key={x.id}>
                    <td><b>v{x.number}</b><div className="small muted">{fmtDateTime(x.created_at)}</div></td>
                    <td>{x.approved_by_name}{x.note && <div className="small muted" style={{ maxWidth: 260 }}>{x.note}</div>}<Diff id={x.id} /></td>
                    <td>{x.readiness}/100</td>
                    <td className="num">{x.claims}</td>
                    <td>
                      {x.shared_with.length === 0 ? <span className="muted">Not shared</span> : x.shared_with.map((s) => (
                        <div key={s.name} className="small">{s.name} <span className={s.acknowledged_at ? 'chip' : 'chip warn'}>{s.acknowledged_at ? 'Acknowledged' : 'Awaiting'}</span></div>
                      ))}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button className="btn sm" onClick={() => go('view/' + x.id)}>Open</button>{' '}
                      {reviewer && <button className="btn sm" onClick={() => setSharing(x)}><Share2 size={13} /> Share</button>}{' '}
                      <button className="icon-btn" title="Export Markdown" aria-label="Export Markdown" onClick={() => exp(x.id, x.number, 'md')}><Download size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {sharing && <ShareModal version={sharing} onClose={() => setSharing(null)} onDone={reload} />}
    </div>
  );
}
