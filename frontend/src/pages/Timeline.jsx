import { useApp, go } from '../App';
import { api } from '../api';
import { Badge, Empty, Loading, useAsync } from '../components/ui';
import { fmtDate, TYPE_LABEL } from '../format';

export default function Timeline() {
  const { project } = useApp();
  const [s] = useAsync(() => api.get(`/projects/${project.id}/timeline`), [project.id]);
  if (s.loading) return <Loading />;
  if (s.error) return <div className="page"><div className="notice error">{s.error.message}</div></div>;
  const days = [];
  s.data.forEach((e) => {
    const last = days[days.length - 1];
    if (last && last.date === e.date) last.items.push(e);
    else days.push({ date: e.date, items: [e] });
  });
  return (
    <div className="page">
      <div className="page-head"><div><h1>Timeline</h1><p>Decisions, risks, open questions and commitments in the order the sources record them. Dates come from chat timestamps or document dates.</p></div></div>
      <div className="panel">
        {days.length === 0 && <Empty title="No dated events yet">Run reconstruction after adding sources with dates.</Empty>}
        {days.map((d) => (
          <div key={d.date} className="tl-day">
            <div className="tl-date">{fmtDate(d.date)}</div>
            <div>
              {d.items.map((e) => (
                <div key={e.claim_id} className="tl-item">
                  <span className="chip" style={{ minWidth: 92, justifyContent: 'center' }}>{TYPE_LABEL[e.type]}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ lineHeight: 1.5 }}>{e.text}</div>
                    <div className="small muted">{e.source}{e.due ? ` · due ${fmtDate(e.due)}` : ''}</div>
                  </div>
                  <Badge label={e.label} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
