import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { CATEGORIES, INTEREST_SUGGESTIONS } from '../lib/constants';
import { useAsync, useTitle } from '../lib/hooks';
import type { Category } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Chip } from '../components/Filters';
import { Button, ErrorState, Field, PageHead } from '../components/ui';

export function ProfilePage() {
  useTitle('Profile');
  const { user, authReady, requireLogin, setUser, toast } = useApp();
  const clubs = useAsync(() => api.clubs(), []);
  const [name, setName] = useState(user?.name ?? '');
  const [interests, setInterests] = useState<string[]>(user?.interests ?? []);
  const [cats, setCats] = useState<Category[]>(user?.preferred_categories ?? []);
  const [custom, setCustom] = useState('');
  const [busy, setBusy] = useState(false);
  const [nameErr, setNameErr] = useState('');

  useEffect(() => { if (authReady && !user) requireLogin('Sign in to see your profile.'); }, [authReady, user, requireLogin]);
  useEffect(() => { if (user) { setName(user.name); setInterests(user.interests); setCats(user.preferred_categories); } }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user) return <div className="container page"><PageHead title="Profile" /></div>;

  const save = async () => {
    if (name.trim().length < 2) { setNameErr('Enter your name.'); return; }
    setNameErr(''); setBusy(true);
    try { setUser(await api.updateProfile({ name: name.trim(), interests, preferred_categories: cats })); toast('Profile saved.', 'ok'); } catch (e) { toast(e instanceof Error ? e.message : 'Could not save.', 'error'); } finally { setBusy(false); }
  };
  const toggleFollow = async (id: string, on: boolean) => {
    try { setUser(on ? await api.unfollowClub(id) : await api.followClub(id)); } catch (e) { toast(e instanceof Error ? e.message : 'Could not update.', 'error'); }
  };
  const addCustom = () => {
    const v = custom.trim();
    if (v && !interests.some((i) => i.toLowerCase() === v.toLowerCase())) setInterests([...interests, v]);
    setCustom('');
  };
  const all = [...INTEREST_SUGGESTIONS, ...interests.filter((i) => !INTEREST_SUGGESTIONS.includes(i))];

  return (
    <div className="container page page--narrow">
      <PageHead title="Profile" sub={`${user.email} · ${user.role.replace('_', ' ')}`} />
      <div className="stack">
        <section className="panel form">
          <h2 className="panel__title">About you</h2>
          <Field id="p-name" label="Name" error={nameErr}><input id="p-name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!nameErr} /></Field>
        </section>
        <section className="panel">
          <h2 className="panel__title">Interests</h2>
          <p className="muted">These shape the &ldquo;Suggested for you&rdquo; row on the home page.</p>
          <div className="chips">{all.map((i) => <Chip key={i} on={interests.includes(i)} onClick={() => setInterests((l) => (l.includes(i) ? l.filter((x) => x !== i) : [...l, i]))}>{i}</Chip>)}</div>
          <div className="inline-form">
            <label className="sr" htmlFor="p-custom">Add your own interest</label>
            <input id="p-custom" value={custom} placeholder="Add your own" maxLength={40} onChange={(e) => setCustom(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustom(); } }} />
            <Button onClick={addCustom}>Add</Button>
          </div>
        </section>
        <section className="panel">
          <h2 className="panel__title">Favourite categories</h2>
          <div className="chips">{CATEGORIES.map((c) => <Chip key={c.id} on={cats.includes(c.id)} onClick={() => setCats((l) => (l.includes(c.id) ? l.filter((x) => x !== c.id) : [...l, c.id]))}>{c.label}</Chip>)}</div>
        </section>
        <div><Button variant="primary" size="lg" loading={busy} onClick={save}>Save changes</Button></div>
        <section className="panel">
          <h2 className="panel__title">Clubs you follow</h2>
          {clubs.error ? <ErrorState error={clubs.error} onRetry={clubs.reload} /> : (
            <ul className="demo-list">
              {(clubs.data ?? []).map((c) => {
                const on = user.followed_club_ids.includes(c.id);
                return <li key={c.id}><div><strong>{c.name}</strong><span className="muted">{c.description}</span></div><Button size="sm" aria-pressed={on} onClick={() => toggleFollow(c.id, on)}>{on ? 'Following' : 'Follow'}</Button></li>;
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
