import React, { useState, useEffect } from 'react';
import { Shell, Login } from './ui.jsx';
import { SearchHome, Results, Preview, History } from './search.jsx';
import { Chat, Library } from './chat-library.jsx';
import { Admin } from './admin.jsx';
import SettingsPanel, { LAYOUTS, ACCENTS } from './SettingsPanel.jsx';
import { api } from './api.js';

const KEY = 'tracuu-state';
const SETTINGS_KEY = 'tracuu-settings';
const LOGGED_OUT_KEY = 'tracuu-dev-logged-out';
const DEFAULT_SETTINGS = { layout: 'Cổ điển', role: 'Quản trị viên', accent: '#d0662f' };

function load(key, fallback) {
  try { return { ...fallback, ...JSON.parse(localStorage.getItem(key) || '{}') }; } catch { return fallback; }
}
function flag(key, v) {
  try { v === undefined ? null : (v ? localStorage.setItem(key, '1') : localStorage.removeItem(key)); return !!localStorage.getItem(key); } catch { return false; }
}

export default function App() {
  const [s, setS] = useState(() => load(SETTINGS_KEY, DEFAULT_SETTINGS));
  const saved = useState(() => load(KEY, {}))[0];
  const [user, setUser] = useState(null);           // null: đang tải hoặc chưa đăng nhập
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState(saved.screen || 'search');
  const [query, setQuery] = useState(saved.query || '');
  const [chat, setChat] = useState({ q: null, doc: null });
  const [dept, setDept] = useState(null);
  const [drawer, setDrawer] = useState(null);

  const layout = LAYOUTS[s.layout] || 'sidebar';

  // Danh tính do server quyết định (ALB + Cognito); client chỉ hiển thị.
  function loadUser() {
    if (import.meta.env.DEV && flag(LOGGED_OUT_KEY)) { setUser(null); setReady(true); return; }
    api('/api/me').then(setUser, () => setUser(null)).finally(() => setReady(true));
  }
  useEffect(loadUser, [s.role]);

  useEffect(() => { localStorage.setItem(KEY, JSON.stringify({ screen, query })); }, [screen, query]);
  useEffect(() => { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); }, [s]);
  useEffect(() => {
    const a = ACCENTS[s.accent] || ACCENTS['#d0662f'];
    const st = document.documentElement.style;
    st.setProperty('--acc', s.accent); st.setProperty('--acc-ink', a[0]); st.setProperty('--acc-soft', a[1]);
  }, [s.accent]);
  useEffect(() => { if (screen === 'admin' && user && user.role !== 'admin') setScreen('search'); }, [user]);

  function login() {
    if (import.meta.env.DEV) { flag(LOGGED_OUT_KEY, false); setReady(false); loadUser(); }
    else window.location.href = '/auth/login';
  }
  function logout() {
    if (import.meta.env.DEV) { flag(LOGGED_OUT_KEY, true); setUser(null); }
    else window.location.href = '/auth/logout';
  }
  function go(sc, o = {}) {
    setDrawer(null);
    if (sc === 'chat' && o.newChat) setChat({ q: null, doc: null });
    if (sc === 'library') setDept(o.dept || null);
    setScreen(sc);
  }
  const search = q => { setQuery(q); setScreen('results'); };
  const toChat = (q, doc = null) => { setDrawer(null); setChat({ q, doc }); setScreen('chat'); };

  if (!ready) return null;
  if (!user) return <><Login onSso={login} />{import.meta.env.DEV && <SettingsPanel s={s} setS={setS} />}</>;

  let body;
  if (screen === 'results' && query) body = <Results layout={layout} query={query} onSearch={search} onChat={toChat} />;
  else if (screen === 'chat') body = <Chat seed={chat.q} seedDoc={chat.doc} openDoc={setDrawer} />;
  else if (screen === 'library') body = <Library user={user} openDoc={setDrawer} dept={dept} />;
  else if (screen === 'history') body = <History onSearch={search} />;
  else if (screen === 'admin' && user.role === 'admin') body = <Admin />;
  else body = <SearchHome user={user} onSearch={search} openDoc={setDrawer} />;

  return <>
    <Shell layout={layout} screen={screen} go={go} user={user} onLogout={logout}>
      <div key={screen + layout} style={{ height: '100%' }}>{body}</div>
      {drawer && <div className="drawer-bg" onClick={() => setDrawer(null)}><div className="drawer" onClick={e => e.stopPropagation()}><Preview d={drawer} onClose={() => setDrawer(null)} onChat={toChat} /></div></div>}
    </Shell>
    {import.meta.env.DEV && <SettingsPanel s={s} setS={setS} />}
  </>;
}
