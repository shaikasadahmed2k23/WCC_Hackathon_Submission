import { api } from '../api';
import { Loading, useAsync } from '../components/ui';
import { fmtDateTime } from '../format';

export default function ActivityLog() {
  const [s] = useAsync(() => api.get('/audit?limit=200'), []);
  if (s.loading) return <Loading />;
  if (s.error) return <div className="page"><div className="notice error">{s.error.message}</div></div>;
  return (
    <div className="page">
      <div className="page-head"><div><h1>Activity</h1><p>An append-only record of who ingested, edited, approved, shared and viewed what.</p></div></div>
      <div className="panel table-wrap">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Object</th><th>Detail</th></tr></thead>
          <tbody>
            {s.data.map((a) => (
              <tr key={a.id}>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(a.ts)}</td>
                <td>{a.actor_name}</td>
                <td><code style={{ fontSize: 12.5 }}>{a.action}</code></td>
                <td>{a.object}</td>
                <td className="muted" style={{ maxWidth: 360, overflowWrap: 'anywhere' }}>{a.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
