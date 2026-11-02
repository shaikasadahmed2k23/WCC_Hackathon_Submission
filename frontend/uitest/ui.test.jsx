import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, configure } from '@testing-library/react';
configure({ asyncUtilTimeout: 8000 });
import userEvent from '@testing-library/user-event';
import React from 'react';

const realFetch = globalThis.fetch;
globalThis.fetch = (u, o) => realFetch('http://127.0.0.1:8000' + u, o);
import App from '../src/App.jsx';

const base = 'http://127.0.0.1:8000/api';
async function apiLogin(who) {
  const r = await realFetch(base + '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: `${who}@campusconnect.example`, password: 'continuity123' }) });
  return (await r.json()).token;
}
async function call(token, method, path, body) {
  const r = await realFetch(base + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  return r.json();
}

async function signInUI(name) {
  localStorage.clear();
  window.location.hash = '';
  render(<App />);
  const btn = await screen.findByText(name, { selector: 'b' });
  await userEvent.click(btn.closest('button'));
}

afterEach(cleanup);
describe('ContinuityOS UI against the live API', () => {
  it('approver sees overview, evidence with highlighted quote, and the review workflow', async () => {
    await signInUI('Meera Iyer');
    expect(await screen.findByText('Needs attention before approval')).toBeTruthy();
    expect(screen.getByText('Handover readiness')).toBeTruthy();
    await screen.findByText('Needs attention before approval');
    window.location.hash = '#/review';
    await screen.findByRole('heading', { name: 'Review and approve' });
    await screen.findAllByText('Supported');
    const links = await screen.findAllByText('Evidence', { selector: 'button' });
    await userEvent.click(links[0]);
    const drawer = await screen.findByRole('dialog');
    expect(drawer.querySelector('mark')).toBeTruthy();
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByRole('tab', { name: /Conflicts/ }));
    expect(await screen.findByText(/Different deployment region/)).toBeTruthy();
    cleanup();
  }, 30000);

  it('approval is blocked in the UI while conflicts are open, then works after review', async () => {
    const t = await apiLogin('meera');
    await signInUI('Meera Iyer');
    await screen.findByText('Needs attention before approval');
    window.location.hash = '#/review';
    await screen.findByRole('heading', { name: 'Review and approve' });
    await userEvent.click(await screen.findByRole('button', { name: 'Approve handover' }));
    expect(await screen.findByText(/Resolve each conflict/)).toBeTruthy();
    const approveBtn = screen.getByRole('button', { name: 'Approve version' });
    expect(approveBtn.disabled).toBe(true);
    cleanup();
    for (const c of await call(t, 'GET', '/projects/1/conflicts')) await call(t, 'POST', `/conflicts/${c.id}/resolve`, { resolution: c.vclass === 'region' ? 'b' : 'unresolved', note: 'ui test' });
    await call(t, 'POST', '/projects/1/claims/confirm-supported');
    const v = await call(t, 'POST', '/projects/1/versions/approve', { note: 'ui test', accept_unreviewed: true });
    const users = await call(t, 'GET', '/users');
    await call(t, 'POST', `/versions/${v.id}/share`, { user_ids: users.filter((u) => u.role.startsWith('incoming')).map((u) => u.id) });
  }, 30000);

  it('restricted volunteer sees the withheld notice and no confidential text; acknowledge works', async () => {
    await signInUI('Nisha Rao');
    expect(await screen.findByText(/withheld/)).toBeTruthy();
    await screen.findByText('Continuation plan');
    expect(document.body.textContent).not.toContain('40,000');
    expect(document.body.textContent).not.toContain('Camp#us2026');
    expect(screen.queryByText('Sources')).toBeNull();
    await userEvent.click(await screen.findByRole('button', { name: 'Acknowledge receipt' }));
    expect(await screen.findByText(/You acknowledged this handover/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Request access' }));
    await userEvent.type(await screen.findByLabelText(/Why do you need it/), 'Need vendor contacts for the fest');
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }));
    expect(await screen.findByText('Request pending')).toBeTruthy();
    cleanup();
  }, 30000);

  it('approver can preview what a restricted role receives', async () => {
    await signInUI('Meera Iyer');
    await screen.findByText('Needs attention before approval');
    window.location.hash = '#/handovers';
    await userEvent.click((await screen.findAllByRole('button', { name: 'Open' }))[0]);
    await screen.findByText(/Prepared for/);
    window.location.hash = window.location.hash + '/incoming_restricted';
    expect(await screen.findByText(/Previewing exactly what/)).toBeTruthy();
    expect(document.body.textContent).not.toContain('40,000');
    cleanup();
  }, 30000);
});
