import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from '../src/App';
import { AppProvider } from '../src/state/AppContext';
import { navigate } from '../src/lib/router';

const opts = { timeout: 4000 };

describe('every route renders for the platform admin', () => {
  it('visits each page without errors', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    navigate('/login');
    render(<AppProvider><App /></AppProvider>);
    const use = await screen.findAllByRole('button', { name: 'Use' }, opts);
    fireEvent.click(use[2]);
    await waitFor(() => expect(screen.getByRole('button', { name: /Account menu/ })).toBeTruthy(), opts);
    const expectations: [string, RegExp][] = [
      ['/explore', /Explore events/],
      ['/events/e03', /Battle of Bands/i],
      ['/calendar', /Calendar/],
      ['/community', /MUJ-COMMUNITY/],
      ['/profile', /Clubs you follow/],
      ['/manage', /Manage events/],
      ['/manage/new', /The basics/],
      ['/admin', /Event approvals/],
      ['/nope', /That page does not exist/],
    ];
    for (const [path, text] of expectations) {
      await act(async () => { navigate(path); });
      await waitFor(() => expect(screen.getAllByText(text).length).toBeGreaterThan(0), opts);
    }
    await act(async () => { navigate('/admin'); });
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Approve' }).length).toBeGreaterThan(0), opts);
    await act(async () => { navigate('/community'); });
    const post = await screen.findAllByRole('link', { name: /.{5,}/ }, opts);
    expect(post.length).toBeGreaterThan(0);
    expect(err.mock.calls.map((c) => String(c[0]).slice(0, 160))).toEqual([]);
  });
});
