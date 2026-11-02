import { useApp, go } from '../App';
import { api } from '../api';
import { Badge, Loading, useAsync, LabelLegend, Modal } from '../components/ui';
import { fmtDateTime, LABELS } from '../format';
import { useState } from 'react';

const ACTION_TEXT = {
  'source.added': 'Source added', 'reconstruction.run': 'Reconstruction run', 'claim.confirm': 'Claim confirmed', 'claim.reject': 'Claim rejected',
  'claim.edit': 'Claim edited', 'claim.answered': 'Gap answered', 'conflict.resolved': 'Conflict resolved', 'handover.approved': 'Handover approved',
  'handover.shared': 'Handover shared', 'handover.viewed': 'Handover viewed', 'handover.acknowledged': 'Receipt acknowledged',
  'claim.bulk_confirm': 'Bulk confirm', 'auth.login': 'Signed in', 'workspace.seeded': 'Demo data loaded', 'access.requested': 'Access requested',
  'access.approved': 'Access granted', 'access.denied': 'Access denied', 'handover.exported': 'Handover exported', 'handover.previewed': 'Role preview',
  'source.sensitivity': 'Sensitivity changed', 'source.deleted': 'Source deleted',
};

export default function Overview() {
  const { project, user, reviewer } = useApp();
  const [state] = useAsync(() => api.get(`/projects/${project.id}/overview`), [project.id]);
  const [legend, setLegend] = useState(false);
  if (state.loading) return <Loading />;
  if (state.error) return <div className="page"><div className="notice error">{state.error.message}</div></div>;
  const o = state.data;
  const r = o.readiness;

  const steps = [
    { n: '01', t: 'Connect', d: `${o.sources} sources, ${o.chunks} passages`, done: o.sources > 0, to: 'sources' },
    { n: '02', t: 'Reconstruct', d: `${o.claims} claims extracted`, done: o.claims > 0, to: 'review' },
    { n: '03', t: 'Verify', d: `${r.open_conflicts} open conflicts, ${r.open_gaps} gaps flagged`, done: o.claims > 0, to: 'review' },
    { n: '04', t: 'Review', d: `${r.unreviewed} claims unreviewed`, done: o.claims > 0 && r.unreviewed === 0 && r.open_conflicts === 0, to: 'review' },
    { n: '05', t: 'Handover', d: o.versions.length ? `Version ${o.versions[0].number} approved` : 'Nothing approved yet', done: o.versions.length > 0, to: 'handovers' },
  ];
  const activeIdx = steps.findIndex((s) => !s.done);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{o.project.name}</h1>
          <p>{o.project.description} Handover from <b>{o.departing}</b>.</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => setLegend(true)}>What do the labels mean?</button>
          <button className="btn primary" onClick={() => go('review')}>Open review</button>
        </div>
      </div>

      <div className="steps" style={{ marginBottom: 16 }}>
        {steps.map((s, i) => (
          <button key={s.n} className={`step ${s.done ? 'done' : ''} ${i === activeIdx ? 'active' : ''}`} onClick={() => go(s.to)} style={{ textAlign: 'left', border: 0, background: i === activeIdx ? undefined : '#fff', cursor: 'pointer' }}>
            <span className="n">{s.n}{s.done ? ' · done' : i === activeIdx ? ' · next' : ''}</span>
            <b>{s.t}</b>
            <small>{s.d}</small>
          </button>
        ))}
      </div>

      <div className="grid2">
        <div className="stack">
          <div className="panel">
            <div className="panel-head"><div><h2>Needs attention before approval</h2><p>Open conflicts, unowned work and unreviewed high-severity risks.</p></div></div>
            {o.attention.length === 0 ? (
              <div className="empty"><b>Nothing is blocking approval</b></div>
            ) : (
              o.attention.map((a, i) => (
                <div key={i} className="claim" style={{ gridTemplateColumns: '104px 1fr auto' }}>
                  <div><span className={`badge ${a.kind === 'conflict' ? 'b-conflicting' : a.kind === 'gap' ? 'b-missing' : 'b-supported'}`}>{a.kind === 'conflict' ? 'Conflict' : a.kind === 'gap' ? 'No owner' : 'High risk'}</span></div>
                  <div className="stmt" style={{ fontSize: 13.5 }}>{a.text}</div>
                  <button className="btn sm" onClick={() => go('review')}>Review</button>
                </div>
              ))
            )}
          </div>

          <div className="panel">
            <div className="panel-head"><div><h2>Claims by confidence</h2><p>Every claim carries one label. Nothing generated is shown as verified.</p></div></div>
            <div className="table-wrap">
              <table>
                <tbody>
                  {['verified', 'supported', 'conflicting', 'missing', 'stated', 'inferred'].map((k) => (
                    <tr key={k}>
                      <td style={{ width: 130 }}><Badge label={k} /></td>
                      <td className="muted">{LABELS[k].help}</td>
                      <td className="num"><b>{o.by_label[k] || 0}</b></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="panel">
            <div className="panel-head"><div><h2>Handover readiness</h2><p>Computed from review progress, shown in full.</p></div></div>
            <div className="panel-body">
              <div className="score">{r.score}<span className="muted" style={{ fontSize: 16, fontWeight: 500 }}> / 100</span></div>
              <div className="bar"><i style={{ width: `${r.score}%` }} /></div>
              <div className="kv"><span>Claims reviewed</span><span>{r.reviewed} of {r.claims} ({r.base}%)</span></div>
              <div className="kv"><span>Open conflicts</span><span>{r.open_conflicts}{r.penalty_conflicts ? ` (-${r.penalty_conflicts})` : ''}</span></div>
              <div className="kv"><span>Unanswered gaps</span><span>{r.open_gaps}{r.penalty_gaps ? ` (-${r.penalty_gaps})` : ''}</span></div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h2>Recent activity</h2><button className="link" onClick={() => go('activity')}>All activity</button></div>
            {o.recent.map((a) => (
              <div key={a.id} className="kv" style={{ padding: '9px 16px', gap: 12 }}>
                <span style={{ color: 'var(--ink-900)' }}>{ACTION_TEXT[a.action] || a.action}<br /><span className="small muted">{a.actor_name}</span></span>
                <span className="small muted" style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(a.ts)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      {legend && <Modal title="Confidence labels" subtitle="What each label tells the reader." onClose={() => setLegend(false)}><LabelLegend /></Modal>}
    </div>
  );
}
