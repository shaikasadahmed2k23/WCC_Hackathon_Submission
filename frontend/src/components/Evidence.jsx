import { useState } from 'react';
import { Lock } from 'lucide-react';
import { Badge, Clearance } from './ui';
import { KIND_LABEL, LABELS, fmtDateTime, TYPE_LABEL } from '../format';

function Highlighted({ item }) {
  const t = item.text;
  if (!item.hl || item.start === undefined || item.end > t.length || item.end <= item.start) return <>{t}</>;
  return <>{t.slice(0, item.start)}<mark>{t.slice(item.start, item.end)}</mark>{t.slice(item.end)}</>;
}

export function Context({ items }) {
  return (
    <div className="ctx">
      {items.map((it, i) =>
        it.restricted ? (
          <div key={i} className="ctx-line restricted"><Lock size={12} style={{ verticalAlign: -1 }} /> Neighbouring text is above your access level and is hidden.</div>
        ) : (
          <div key={i} className={`ctx-line ${it.hl ? 'hl' : ''}`}>
            {(it.speaker || it.ts) && (
              <span className="at">{it.speaker && <span className="who">{it.speaker}</span>}{it.speaker && it.ts ? ' · ' : ''}{it.ts ? fmtDateTime(it.ts) : ''}</span>
            )}
            <Highlighted item={it} />
          </div>
        ),
      )}
    </div>
  );
}

export function EvidenceBody({ claim }) {
  const [i, setI] = useState(0);
  const ev = claim.evidence?.[i];
  return (
    <>
      <h3>Claim</h3>
      <p style={{ lineHeight: 1.55 }}>{claim.statement}</p>
      <div className="meta" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10, alignItems: 'center' }}>
        <Badge label={claim.label} />
        <span className="chip">{TYPE_LABEL[claim.type]}</span>
        <Clearance level={claim.clearance} />
        {claim.owner && <span className="chip">Owner: {claim.owner}</span>}
        {claim.due && <span className="chip">Due {claim.due}</span>}
        {claim.severity && <span className={`chip sev-${claim.severity}`}>{claim.severity} severity</span>}
        {claim.recurring ? <span className="chip warn">Recurring problem</span> : null}
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>{LABELS[claim.label]?.help}</p>
      {claim.answer && (
        <>
          <h3>Answer</h3>
          <p style={{ lineHeight: 1.55 }}>{claim.answer}</p>
          <p className="small muted" style={{ marginTop: 4 }}>Stated by {claim.answered_by_name}. This answer has no document behind it.</p>
        </>
      )}
      <h3>Evidence ({claim.evidence?.length || 0})</h3>
      {claim.evidence?.length > 1 && (
        <div className="tabs" style={{ marginBottom: 10 }}>
          {claim.evidence.map((e, k) => (
            <button key={k} className={`tab ${k === i ? 'active' : ''}`} onClick={() => setI(k)}>Source {k + 1}</button>
          ))}
        </div>
      )}
      {ev ? (
        <>
          <div className="src-card">
            <b style={{ fontSize: 13.5 }}>{ev.source_name}</b>
            <div className="small muted" style={{ marginTop: 3 }}>{KIND_LABEL[ev.source_kind] || ev.source_kind} · {ev.location}</div>
          </div>
          <Context items={ev.context} />
          <p className="small muted" style={{ marginTop: 8 }}>The highlighted text is the exact passage this claim rests on.</p>
        </>
      ) : <p className="muted">No evidence attached.</p>}
      {claim.original_statement && claim.original_statement !== claim.statement && (
        <>
          <h3>Original extraction</h3>
          <p className="muted" style={{ lineHeight: 1.5 }}>{claim.original_statement}</p>
        </>
      )}
    </>
  );
}
