import { useState, type FormEvent } from 'react';
import { isDemo } from '../lib/api';
import { INTEREST_SUGGESTIONS } from '../lib/constants';
import { useTitle } from '../lib/hooks';
import { navigate, useLocation } from '../lib/router';
import { useApp } from '../state/AppContext';
import { Button, Field, Tabs } from '../components/ui';

const DEMOS = [
  { label: 'Student', email: 'student@muj-demo.edu', note: 'Ananya Verma, has saved events' },
  { label: 'Club admin', email: 'acm@muj-demo.edu', note: 'Runs the ACM chapter' },
  { label: 'Platform admin', email: 'admin@muj-demo.edu', note: 'Reviews events and clubs' },
];

export function LoginPage() {
  useTitle('Sign in');
  const { login, register, user } = useApp();
  const { query } = useLocation();
  const next = query.get('next');
  const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [interests, setInterests] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  const go = async (fn: () => Promise<unknown>) => {
    setBusy(true); setFormError('');
    try { await fn(); navigate(safeNext, { replace: true }); } catch (e) { setFormError(e instanceof Error ? e.message : 'Something went wrong. Try again.'); } finally { setBusy(false); }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (mode === 'up' && name.trim().length < 2) errs.name = 'Enter your name.';
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) errs.email = 'Enter a valid email address.';
    if (password.length < (mode === 'up' ? 8 : 1)) errs.password = mode === 'up' ? 'Use at least 8 characters.' : 'Enter your password.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    go(() => (mode === 'in' ? login(email.trim(), password) : register({ name: name.trim(), email: email.trim(), password, interests })));
  };

  if (user) {
    return (
      <div className="container page page--narrow">
        <div className="panel"><h1 className="panel__title">You are signed in as {user.name}</h1><Button variant="primary" onClick={() => navigate(safeNext)}>Continue</Button></div>
      </div>
    );
  }

  return (
    <div className="container page auth">
      <div className="auth__card panel">
        <h1 className="auth__title">{mode === 'in' ? 'Sign in' : 'Create your account'}</h1>
        <Tabs label="Account" value={mode} onChange={(m) => { setMode(m); setErrors({}); setFormError(''); }} tabs={[{ id: 'in', label: 'Sign in' }, { id: 'up', label: 'Create account' }]} />
        <form onSubmit={submit} noValidate className="form">
          {mode === 'up' && <Field id="a-name" label="Name" error={errors.name}><input id="a-name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!errors.name} /></Field>}
          <Field id="a-email" label="Email" error={errors.email}><input id="a-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!errors.email} /></Field>
          <Field id="a-pass" label="Password" error={errors.password} hint={mode === 'up' ? 'At least 8 characters.' : undefined}><input id="a-pass" type="password" autoComplete={mode === 'in' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!errors.password} /></Field>
          {mode === 'up' && (
            <fieldset className="field">
              <legend className="field__label">What are you into? <span className="muted">(optional, used for suggestions)</span></legend>
              <div className="chips">
                {INTEREST_SUGGESTIONS.map((i) => {
                  const on = interests.includes(i);
                  return <button key={i} type="button" className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={() => setInterests((l) => (on ? l.filter((x) => x !== i) : [...l, i]))}>{i}</button>;
                })}
              </div>
            </fieldset>
          )}
          {formError && <p className="field__error" role="alert">{formError}</p>}
          <Button type="submit" variant="primary" size="lg" block loading={busy}>{mode === 'in' ? 'Sign in' : 'Create account'}</Button>
        </form>
      </div>
      {isDemo && (
        <aside className="auth__demo panel" aria-label="Demo accounts">
          <h2 className="panel__title">Try a demo account</h2>
          <p className="muted">This preview uses sample data. Pick a role to see what it can do.</p>
          <ul className="demo-list">
            {DEMOS.map((d) => (
              <li key={d.email}>
                <div><strong>{d.label}</strong><span className="muted">{d.note}</span></div>
                <Button size="sm" disabled={busy} onClick={() => go(() => login(d.email, 'demo1234'))}>Use</Button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
