import { useState } from 'react';
import { api, setToken } from '../api';
import { Spinner } from '../components/ui';

export default function Login({ config, onDone }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e, creds) {
    e?.preventDefault();
    const body = creds || { email, password };
    setBusy(true);
    setError('');
    try {
      const r = await api.post('/auth/login', body);
      setToken(r.token);
      window.location.hash = '';
      await onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-side">
        <div className="brand" style={{ padding: 0 }}><span className="brand-mark">C</span><span>continuity<em>OS</em></span></div>
        <div>
          <h1>Your team's knowledge should never leave with a person.</h1>
          <p>ContinuityOS rebuilds a project's state from authorised sources, shows the evidence behind every statement, and shares a handover only after a person approves it.</p>
        </div>
        <ol>
          <li>Connect authorised sources</li>
          <li>Reconstruct decisions, owners, risks and gaps</li>
          <li>Verify each claim against its source</li>
          <li>Review, correct and approve</li>
          <li>Share a role-appropriate handover</li>
        </ol>
      </div>
      <div className="login-form">
        <div className="login-box">
          <h2>Sign in</h2>
          <p className="muted" style={{ marginBottom: 18 }}>Use a demo account below. All data in this workspace is synthetic.</p>
          <form onSubmit={submit}>
            <div className="field"><label htmlFor="em">Email</label><input id="em" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
            <div className="field"><label htmlFor="pw">Password</label><input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
            {error && <div className="notice error" style={{ marginBottom: 12 }}>{error}</div>}
            <button className="btn primary" disabled={busy} style={{ width: '100%', justifyContent: 'center' }}>{busy ? <Spinner /> : 'Sign in'}</button>
          </form>
          {config.demo && (
            <div style={{ marginTop: 26 }}>
              <div className="label">Demo accounts <span className="muted" style={{ fontWeight: 400 }}>(password: {config.demo_password})</span></div>
              <div className="demo-list">
                {config.demo_accounts.map((a) => (
                  <button key={a.email} className="demo-acct" disabled={busy} onClick={() => submit(null, { email: a.email, password: config.demo_password })}>
                    <span><b>{a.name}</b><small>{a.title}</small></span>
                    <small>{a.role_label}</small>
                  </button>
                ))}
              </div>
              <p className="small muted" style={{ marginTop: 10 }}>Try Meera Iyer (approver) first. Then open Nisha Rao to see what a restricted volunteer receives.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
