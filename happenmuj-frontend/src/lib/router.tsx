import { useMemo, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react';

// A tiny hash router. State lives in memory first and the URL hash second, so navigation still works
// in places where writing to location.hash is blocked (for example a sandboxed preview frame).

function readHash(): string {
  try {
    const h = window.location.hash;
    return h.startsWith('#/') ? h.slice(1) : '/';
  } catch {
    return '/';
  }
}

let current = typeof window === 'undefined' ? '/' : readHash();
const listeners = new Set<() => void>();
const pathOf = (s: string) => s.split('?')[0];

function setCurrent(next: string) {
  if (next === current) return;
  const pathChanged = pathOf(next) !== pathOf(current);
  current = next;
  if (pathChanged) {
    try { window.scrollTo(0, 0); } catch { /* ignore */ }
  }
  listeners.forEach((l) => l());
}

if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => setCurrent(readHash()));
}

export function navigate(to: string, opts: { replace?: boolean } = {}): void {
  setCurrent(to);
  try {
    if (opts.replace) window.location.replace(`#${to}`);
    else window.location.hash = to;
  } catch { /* the in-memory state above is already updated */ }
}

export const currentPath = (): string => current;

export interface Loc { path: string; query: URLSearchParams; raw: string }

export function useLocation(): Loc {
  const raw = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => current,
    () => '/',
  );
  return useMemo(() => {
    const [path, qs = ''] = raw.split('?');
    return { path: path || '/', query: new URLSearchParams(qs), raw };
  }, [raw]);
}

export function qs(params: Record<string, string | string[] | number | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : '';
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string };

export function Link({ to, onClick, children, ...rest }: LinkProps) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (rest.target && rest.target !== '_self') return;
    e.preventDefault();
    navigate(to);
  };
  return <a href={`#${to}`} onClick={handle} {...rest}>{children}</a>;
}

export type Route =
  | { name: 'home' }
  | { name: 'explore' }
  | { name: 'event'; id: string }
  | { name: 'my-events' }
  | { name: 'calendar' }
  | { name: 'community' }
  | { name: 'post'; id: string }
  | { name: 'login' }
  | { name: 'profile' }
  | { name: 'manage' }
  | { name: 'manage-new' }
  | { name: 'manage-edit'; id: string }
  | { name: 'admin' }
  | { name: 'not-found' };

export function matchRoute(path: string): Route {
  const p = path.replace(/\/+$/, '') || '/';
  if (p === '/') return { name: 'home' };
  if (p === '/explore') return { name: 'explore' };
  if (p === '/my-events') return { name: 'my-events' };
  if (p === '/calendar') return { name: 'calendar' };
  if (p === '/community') return { name: 'community' };
  if (p === '/login') return { name: 'login' };
  if (p === '/profile') return { name: 'profile' };
  if (p === '/manage') return { name: 'manage' };
  if (p === '/manage/new') return { name: 'manage-new' };
  if (p === '/admin') return { name: 'admin' };
  let m = /^\/events\/([^/]+)$/.exec(p);
  if (m) return { name: 'event', id: decodeURIComponent(m[1]) };
  m = /^\/community\/([^/]+)$/.exec(p);
  if (m) return { name: 'post', id: decodeURIComponent(m[1]) };
  m = /^\/manage\/([^/]+)\/edit$/.exec(p);
  if (m) return { name: 'manage-edit', id: decodeURIComponent(m[1]) };
  return { name: 'not-found' };
}
