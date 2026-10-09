import { useRef, useState, type FormEvent } from 'react';
import { Link, navigate, qs, useLocation } from '../lib/router';
import { useOutside } from '../lib/hooks';
import { useApp } from '../state/AppContext';
import { Avatar } from './ui';
import { Icon, type IconName } from './Icon';

const NAV: { to: string; label: string; match: (p: string) => boolean }[] = [
  { to: '/', label: 'Home', match: (p) => p === '/' },
  { to: '/explore', label: 'Explore Events', match: (p) => p.startsWith('/explore') || p.startsWith('/events') },
  { to: '/my-events', label: 'My Events', match: (p) => p === '/my-events' },
  { to: '/calendar', label: 'Calendar', match: (p) => p === '/calendar' },
  { to: '/community', label: 'MUJ-COMMUNITY', match: (p) => p.startsWith('/community') },
];

export function Header() {
  const { path, query } = useLocation();
  const { user, logout, theme, toggleTheme } = useApp();
  const [searchOpen, setSearchOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useOutside(menuRef, () => setMenu(false), menu);

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const q = String(new FormData(e.currentTarget).get('q') ?? '').trim();
    navigate(`/explore${qs({ q })}`);
    setSearchOpen(false);
  };

  return (
    <header className="header">
      <div className="header__bar">
        <Link to="/" className="brand" aria-label="HappenMUJ home">Happen<span>MUJ</span></Link>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className="nav__link" aria-current={n.match(path) ? 'page' : undefined}>{n.label}</Link>
          ))}
        </nav>
        <div className="header__tools">
          <form className={`search${searchOpen ? ' search--open' : ''}`} role="search" onSubmit={submit}>
            <label className="sr" htmlFor="site-search">Search events</label>
            <input id="site-search" name="q" type="search" placeholder="Search events, clubs, tags" defaultValue={path === '/explore' ? query.get('q') ?? '' : ''} autoComplete="off" />
            <button type="submit" className="icon-btn" aria-label="Search" onClick={(e) => { if (!searchOpen && window.matchMedia('(max-width: 960px)').matches) { e.preventDefault(); setSearchOpen(true); document.getElementById('site-search')?.focus(); } }}>
              <Icon name="search" />
            </button>
          </form>
          <button type="button" className="icon-btn" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>
          {user ? (
            <div className="menu" ref={menuRef}>
              <button type="button" className="menu__btn" aria-haspopup="true" aria-expanded={menu} onClick={() => setMenu((v) => !v)} aria-label="Account menu">
                <Avatar name={user.name} />
              </button>
              {menu && (
                <div className="menu__panel" role="menu" onClick={() => setMenu(false)}>
                  <p className="menu__who"><strong>{user.name}</strong><span>{user.email}</span></p>
                  <Link role="menuitem" to="/profile">Profile</Link>
                  {user.role !== 'student' && <Link role="menuitem" to="/manage">Manage events</Link>}
                  {user.role === 'platform_admin' && <Link role="menuitem" to="/admin">Admin</Link>}
                  <button role="menuitem" type="button" onClick={logout}>Sign out</button>
                </div>
              )}
            </div>
          ) : (
            <Link to="/login" className="btn btn--primary btn--sm">Sign in</Link>
          )}
        </div>
      </div>
    </header>
  );
}

const TABS: { to: string; label: string; icon: IconName; match: (p: string) => boolean }[] = [
  { to: '/', label: 'Home', icon: 'home', match: (p) => p === '/' },
  { to: '/explore', label: 'Explore', icon: 'compass', match: (p) => p.startsWith('/explore') || p.startsWith('/events') },
  { to: '/my-events', label: 'Saved', icon: 'bookmark', match: (p) => p === '/my-events' },
  { to: '/calendar', label: 'Calendar', icon: 'calendar', match: (p) => p === '/calendar' },
  { to: '/community', label: 'Community', icon: 'message', match: (p) => p.startsWith('/community') },
];

export function TabBar() {
  const { path } = useLocation();
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map((t) => (
        <Link key={t.to} to={t.to} className="tabbar__link" aria-current={t.match(path) ? 'page' : undefined}>
          <Icon name={t.icon} size={22} />
          <span>{t.label}</span>
        </Link>
      ))}
    </nav>
  );
}
