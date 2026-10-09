import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../src/App';
import { AppProvider } from '../src/state/AppContext';
import { navigate } from '../src/lib/router';

const mount = () => render(<AppProvider><App /></AppProvider>);
const opts = { timeout: 4000 };

describe('app smoke', () => {
  it('home renders the eight sections in order with ten ranked cards', async () => {
    navigate('/');
    mount();
    await waitFor(() => expect(screen.getAllByRole('article').length).toBeGreaterThan(10), opts);
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent ?? '');
    const order = ['Suggested', 'Top 10', 'Next 7 days', 'Tomorrow', 'Browse by category', 'Browse by club', 'All upcoming'];
    let last = -1;
    for (const t of order) {
      const i = titles.findIndex((x) => x.includes(t));
      expect(i, t).toBeGreaterThan(last);
      last = i;
    }
    const top = screen.getByRole('list', { name: 'Top 10 events' });
    await waitFor(() => expect(within(top).getAllByRole('article')).toHaveLength(10), opts);
    expect(within(top).getByLabelText('Number 10')).toBeTruthy();
  });

  it('category chips filter the catalogue and can be cleared', async () => {
    navigate('/');
    mount();
    const chip = await screen.findByRole('button', { name: 'Sports' }, opts);
    fireEvent.click(chip);
    await waitFor(() => expect(screen.getByText(/match your filters/)).toBeTruthy(), opts);
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
    await waitFor(() => expect(screen.queryByText(/match your filters/)).toBeNull(), opts);
  });

  it('saving while signed out sends you to sign in, and a demo login returns you', async () => {
    navigate('/explore');
    mount();
    const save = (await screen.findAllByRole('button', { name: /^Save /i }, opts))[0];
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy(), opts);
    fireEvent.click(screen.getAllByRole('button', { name: 'Use' })[0]);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Explore events' })).toBeTruthy(), opts);
  });

  it('calendar flags the overlapping saved events for the demo student', async () => {
    navigate('/login');
    mount();
    fireEvent.click((await screen.findAllByRole('button', { name: 'Use' }, opts))[0]);
    await waitFor(() => expect(screen.getByRole('button', { name: /Account menu/ })).toBeTruthy(), opts);
    await act(async () => { navigate('/my-events'); });
    await waitFor(() => expect(screen.getByText(/time clash/)).toBeTruthy(), opts);
  });
});
