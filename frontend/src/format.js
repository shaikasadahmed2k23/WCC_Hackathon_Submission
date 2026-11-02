export const TYPE_LABEL = {
  decision: 'Decision', owner: 'Ownership', action: 'Action', risk: 'Risk', dependency: 'Dependency',
  state: 'Project state', question: 'Open question', gap: 'Gap', contact: 'Contact',
};
export const TYPE_PLURAL = {
  decision: 'Decisions', owner: 'Ownership', action: 'Actions', risk: 'Risks', dependency: 'Dependencies',
  state: 'Project state', question: 'Open questions', gap: 'Gaps', contact: 'Contacts',
};
export const LABELS = {
  verified: { text: 'Verified', help: 'A reviewer confirmed this against its source.' },
  supported: { text: 'Supported', help: 'The quote exists in the source. Not yet reviewed by a person.' },
  inferred: { text: 'Inferred', help: 'Reasoned across sources. Treat as a lead, not a fact.' },
  conflicting: { text: 'Conflicting', help: 'Sources disagree. A reviewer must decide.' },
  missing: { text: 'Missing', help: 'The sources do not answer this.' },
  stated: { text: 'Stated', help: 'Answered by a person. There is no document evidence.' },
  unsupported: { text: 'Unverified', help: 'The model\u2019s quote was not found in the source. Never shown as fact.' },
  rejected: { text: 'Rejected', help: 'A reviewer removed this from the handover.' },
};
export const SENS = ['General', 'Internal', 'Confidential'];
export const KIND_LABEL = { doc: 'Document', task: 'Task board', chat: 'Chat export', data: 'Data file', repo: 'Repository' };

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
export function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
export const initials = (name = '') => name.split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase();
