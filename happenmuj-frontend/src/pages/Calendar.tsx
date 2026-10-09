import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import { DOW_MON_FIRST, MONTH_LONG, formatRange, plural, regState } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { findOverlaps } from '../lib/rules';
import { Link } from '../lib/router';
import { dayKeyIST, istDate, istWall } from '../lib/time';
import type { SavedItem } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Icon } from '../components/Icon';
import { Button, ErrorState, Notice, PageHead, Skeleton } from '../components/ui';

export function CalendarPage() {
  useTitle('Calendar');
  const { user, authReady, requireLogin } = useApp();
  const list = useAsync(() => (user ? api.savedEvents() : Promise.resolve([] as SavedItem[])), [user?.id]);
  const today = new Date();
  const w = istWall(today);
  const [ym, setYm] = useState({ y: w.y, m: w.m });
  const [selected, setSelected] = useState<string>(dayKeyIST(today));

  useEffect(() => { if (authReady && !user) requireLogin('Sign in to see your calendar.'); }, [authReady, user, requireLogin]);

  const events = useMemo(() => (list.data ?? []).filter((s) => !s.cancelled).map((s) => s.event), [list.data]);
  const byDay = useMemo(() => {
    const m = new Map<string, typeof events>();
    for (const e of events) {
      const k = dayKeyIST(new Date(e.schedule.start));
      m.set(k, [...(m.get(k) ?? []), e]);
    }
    m.forEach((v) => v.sort((a, b) => new Date(a.schedule.start).getTime() - new Date(b.schedule.start).getTime()));
    return m;
  }, [events]);
  const overlaps = useMemo(() => findOverlaps(events, (iso) => dayKeyIST(new Date(iso))), [events]);
  const clashDays = new Set(overlaps.map((o) => o.day));

  const first = istDate(ym.y, ym.m, 1);
  const lead = (istWall(first).dow + 6) % 7;
  const daysIn = new Date(Date.UTC(ym.y, ym.m + 1, 0)).getUTCDate();
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: daysIn }, (_, i) => i + 1)];
  while (cells.length % 7 !== 0) cells.push(null);
  const keyOf = (d: number) => dayKeyIST(istDate(ym.y, ym.m, d, 12));
  const step = (n: number) => setYm((c) => { const t = new Date(Date.UTC(c.y, c.m + n, 1)); return { y: t.getUTCFullYear(), m: t.getUTCMonth() }; });
  const todayKey = dayKeyIST(today);
  const dayEvents = byDay.get(selected) ?? [];
  const dayOverlaps = overlaps.filter((o) => o.day === selected);
  const nameOf = (id: string) => events.find((e) => e.id === id)?.title ?? id;

  if (!user) return <div className="container page"><PageHead title="Calendar" /></div>;

  return (
    <div className="container page">
      <PageHead title="Calendar" sub="Your saved events by day. Times are in IST." />
      {list.error && !list.data ? <ErrorState error={list.error} onRetry={list.reload} /> : (
        <div className="cal">
          <div className="cal__month">
            <div className="cal__nav">
              <button type="button" className="icon-btn" aria-label="Previous month" onClick={() => step(-1)}><Icon name="left" /></button>
              <h2 className="cal__title" aria-live="polite">{MONTH_LONG[ym.m]} {ym.y}</h2>
              <button type="button" className="icon-btn" aria-label="Next month" onClick={() => step(1)}><Icon name="right" /></button>
              <Button size="sm" onClick={() => { setYm({ y: w.y, m: w.m }); setSelected(todayKey); }}>Today</Button>
            </div>
            {list.loading && !list.data ? <Skeleton h={360} /> : (
              <div className="cal__grid" role="grid" aria-label={`${MONTH_LONG[ym.m]} ${ym.y}`}>
                {DOW_MON_FIRST.map((d) => <div key={d} className="cal__dow" role="columnheader">{d}</div>)}
                {cells.map((d, i) => {
                  if (d === null) return <div key={i} className="cal__cell cal__cell--empty" role="gridcell" />;
                  const k = keyOf(d);
                  const es = byDay.get(k) ?? [];
                  const clash = clashDays.has(k);
                  return (
                    <button
                      key={i}
                      type="button"
                      role="gridcell"
                      className={`cal__cell${k === todayKey ? ' cal__cell--today' : ''}${k === selected ? ' cal__cell--sel' : ''}${clash ? ' cal__cell--clash' : ''}`}
                      aria-pressed={k === selected}
                      aria-label={`${d} ${MONTH_LONG[ym.m]}${es.length ? `, ${plural(es.length, 'event')}` : ''}${clash ? ', time clash' : ''}`}
                      onClick={() => setSelected(k)}
                    >
                      <span className="cal__num">{d}</span>
                      <span className="cal__items">
                        {es.slice(0, 2).map((e) => <span key={e.id} className="cal__item">{e.title}</span>)}
                        {es.length > 2 && <span className="cal__more">+{es.length - 2} more</span>}
                      </span>
                      {es.length > 0 && <span className="cal__dots" aria-hidden="true">{es.slice(0, 3).map((e) => <i key={e.id} />)}</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <section className="cal__day panel" aria-live="polite" aria-label="Selected day">
            <h2 className="panel__title">{new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' }).format(new Date(`${selected}T12:00:00+05:30`))}</h2>
            {dayOverlaps.map((o, i) => (
              <Notice key={i} tone="warn">{nameOf(o.a)} and {nameOf(o.b)} overlap. You may not make both.</Notice>
            ))}
            {dayEvents.length === 0 ? (
              <p className="muted">Nothing saved for this day. <Link to="/explore">Find something to go to</Link>.</p>
            ) : (
              <ul className="agenda">
                {dayEvents.map((e) => {
                  const r = regState(e);
                  return (
                    <li key={e.id}>
                      <Link to={`/events/${e.id}`} className="agenda__title">{e.title}</Link>
                      <span className="muted">{formatRange(e.schedule.start, e.schedule.end)}</span>
                      <span className="muted">{e.venue.name} · {e.club.name}</span>
                      {(r.kind === 'open' || r.kind === 'closing') && <span className={`reg reg--${r.kind}`}><span className="reg__dot" aria-hidden="true" />{r.label}</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
