import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../../src/App';
import { AppProvider } from '../../src/state/AppContext';
import { navigate } from '../../src/lib/router';
import { api } from '../../src/lib/api';

// Walks the real UI against the real backend. The API itself is the oracle for what the UI should show.
const API = (import.meta.env.VITE_API_BASE_URL as string).replace(/\/$/, '');
const opts = { timeout: 15000 };
const get = async (path: string, token?: string) =>
  (await fetch(API + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })).json();
const apiLogin = async (email: string) =>
  (await (await fetch(API + '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password: 'demo1234' }) })).json()).access_token as string;
const mount = () => render(<AppProvider><App /></AppProvider>);

async function signIn(email: string) {
  navigate('/login');
  mount();
  fireEvent.change(await screen.findByLabelText('Email', {}, opts), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo1234' } });
  const submit = screen.getAllByRole('button', { name: 'Sign in' }).find((b) => b.getAttribute('type') === 'submit')!;
  fireEvent.click(submit);
  await waitFor(() => expect(screen.getByRole('button', { name: /Account menu/ })).toBeTruthy(), opts);
}
const go = async (path: string) => { await act(async () => { navigate(path); }); };
const istLocal = (daysAhead: number, hh: number) => {
  const d = new Date(Date.now() + daysAhead * 864e5 + 330 * 60e3); // shift to IST wall-clock, then read UTC fields
  return `${d.toISOString().slice(0, 10)}T${String(hh).padStart(2, '0')}:00`;
};

beforeEach(() => {
  cleanup();
  localStorage.clear();
  api.setToken(null);
  navigate('/');
});

describe('real backend, real UI', () => {
  it('uses the HTTP adapter', () => {
    expect(api.mode).toBe('http');
  });

  it('home: all eight sections, ten ranked cards, a real featured event', async () => {
    mount();
    await waitFor(() => expect(screen.getAllByRole('article').length).toBeGreaterThan(10), opts);
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent ?? '');
    let last = -1;
    for (const t of ['Suggested', 'Top 10', 'Next 7 days', 'Tomorrow', 'Browse by category', 'Browse by club', 'All upcoming']) {
      const i = titles.findIndex((x) => x.includes(t));
      expect(i, `section "${t}" missing`).toBeGreaterThan(last);
      last = i;
    }
    const top = screen.getByRole('list', { name: 'Top 10 events' });
    await waitFor(() => expect(within(top).getAllByRole('article')).toHaveLength(10), opts);
    expect(within(top).getByLabelText('Number 10')).toBeTruthy();
    const apiTop = (await get('/home/top-events')).items.map((e: { title: string }) => e.title);
    const shown = within(top).getAllByRole('article').map((a) => a.textContent ?? '');
    apiTop.forEach((t: string, i: number) => expect(shown[i], `rank ${i + 1}`).toContain(t));
    expect(document.body.textContent).toContain((await get('/home/featured')).title);
    expect(document.body.textContent).toContain('not an official endorsement');
  });

  it('home filters: (cat OR cat) AND (club) and the count matches the API', async () => {
    navigate('/');
    mount();
    fireEvent.click(await screen.findByRole('button', { name: /^Technical/ }, opts));
    fireEvent.click(screen.getByRole('button', { name: /^Cultural/ }));
    fireEvent.click(screen.getByRole('button', { name: /^ACM/ }));
    const acm = (await get('/clubs/acm')).id;
    const expected = (await get(`/events?category=technical&category=cultural&club=${acm}&page_size=50`)).total;
    expect(expected).toBeGreaterThan(0);
    await waitFor(() => expect(document.body.textContent).toMatch(new RegExp(`${expected} ${expected === 1 ? 'event' : 'events'}`)), opts);
    // only the filtered grid ("All upcoming events"), not the carousels above it
    const grid = (await screen.findByRole('heading', { level: 2, name: /All upcoming events/ }, opts)).closest('section') as HTMLElement;
    const cards = await within(grid).findAllByRole('article', {}, opts);
    expect(cards).toHaveLength(Math.min(expected, cards.length));
    cards.forEach((c) => expect(c.textContent).toMatch(/ACM/));
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
    await waitFor(() => expect(document.body.textContent).not.toMatch(/match your filters/), opts);
  });

  it('event page: details render, fee is never assumed free, cancelled events stay readable', async () => {
    const adminTok = await apiLogin('admin@muj-demo.edu');
    const unspecified = (await get('/events?page_size=50')).items.find((e: { fee: { type: string } }) => e.fee.type === 'not_specified');
    navigate(`/events/${unspecified.id}`);
    mount();
    await waitFor(() => expect(screen.getAllByText(unspecified.title).length).toBeGreaterThan(0), opts);
    expect(document.body.textContent).toContain('Fee not specified');
    expect(document.body.textContent).not.toMatch(/\bFree\b/);
    cleanup();
    const cancelled = (await get('/admin/events?status=cancelled', adminTok)).items[0];
    navigate(`/events/${cancelled.id}`);
    mount();
    await waitFor(() => expect(screen.getAllByText(cancelled.title).length).toBeGreaterThan(0), opts);
    expect(document.body.textContent).toMatch(/cancel/i);
    expect(document.body.textContent).toContain(cancelled.cancel_reason);
  });

  it('student: sign in, save, see it under My events, the calendar flags the clash, unsave', async () => {
    await signIn('student@muj-demo.edu');
    const me = await get('/auth/me', await apiLogin('student@muj-demo.edu'));
    expect(me.interests).toContain('ai');
    await go('/my-events');
    await waitFor(() => expect(document.body.textContent).toMatch(/time clash/), opts);
    await go('/explore');
    const stuTok = await apiLogin('student@muj-demo.edu');
    const before = (await get('/saved-events', stuTok)).total;
    const saveBtn = (await screen.findAllByRole('button', { name: /^Save /i }, opts))[0];
    const title = saveBtn.getAttribute('aria-label')!.replace(/^Save /, '');
    fireEvent.click(saveBtn);
    await waitFor(() => expect(screen.getByRole('button', { name: `Remove ${title} from saved events` })).toBeTruthy(), opts);
    await waitFor(async () => expect((await get('/saved-events', stuTok)).total).toBe(before + 1), opts);
    fireEvent.click(screen.getByRole('button', { name: `Remove ${title} from saved events` }));
    await waitFor(() => expect(screen.getByRole('button', { name: `Save ${title}` })).toBeTruthy(), opts);
    await waitFor(async () => expect((await get('/saved-events', stuTok)).total).toBe(before), opts);
    await go('/calendar');
    await waitFor(() => expect(screen.getAllByText(/Calendar/).length).toBeGreaterThan(0), opts);
  });

  it('registration: the button opens the organiser link and records a click, never "registered"', async () => {
    await signIn('student@muj-demo.edu');
    const stuTok = await apiLogin('student@muj-demo.edu');
    const target = (await get('/events?page_size=50', stuTok)).items.find(
      (e: { registration: { required: boolean }; registration_open: boolean; is_saved: boolean }) => e.registration.required && e.registration_open && !e.is_saved,
    );
    const clicksBefore = (await get(`/events/${target.id}`)).stats.registration_clicks;
    // The app opens a blank tab first (popup-blocker workaround), then sets its location once the click is recorded.
    const popup = { opener: {}, location: { href: '' } };
    const open = vi.spyOn(window, 'open').mockImplementation(() => popup as unknown as Window);
    await go(`/events/${target.id}`);
    await waitFor(() => expect(screen.getAllByText(target.title).length).toBeGreaterThan(0), opts);
    const reg = (await screen.findAllByRole('button', { name: /register/i }, opts))[0];
    fireEvent.click(reg);
    await waitFor(async () => expect((await get(`/events/${target.id}`)).stats.registration_clicks).toBe(clicksBefore + 1), opts);
    await waitFor(() => expect(popup.location.href).toMatch(/^https?:\/\//), opts);
    expect(open).toHaveBeenCalled();
    expect(popup.opener).toBeNull(); // noopener: the organiser's page cannot reach back into ours
    expect(document.body.textContent).not.toMatch(/you are registered|you.re registered|registration confirmed/i);
    open.mockRestore();
  });

  it('community: real authors, a thread, and a new comment lands in the database', async () => {
    await signIn('student@muj-demo.edu');
    await go('/community');
    const posts = (await get('/posts')).items;
    await waitFor(() => expect(document.body.textContent).toContain(posts[0].title), opts);
    expect(document.body.textContent).toContain(posts[0].author.name);
    expect(document.body.textContent).not.toMatch(/\bStudent\b.*\bStudent\b.*\bStudent\b/);
    await go(`/community/${posts.find((p: { comment_count: number }) => p.comment_count > 0).id}`);
    const withComments = posts.find((p: { comment_count: number }) => p.comment_count > 0);
    await waitFor(() => expect(screen.getByRole('heading', { name: withComments.title })).toBeTruthy(), opts);
    const box = await screen.findByPlaceholderText('Add a comment', {}, opts);
    const text = `Live test comment ${Date.now()}`;
    fireEvent.change(box, { target: { value: text } });
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }));
    // A controlled textarea mirrors what was typed into its text content, so look at the rendered comment itself.
    await waitFor(() => expect(Array.from(document.querySelectorAll('.comment__body')).some((el) => el.textContent === text)).toBe(true), opts);
    await waitFor(async () => expect(JSON.stringify((await get(`/posts/${withComments.id}/comments?page_size=50`)).items)).toContain(text), opts);
  });

  it('club admin creates an event; the platform admin approves it; it goes public', async () => {
    const title = `Live E2E Workshop ${Date.now()}`;
    await signIn('acm@muj-demo.edu');
    await go('/manage/new');
    fireEvent.change(await screen.findByLabelText('Title', {}, opts), { target: { value: title } });
    fireEvent.change(screen.getByLabelText('One-line summary'), { target: { value: 'Created end to end by the live test.' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'A workshop created through the real UI against the real API.' } });
    fireEvent.change(screen.getByLabelText('Event type'), { target: { value: 'workshop' } });
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: istLocal(12, 15) } });
    fireEvent.change(screen.getByLabelText('Ends'), { target: { value: istLocal(12, 17) } });
    fireEvent.change(screen.getByLabelText('Venue'), { target: { value: 'AB3 Seminar Hall' } });
    fireEvent.change(screen.getByLabelText('Fee'), { target: { value: 'fixed' } });
    fireEvent.change(await screen.findByLabelText('Amount in ₹'), { target: { value: '199' } });
    fireEvent.change(screen.getByLabelText('Registration link'), { target: { value: 'https://forms.example.com/live' } });
    fireEvent.change(screen.getByLabelText('Speaker'), { target: { value: 'Dr Live Test' } });
    fireEvent.change(screen.getByLabelText('Topics covered'), { target: { value: 'End to end\nTesting' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and send for review' }));
    const acmTok = await apiLogin('acm@muj-demo.edu');
    let created: { id: string; status: string; details: Record<string, unknown>; fee: { display: string } } | undefined;
    await waitFor(async () => {
      created = (await get('/events/mine?page_size=50', acmTok)).items.find((e: { title: string }) => e.title === title);
      expect(created?.status).toBe('pending_review');
    }, opts);
    expect(created!.details).toMatchObject({ speaker: { name: 'Dr Live Test' }, topics: ['End to end', 'Testing'] });
    expect(created!.fee.display).toBe('₹199');
    expect((await get('/events?q=Live+E2E&page_size=50')).items.some((e: { title: string }) => e.title === title)).toBe(false); // not public yet

    cleanup();
    localStorage.clear();
    api.setToken(null);
    await signIn('admin@muj-demo.edu');
    await go('/admin');
    await waitFor(() => expect(screen.getAllByText(title).length).toBeGreaterThan(0), opts);
    const row = screen.getAllByText(title)[0].closest('li, article, div.row') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Approve' }));
    await waitFor(async () => {
      expect((await get('/events?page_size=50')).items.some((e: { title: string }) => e.title === title)).toBe(true);
    }, opts);
    const pub = (await get('/events?page_size=50')).items.find((e: { title: string }) => e.title === title);
    expect(pub.status).toBe('published');
  });
});
