import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from '../src/App';
import { AppProvider } from '../src/state/AppContext';
import { navigate } from '../src/lib/router';
import { createHttpApi } from '../src/lib/api/http';
import { createMockApi } from '../src/lib/api/mock';

const opts = { timeout: 12000 };

describe('sign-up form (sample-data mode)', () => {
  it('asks for a name, a PERSONAL email and a password, and does not ask for a registration number', async () => {
    navigate('/login');
    render(<AppProvider><App /></AppProvider>);
    fireEvent.click(await screen.findByRole('tab', { name: 'Create account' }, opts));
    expect(screen.getByLabelText('Name')).toBeTruthy();
    expect(screen.getByLabelText('Personal email')).toBeTruthy();
    expect(screen.getByLabelText('Password')).toBeTruthy();
    expect(screen.queryByLabelText(/registration/i)).toBeNull();
    expect(document.body.textContent).toMatch(/college Outlook address is not needed/);
  });

  it('the sign-in tab keeps the plain "Email" label, and Google is hidden when the server has no Google client id', async () => {
    navigate('/login');
    render(<AppProvider><App /></AppProvider>);
    expect(await screen.findByLabelText('Email', {}, opts)).toBeTruthy();
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Use' }).length).toBe(3), opts); // demo accounts
    expect(screen.queryByRole('group', { name: 'Continue with Google' })).toBeNull();
  });

  it('creating an account in sample mode signs you in', async () => {
    navigate('/login');
    render(<AppProvider><App /></AppProvider>);
    fireEvent.click(await screen.findByRole('tab', { name: 'Create account' }, opts));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Test Student' } });
    fireEvent.change(screen.getByLabelText('Personal email'), { target: { value: 'test.student@gmail.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'longenough1' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Create account' }).find((b) => b.getAttribute('type') === 'submit')!);
    await waitFor(() => expect(screen.getByRole('button', { name: /Account menu/ })).toBeTruthy(), opts);
  });
});

describe('Google sign-in in the API adapters', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('the sample-data adapter has no Google and says so', async () => {
    const mock = createMockApi();
    expect(await mock.authConfig()).toEqual({ google_client_id: null });
    await expect(mock.googleLogin('x')).rejects.toMatchObject({ code: 'google_not_configured' });
  });

  it('the HTTP adapter reads /auth/config and exchanges the Google credential at /auth/google', async () => {
    const user = { id: 'u1', name: 'G', email: 'g@gmail.com', role: 'student', interests: [], preferred_categories: [], followed_club_ids: [], managed_club_ids: [], email_verified: true, auth_providers: ['google'] };
    const calls: { url: string; method: string; body?: string; auth?: string }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, method: init.method ?? 'GET', body: init.body as string | undefined, auth: (init.headers as Record<string, string>).Authorization });
      const path = new URL(url).pathname;
      const body = path.endsWith('/auth/config') ? { google_client_id: 'abc.apps.googleusercontent.com' }
        : path.endsWith('/auth/google') ? { access_token: 'tok-google', user }
        : user;
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    const api = createHttpApi('/api');
    expect(await api.authConfig()).toEqual({ google_client_id: 'abc.apps.googleusercontent.com' });
    const r = await api.googleLogin('the-google-id-token');
    expect(r.token).toBe('tok-google');
    expect(r.user).toMatchObject({ email: 'g@gmail.com', email_verified: true, auth_providers: ['google'] });
    const post = calls.find((c) => c.url.endsWith('/auth/google'))!;
    expect(post.method).toBe('POST');
    expect(JSON.parse(post.body!)).toEqual({ credential: 'the-google-id-token' });
    expect(calls.at(-1)!.auth).toBe('Bearer tok-google'); // the follow-up /auth/me is authenticated with the new token
  });
});
