import { Check, X } from 'lucide-react';
import { api } from '../api';
import { Empty, Loading, useAsync, useToast } from '../components/ui';
import { fmtDateTime, SENS } from '../format';

export default function Access() {
  const toast = useToast();
  const [users] = useAsync(() => api.get('/users'), []);
  const [reqs, reload] = useAsync(() => api.get('/access-requests'), []);
  async function decide(id, approve) {
    try { await api.post(`/access-requests/${id}/decide`, { approve }); toast(approve ? 'Access granted for that handover' : 'Request declined'); reload(); } catch (e) { toast(e.message, 'error'); }
  }
  return (
    <div className="page">
      <div className="page-head"><div><h1>Access and roles</h1><p>Access is enforced on the server. Every claim has an access level, taken from the most sensitive passage it rests on.</p></div></div>
      <div className="stack">
        <div className="panel">
          <div className="panel-head"><div><h2>Access requests</h2><p>Recipients can ask for one level more, for one handover.</p></div></div>
          {reqs.loading ? <Loading /> : reqs.error ? <div className="notice error" style={{ margin: 16 }}>{reqs.error.message}</div> : reqs.data.length === 0 ? <Empty title="No requests">When a recipient asks for more access it appears here.</Empty> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Who</th><th>Reason</th><th>Requested</th><th>Status</th><th /></tr></thead>
              <tbody>{reqs.data.map((r) => (
                <tr key={r.id}>
                  <td><b style={{ fontWeight: 550 }}>{r.user_name}</b><div className="small muted">Handover v{r.version_number}</div></td>
                  <td style={{ maxWidth: 360 }}>{r.reason}</td>
                  <td className="muted">{fmtDateTime(r.created_at)}</td>
                  <td><span className={`chip ${r.status === 'pending' ? 'warn' : ''}`}>{r.status}</span></td>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.status === 'pending' && <><button className="btn sm" onClick={() => decide(r.id, true)}><Check size={13} /> Approve</button>{' '}<button className="btn sm" onClick={() => decide(r.id, false)}><X size={13} /> Decline</button></>}</td>
                </tr>))}
              </tbody></table></div>
          )}
        </div>
        <div className="panel">
          <div className="panel-head"><div><h2>People and roles</h2></div></div>
          {users.loading ? <Loading /> : users.error ? <div className="notice error" style={{ margin: 16 }}>{users.error.message}</div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Name</th><th>Role</th><th>Sees up to</th><th>Can do</th></tr></thead>
              <tbody>{users.data.map((u) => (
                <tr key={u.id}>
                  <td><b style={{ fontWeight: 550 }}>{u.name}</b><div className="small muted">{u.title}</div></td>
                  <td>{u.role_label}</td><td>{SENS[u.clearance]}</td>
                  <td className="muted">{{ admin: 'Everything, including source deletion', approver: 'Review, resolve conflicts, approve, share', departing: 'Add sources, answer gaps, read the draft', incoming_peer: 'Read the shared handover, acknowledge', incoming_restricted: 'Read the shared handover, acknowledge' }[u.role]}</td>
                </tr>))}
              </tbody></table></div>
          )}
        </div>
      </div>
    </div>
  );
}
