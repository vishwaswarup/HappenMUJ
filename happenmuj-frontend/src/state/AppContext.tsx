import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, isDemo } from '../lib/api';
import type { RegisterInput } from '../lib/api/api';
import { safeUrl } from '../lib/format';
import { storageGet, storageSet } from '../lib/hooks';
import { currentPath, navigate, qs } from '../lib/router';
import type { EventCardData, SavedItem, User } from '../lib/types';

type ToastKind = 'ok' | 'error' | 'info';
interface ToastItem { id: number; kind: ToastKind; text: string }
type SavedStatus = SavedItem['status'];
export type Theme = 'dark' | 'light';

interface RegTarget { id: string; title: string; registration: { platform: string | null } }
interface DemoRegistration { title: string; platform: string | null; url: string }

interface AppValue {
  user: User | null;
  authReady: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
  setUser: (u: User) => void;
  saved: ReadonlyMap<string, SavedStatus>;
  savedReady: boolean;
  isSaved: (id: string) => boolean;
  toggleSave: (e: Pick<EventCardData, 'id' | 'title'>) => Promise<void>;
  reloadSaved: () => Promise<SavedItem[]>;
  startRegistration: (e: RegTarget) => Promise<void>;
  markRegistrationStarted: (id: string) => void;
  requireLogin: (message?: string) => boolean;
  toast: (text: string, kind?: ToastKind) => void;
  theme: Theme;
  toggleTheme: () => void;
  demoDismissed: boolean;
  dismissDemo: () => void;
}

const Ctx = createContext<AppValue | null>(null);
export const useApp = (): AppValue => {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be used inside AppProvider');
  return v;
};

const TOKEN_KEY = 'happenmuj.token';
const THEME_KEY = 'happenmuj.theme';

function systemTheme(): Theme {
  try { return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; } catch { return 'dark'; }
}
function initialTheme(): Theme {
  const saved = storageGet(THEME_KEY);
  const attr = document.documentElement.getAttribute('data-theme');
  const t = saved === 'light' || saved === 'dark' ? saved : attr === 'light' || attr === 'dark' ? attr : systemTheme();
  return t;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [saved, setSaved] = useState<Map<string, SavedStatus>>(new Map());
  const [savedReady, setSavedReady] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [demoDismissed, setDemoDismissed] = useState(() => storageGet('happenmuj.demo-dismissed') === '1');
  const [demoReg, setDemoReg] = useState<DemoRegistration | null>(null);
  const toastId = useRef(0);
  const savedRef = useRef(saved);
  savedRef.current = saved;

  const toast = useCallback((text: string, kind: ToastKind = 'info') => {
    const id = ++toastId.current;
    setToasts((t) => [...t.slice(-2), { id, kind, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  // theme: an explicit attribute wins over the system setting in CSS
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); }, [theme]);
  // follow the host if something else changes the attribute (for example an embedding viewer)
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => {
      const v = el.getAttribute('data-theme');
      if (v === 'light' || v === 'dark') setTheme((t) => (t === v ? t : v));
    });
    obs.observe(el, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === 'dark' ? 'light' : 'dark';
      storageSet(THEME_KEY, next);
      return next;
    });
  }, []);

  const reloadSaved = useCallback(async () => {
    const list = await api.savedEvents();
    setSaved(new Map(list.map((s) => [s.event.id, s.status])));
    setSavedReady(true);
    return list;
  }, []);

  // restore a session from the stored token
  useEffect(() => {
    const token = storageGet(TOKEN_KEY);
    if (!token) { setAuthReady(true); return; }
    api.setToken(token);
    api.me().then(
      (u) => { setUserState(u); reloadSaved().catch(() => setSavedReady(true)); },
      () => { api.setToken(null); storageSet(TOKEN_KEY, null); },
    ).finally(() => setAuthReady(true));
  }, [reloadSaved]);

  const afterAuth = useCallback(async (token: string, u: User) => {
    storageSet(TOKEN_KEY, token);
    setUserState(u);
    await reloadSaved().catch(() => setSavedReady(true));
    return u;
  }, [reloadSaved]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.login(email, password);
    return afterAuth(r.token, r.user);
  }, [afterAuth]);
  const register = useCallback(async (input: RegisterInput) => {
    const r = await api.register(input);
    return afterAuth(r.token, r.user);
  }, [afterAuth]);
  const logout = useCallback(() => {
    api.setToken(null);
    storageSet(TOKEN_KEY, null);
    setUserState(null);
    setSaved(new Map());
    setSavedReady(false);
    toast('You have signed out.', 'info');
    navigate('/');
  }, [toast]);

  const requireLogin = useCallback((message = 'Sign in to continue.') => {
    if (user) return true;
    toast(message, 'info');
    const here = currentPath();
    navigate(`/login${qs({ next: here.startsWith('/login') ? undefined : here })}`);
    return false;
  }, [user, toast]);

  const toggleSave = useCallback(async (e: Pick<EventCardData, 'id' | 'title'>) => {
    if (!requireLogin('Sign in to save events.')) return;
    const was = savedRef.current.has(e.id);
    const optimistic = new Map(savedRef.current);
    if (was) optimistic.delete(e.id); else optimistic.set(e.id, 'saved');
    setSaved(optimistic);
    try {
      if (was) await api.unsaveEvent(e.id); else await api.saveEvent(e.id);
      toast(was ? `Removed ${e.title} from your events.` : `Saved ${e.title}.`, 'ok');
    } catch (err) {
      const rollback = new Map(savedRef.current);
      if (was) rollback.set(e.id, 'saved'); else rollback.delete(e.id);
      setSaved(rollback);
      toast(err instanceof Error ? err.message : 'Could not update your saved events.', 'error');
    }
  }, [requireLogin, toast]);

  const markRegistrationStarted = useCallback((id: string) => {
    setSaved((m) => (m.has(id) ? new Map(m).set(id, 'registration_initiated') : m));
  }, []);

  // Registration always happens on the organiser's own page. We only record the click.
  const startRegistration = useCallback(async (e: RegTarget) => {
    const popup = isDemo ? null : window.open('about:blank', '_blank');
    try {
      const { url } = await api.registrationClick(e.id);
      markRegistrationStarted(e.id);
      const safe = safeUrl(url);
      if (!safe) throw new Error('This registration link is not valid.');
      if (isDemo) {
        setDemoReg({ title: e.title, platform: e.registration.platform, url: safe });
      } else if (popup) {
        popup.opener = null;
        popup.location.href = safe;
      } else {
        window.open(safe, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      popup?.close();
      toast(err instanceof Error ? err.message : 'Could not open registration.', 'error');
    }
  }, [markRegistrationStarted, toast]);

  const dismissDemo = useCallback(() => { setDemoDismissed(true); storageSet('happenmuj.demo-dismissed', '1'); }, []);

  const value = useMemo<AppValue>(() => ({
    user, authReady, login, register, logout, setUser: setUserState,
    saved, savedReady, isSaved: (id) => saved.has(id), toggleSave, reloadSaved, startRegistration, markRegistrationStarted,
    requireLogin, toast, theme, toggleTheme, demoDismissed, dismissDemo,
  }), [user, authReady, login, register, logout, saved, savedReady, toggleSave, reloadSaved, startRegistration, markRegistrationStarted, requireLogin, toast, theme, toggleTheme, demoDismissed, dismissDemo]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.kind}`}>{t.text}</div>
        ))}
      </div>
      {demoReg && <DemoRegistrationDialog info={demoReg} onClose={() => setDemoReg(null)} />}
    </Ctx.Provider>
  );
}

function DemoRegistrationDialog({ info, onClose }: { info: DemoRegistration; onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="demo-reg-title">
        <h2 id="demo-reg-title" className="dialog__title">Registration opens on the organiser&rsquo;s page</h2>
        <p>
          With live data, this button opens the registration page for <strong>{info.title}</strong> in a new tab. You are looking at sample data,
          so the link below is not active.
        </p>
        <p className="dialog__url">{info.url}</p>
        <p className="muted">HappenMUJ records the click so clubs can see interest. It does not know whether you finish the form.</p>
        <div className="dialog__actions">
          <button ref={ref} type="button" className="btn btn--primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  );
}
