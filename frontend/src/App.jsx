import { createContext, useContext, useEffect, useState } from 'react';
import { Activity, BookOpen, FileText, FolderKanban, GitBranch, LayoutDashboard, Menu, ShieldCheck, ClipboardCheck } from 'lucide-react';
import { api, getToken, setToken } from './api';
import { Loading, ToastProvider } from './components/ui';
import { initials } from './format';
import Login from './pages/Login';
import Overview from './pages/Overview';
import Sources from './pages/Sources';
import Review from './pages/Review';
import Timeline from './pages/Timeline';
import Handovers from './pages/Handovers';
import HandoverView from './pages/HandoverView';
import Access from './pages/Access';
import ActivityLog from './pages/ActivityLog';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

function useHash() {
  const [h, setH] = useState(window.location.hash.replace(/^#\/?/, ''));
  useEffect(() => {
    const f = () => setH(window.location.hash.replace(/^#\/?/, ''));
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);
  return h;
}
export const go = (path) => { window.location.hash = '/' + path; };

const STAFF_NAV = [
  ['overview', 'Overview', LayoutDashboard],
  ['sources', 'Sources', FileText],
  ['review', 'Review and approve', ClipboardCheck],
  ['timeline', 'Timeline', GitBranch],
  ['handovers', 'Handovers', BookOpen],
];

function Shell({ user, project, config, onSignOut }) {
  const hash = useHash();
  const [open, setOpen] = useState(false);
  const staff = ['admin', 'approver', 'departing'].includes(user.role);
  const reviewer = ['admin', 'approver'].includes(user.role);
  const [page, arg, arg2] = hash.split('/');
  const current = page || (staff ? 'overview' : 'mine');

  useEffect(() => { setOpen(false); }, [hash]);

  const nav = staff
    ? [...STAFF_NAV, ...(reviewer ? [['access', 'Access and roles', ShieldCheck]] : []), ['activity', 'Activity', Activity]]
    : [['mine', 'My handover', BookOpen]];

  let content;
  if (!staff && !['mine', 'view'].includes(current)) content = <HandoverList />;
  else if (current === 'overview') content = <Overview />;
  else if (current === 'sources') content = <Sources />;
  else if (current === 'review') content = <Review />;
  else if (current === 'timeline') content = <Timeline />;
  else if (current === 'handovers') content = <Handovers />;
  else if (current === 'view' && arg) content = <HandoverView key={arg + (arg2 || '')} versionId={Number(arg)} previewAs={arg2} />;
  else if (current === 'access' && reviewer) content = <Access />;
  else if (current === 'activity') content = <ActivityLog />;
  else if (current === 'mine') content = <HandoverList />;
  else content = <Overview />;

  const titleOf = (nav.find(([k]) => k === current) || [null, current === 'view' ? 'Handover' : ''])[1];

  return (
    <Ctx.Provider value={{ user, project, config, staff, reviewer }}>
      <div className="shell">
        <aside className={`sidebar ${open ? 'open' : ''}`}>
          <div className="brand"><span className="brand-mark">C</span><span>continuity<em>OS</em></span></div>
          <div className="ws"><b>{project.workspace}</b><small>{project.name}</small></div>
          <div className="nav-label">{staff ? 'Workspace' : 'Your handover'}</div>
          {nav.map(([key, label, Icon]) => (
            <button key={key} className={`nav-item ${current === key || (key === 'handovers' && current === 'view') ? 'active' : ''}`} onClick={() => go(key)}>
              <Icon size={16} />{label}
            </button>
          ))}
          <div className="sidebar-foot">
            <div className="me"><span className="avatar">{initials(user.name)}</span><div><b>{user.name}</b><small>{user.role_label}</small></div></div>
            <button className="signout" onClick={onSignOut}>Sign out</button>
          </div>
        </aside>
        <div className="main">
          <div className="topbar">
            <button className="icon-btn menu-btn" onClick={() => setOpen(!open)} aria-label="Menu"><Menu size={18} /></button>
            <span>{project.name}</span><span>/</span><b>{titleOf}</b>
            <span className="spacer" />
            <span className="chip" title="How claims are extracted">Extractor: {config.extractor === 'llm' ? `language model (${config.llm_model}) + verifier` : 'rules + verifier'}</span>
            <span className="chip">Access: {user.clearance_label}</span>
          </div>
          {content}
        </div>
      </div>
    </Ctx.Provider>
  );
}

function HandoverList() {
  const [list, setList] = useState(null);
  useEffect(() => { api.get('/my/handovers').then(setList); }, []);
  useEffect(() => { if (list && list.length === 1) go('view/' + list[0].id); }, [list]);
  if (!list) return <Loading />;
  if (!list.length)
    return (
      <div className="page">
        <div className="panel"><div className="empty"><b>No handover has been shared with you yet</b>When an approver approves and shares a handover, it will appear here.</div></div>
      </div>
    );
  return (
    <div className="page">
      <div className="page-head"><div><h1>My handover</h1><p>Handovers shared with you.</p></div></div>
      <div className="panel table-wrap">
        <table>
          <thead><tr><th>Project</th><th>Version</th><th>Status</th><th /></tr></thead>
          <tbody>
            {list.map((h) => (
              <tr key={h.id} className="click" onClick={() => go('view/' + h.id)}>
                <td>{h.project}</td><td>v{h.number}</td><td>{h.acknowledged_at ? 'Acknowledged' : 'Awaiting acknowledgement'}</td>
                <td><button className="btn sm">Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function App() {
  const [boot, setBoot] = useState({ loading: true });
  const refresh = async () => {
    let config = null;
    try { config = await api.get('/config'); } catch (e) { setBoot({ loading: false, error: e.message }); return; }
    if (!getToken()) { setBoot({ loading: false, config, user: null }); return; }
    try {
      const [user, projects] = await Promise.all([api.get('/me'), api.get('/projects')]);
      setBoot({ loading: false, config, user, project: projects[0] });
    } catch {
      setToken(null);
      setBoot({ loading: false, config, user: null });
    }
  };
  useEffect(() => {
    refresh();
    const f = () => setBoot((b) => ({ ...b, user: null }));
    window.addEventListener('continuityos:signed-out', f);
    return () => window.removeEventListener('continuityos:signed-out', f);
  }, []);

  const signOut = async () => {
    try { await api.post('/auth/logout'); } catch { /* already expired */ }
    setToken(null);
    window.location.hash = '';
    setBoot((b) => ({ ...b, user: null }));
  };

  if (boot.loading) return <Loading text="Starting" />;
  if (boot.error)
    return (
      <div className="login-form" style={{ minHeight: '100vh' }}>
        <div className="login-box"><div className="notice error">{boot.error} Start the backend with <code>uvicorn app.main:app --port 8000</code> and reload.</div></div>
      </div>
    );
  return (
    <ToastProvider>
      {boot.user && boot.project ? (
        <Shell user={boot.user} project={boot.project} config={boot.config} onSignOut={signOut} />
      ) : (
        <Login config={boot.config} onDone={refresh} />
      )}
    </ToastProvider>
  );
}
