import { describe, expect, it } from 'vitest';
import { createMockApi } from '../src/lib/api/mock';
import { findOverlaps, feeDisplay, teamDisplay } from '../src/lib/rules';
import { regState } from '../src/lib/format';
import {
  dayKeyIST, istDate, istWall, next7DaysRange, startOfDayIST, todayRange, tomorrowRange, monthRange, parseDateTimeLocalIST, toDateTimeLocalIST,
} from '../src/lib/time';
import type { CatalogueParams } from '../src/lib/types';

const params = (over: Partial<CatalogueParams> = {}): CatalogueParams => ({ categories: [], clubs: [], sort: 'date', page: 1, page_size: 50, ...over });

describe('IST day boundaries', () => {
  it('rolls the day at 18:30 UTC', () => {
    const justBefore = new Date('2026-10-09T18:29:59Z'); // 23:59:59 IST on the 9th
    const justAfter = new Date('2026-10-09T18:30:00Z'); // 00:00 IST on the 10th
    expect(dayKeyIST(justBefore)).toBe('2026-10-09');
    expect(dayKeyIST(justAfter)).toBe('2026-10-10');
  });

  it('computes tomorrow as [00:00 IST tomorrow, 00:00 IST day after)', () => {
    const now = new Date('2026-10-09T07:30:00Z'); // 13:00 IST
    const r = tomorrowRange(now);
    expect(r.from.toISOString()).toBe('2026-10-09T18:30:00.000Z');
    expect(r.to.toISOString()).toBe('2026-10-10T18:30:00.000Z');
  });

  it('puts an event at 00:30 IST tomorrow inside tomorrow and 23:30 IST today outside it', () => {
    const now = new Date('2026-10-09T07:30:00Z');
    const r = tomorrowRange(now);
    const lateToday = istDate(2026, 9, 9, 23, 30);
    const earlyTomorrow = istDate(2026, 9, 10, 0, 30);
    expect(lateToday.getTime() < r.from.getTime()).toBe(true);
    expect(earlyTomorrow.getTime() >= r.from.getTime() && earlyTomorrow.getTime() < r.to.getTime()).toBe(true);
  });

  it('treats exactly midnight IST as the start of the new day', () => {
    const midnight = istDate(2026, 9, 10, 0, 0);
    expect(istWall(midnight).d).toBe(10);
    expect(startOfDayIST(midnight).getTime()).toBe(midnight.getTime());
  });

  it('next 7 days ends at 00:00 IST of today + 7', () => {
    const now = new Date('2026-10-09T07:30:00Z');
    const r = next7DaysRange(now);
    expect(r.from.getTime()).toBe(now.getTime());
    expect(r.to.toISOString()).toBe('2026-10-15T18:30:00.000Z');
    expect(todayRange(now).from.toISOString()).toBe('2026-10-08T18:30:00.000Z');
  });

  it('builds month ranges and round-trips datetime-local values', () => {
    expect(monthRange(2026, 9).from.toISOString()).toBe('2026-09-30T18:30:00.000Z');
    const d = parseDateTimeLocalIST('2026-10-10T16:00')!;
    expect(d.toISOString()).toBe('2026-10-10T10:30:00.000Z');
    expect(toDateTimeLocalIST(d.toISOString())).toBe('2026-10-10T16:00');
  });
});

describe('fee and team display', () => {
  it('never reads an unspecified fee as free', () => {
    expect(feeDisplay({ type: 'not_specified', amount: null })).toBe('Fee not specified');
    expect(feeDisplay({ type: 'free', amount: null })).toBe('Free');
    expect(feeDisplay({ type: 'per_team', amount: 499 })).toBe('₹499 per team');
  });
  it('describes team formats', () => {
    expect(teamDisplay({ type: 'range', min: 2, max: 4 })).toBe('2–4 members');
    expect(teamDisplay({ type: 'fixed', min: 3, max: 3 })).toBe('Exactly 3 members');
    expect(teamDisplay({ type: 'individual' })).toBe('Individual');
  });
});

describe('overlap detection', () => {
  const day = (iso: string) => dayKeyIST(new Date(iso));
  it('finds overlapping ranges and ignores back-to-back events', () => {
    const list = [
      { id: 'a', schedule: { start: '2026-10-10T10:30:00Z', end: '2026-10-10T12:30:00Z' } },
      { id: 'b', schedule: { start: '2026-10-10T11:30:00Z', end: '2026-10-10T13:30:00Z' } },
      { id: 'c', schedule: { start: '2026-10-10T13:30:00Z', end: '2026-10-10T14:30:00Z' } },
    ];
    const o = findOverlaps(list, day);
    expect(o).toHaveLength(1);
    expect([o[0].a, o[0].b]).toEqual(['a', 'b']);
  });
});

describe('sample API behaviour', () => {
  const now = () => new Date();
  const make = () => createMockApi({ now });

  it('only exposes published, upcoming events in discovery', async () => {
    const api = make();
    const all = await api.listEvents(params());
    expect(all.items.length).toBeGreaterThan(10);
    expect(all.items.every((e) => e.status === 'published')).toBe(true);
    expect(all.items.every((e) => new Date(e.schedule.start).getTime() > Date.now())).toBe(true);
    expect(all.items.find((e) => e.title === 'Hardware Hack Day')).toBeUndefined(); // cancelled
    expect(all.items.find((e) => e.title === 'Generative AI Workshop')).toBeUndefined(); // pending review
  });

  it('filters with OR inside a group and AND between groups', async () => {
    const api = make();
    const clubs = await api.clubs();
    const id = (name: string) => clubs.find((c) => c.name === name)!.id;
    const r = await api.listEvents(params({ categories: ['technical', 'hackathon'], clubs: [id('ACM'), id('IEEE')] }));
    expect(r.items.length).toBeGreaterThan(0);
    for (const e of r.items) {
      expect(['technical', 'hackathon']).toContain(e.category);
      expect(['ACM', 'IEEE']).toContain(e.club.name);
    }
    // Same two groups on their own return more than the combination
    const onlyCats = await api.listEvents(params({ categories: ['technical', 'hackathon'] }));
    const onlyClubs = await api.listEvents(params({ clubs: [id('ACM'), id('IEEE')] }));
    expect(onlyCats.total).toBeGreaterThan(r.total);
    expect(onlyClubs.total).toBeGreaterThan(r.total);
  });

  it('searches title, tags and club and counts facets without the group being counted', async () => {
    const api = make();
    const r = await api.listEvents(params({ q: 'robotics' }));
    expect(r.items.length).toBeGreaterThan(0);
    const filtered = await api.listEvents(params({ categories: ['sports'] }));
    // The category facet ignores the category filter itself, so other categories still show counts
    expect(Object.keys(filtered.facets.category).length).toBeGreaterThan(1);
  });

  it('ranks at most ten eligible events, best first, without padding', async () => {
    const api = make();
    const top = await api.homeTop();
    expect(top.items.length).toBeLessThanOrEqual(10);
    expect(top.items.map((e) => e.rank)).toEqual(top.items.map((_, i) => i + 1));
    const scores = top.items.map((e) => Object.values(e.score_breakdown).reduce((a, b) => a + b, 0));
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
    expect(top.items.every((e) => e.status === 'published' && !(e.registration.required && !e.registration_open && e.registration.deadline && new Date(e.registration.deadline) < new Date()))).toBe(true);
    expect(top.disclaimer).toMatch(/not an endorsement/i);
  });

  it('keeps next-7-days chronological and tomorrow inside tomorrow', async () => {
    const api = make();
    const week = await api.homeNext7();
    const starts = week.map((e) => new Date(e.schedule.start).getTime());
    expect([...starts].sort((a, b) => a - b)).toEqual(starts);
    const tm = tomorrowRange(new Date());
    const tomorrow = await api.homeTomorrow();
    expect(tomorrow.length).toBeGreaterThan(0);
    expect(tomorrow.every((e) => new Date(e.schedule.start) >= tm.from && new Date(e.schedule.start) < tm.to)).toBe(true);
  });

  it('requires sign-in to save and keeps saving idempotent', async () => {
    const api = make();
    await expect(api.saveEvent('e02')).rejects.toMatchObject({ status: 401 });
    await api.login('ishita@muj-demo.edu', 'demo1234');
    await api.saveEvent('e07');
    await api.saveEvent('e07');
    const saved = await api.savedEvents();
    expect(saved.filter((s) => s.event.id === 'e07')).toHaveLength(1);
    await api.unsaveEvent('e07');
    expect((await api.savedEvents()).some((s) => s.event.id === 'e07')).toBe(false);
  });

  it('personalises suggestions for a student with interests and not for anonymous visitors', async () => {
    const anon = make();
    expect((await anon.homeSuggested()).personalised).toBe(false);
    const api = make();
    await api.login('student@muj-demo.edu', 'demo1234');
    const s = await api.homeSuggested();
    expect(s.personalised).toBe(true);
    const saved = new Set((await api.savedEvents()).map((x) => x.event.id));
    expect(s.items.some((e) => saved.has(e.id))).toBe(false);
  });

  it('enforces roles on club and admin actions', async () => {
    const api = make();
    await api.login('student@muj-demo.edu', 'demo1234');
    await expect(api.myEvents()).rejects.toMatchObject({ status: 403 });
    await expect(api.adminEvents('pending_review')).rejects.toMatchObject({ status: 403 });
    await api.login('ieee@muj-demo.edu', 'demo1234');
    const mine = await api.myEvents();
    expect(mine.every((e) => e.club.name === 'IEEE')).toBe(true);
    await expect(api.submitEvent('e41')).rejects.toMatchObject({ status: 403 }); // another club's draft
  });

  it('moves events through review', async () => {
    const api = make();
    await api.login('admin@muj-demo.edu', 'demo1234');
    const pending = await api.adminEvents('pending_review');
    expect(pending.length).toBeGreaterThan(0);
    await api.adminReject(pending[0].id, 'Missing venue confirmation');
    expect((await api.adminEvents('rejected')).some((e) => e.id === pending[0].id)).toBe(true);
    await api.adminApprove(pending[1].id);
    expect((await api.listEvents(params({ page_size: 50 }))).items.some((e) => e.id === pending[1].id)).toBe(true);
  });

  it('caps comment threads at two levels and keeps counters in step', async () => {
    const api = make();
    await api.login('student@muj-demo.edu', 'demo1234');
    const before = (await api.getPost('p3')).comment_count;
    const top = await api.addComment('p3', 'Thanks for the answer', null);
    const reply = await api.addComment('p3', 'Reply', top.id);
    const deep = await api.addComment('p3', 'Reply to the reply', reply.id);
    expect(deep.parent_id).toBe(top.id);
    expect((await api.getPost('p3')).comment_count).toBe(before + 3);
    const thread = await api.listComments('p3');
    expect(thread.find((c) => c.id === top.id)?.replies).toHaveLength(2);
  });

  it('toggles reactions and keeps one reaction per user', async () => {
    const api = make();
    await api.login('student@muj-demo.edu', 'demo1234');
    const base = (await api.getPost('p2')).reaction_counts;
    await api.react('post', 'p2', 'like');
    expect((await api.getPost('p2')).reaction_counts.like).toBe(base.like + 1);
    await api.react('post', 'p2', 'insightful');
    const switched = await api.getPost('p2');
    expect(switched.reaction_counts.like).toBe(base.like);
    expect(switched.reaction_counts.insightful).toBe(base.insightful + 1);
    await api.react('post', 'p2', 'insightful');
    expect((await api.getPost('p2')).my_reaction).toBeNull();
  });
});

describe('registration state', () => {
  const base = { schedule: { start: '2026-10-10T10:30:00Z', end: '2026-10-10T12:30:00Z' }, status: 'published' as const };
  it('reports open, closing, closed and none without claiming anyone is registered', () => {
    const now = new Date('2026-10-09T07:30:00Z');
    expect(regState({ ...base, registration: { required: true, platform: 'google_forms', deadline: '2026-10-20T00:00:00Z' }, registration_open: true }, now).kind).toBe('open');
    expect(regState({ ...base, registration: { required: true, platform: 'google_forms', deadline: '2026-10-09T18:29:00Z' }, registration_open: true }, now).kind).toBe('closing');
    expect(regState({ ...base, registration: { required: true, platform: 'google_forms', deadline: '2026-10-08T00:00:00Z' }, registration_open: false }, now).kind).toBe('closed');
    expect(regState({ ...base, registration: { required: false, platform: null, deadline: null }, registration_open: false }, now).kind).toBe('none');
  });
});
