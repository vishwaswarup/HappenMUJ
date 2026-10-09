import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import { dayKeyIST } from '../lib/time';
import { formatDay, formatTime, isPast, plural } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { findOverlaps } from '../lib/rules';
import { Link } from '../lib/router';
import { useApp } from '../state/AppContext';
import { EventCard } from '../components/EventCard';
import { CardSkeleton, EmptyState, ErrorState, Notice, PageHead, Tabs } from '../components/ui';

type Tab = 'saved' | 'started' | 'past';

export function MyEventsPage() {
  useTitle('My events');
  const { user, authReady, requireLogin, reloadSaved } = useApp();
  const list = useAsync(() => (user ? api.savedEvents() : Promise.resolve([])), [user?.id]);
  const [tab, setTab] = useState<Tab>('saved');

  useEffect(() => { if (authReady && !user) requireLogin('Sign in to see your saved events.'); }, [authReady, user, requireLogin]);
  useEffect(() => { if (user) reloadSaved().catch(() => undefined); }, [user, reloadSaved]);

  const items = list.data ?? [];
  const now = new Date();
  const upcoming = items.filter((s) => !isPast(s.event, now));
  const groups = useMemo(() => ({
    saved: upcoming.filter((s) => s.status === 'saved'),
    started: upcoming.filter((s) => s.status === 'registration_initiated'),
    past: items.filter((s) => isPast(s.event, now)),
  }), [items]); // eslint-disable-line react-hooks/exhaustive-deps
  const overlaps = findOverlaps(upcoming.filter((s) => !s.cancelled).map((s) => s.event), (iso) => dayKeyIST(new Date(iso)));
  const title = (id: string) => items.find((s) => s.event.id === id)?.event.title ?? id;

  if (!user) return <div className="container page"><PageHead title="My events" /></div>;
  const shown = groups[tab];

  return (
    <div className="container page">
      <PageHead title="My events" sub="Events you saved. Dates are in IST." actions={<Link to="/calendar" className="btn btn--sm">View calendar</Link>} />
      {overlaps.length > 0 && (
        <Notice tone="warn" action={<Link to="/calendar" className="link-btn">See on calendar</Link>}>
          {plural(overlaps.length, 'time clash')}: {overlaps.slice(0, 2).map((o) => `${title(o.a)} and ${title(o.b)}`).join('; ')}
          {overlaps.length > 2 ? ' and more' : ''}.
        </Notice>
      )}
      <Tabs
        label="Saved events"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'saved', label: 'Saved', count: groups.saved.length },
          { id: 'started', label: 'Registration started', count: groups.started.length },
          { id: 'past', label: 'Past', count: groups.past.length },
        ]}
      />
      <div role="tabpanel" aria-labelledby={`tab-${tab}`} className="tabpanel">
        {list.error && !list.data ? <ErrorState error={list.error} onRetry={list.reload} /> :
          list.loading && !list.data ? <div className="grid">{Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}</div> :
          shown.length === 0 ? (
            <EmptyState
              title={tab === 'saved' ? 'Nothing saved yet' : tab === 'started' ? 'No registrations started' : 'No past events'}
              action={tab === 'saved' ? <Link to="/explore" className="btn btn--primary btn--sm">Find events</Link> : undefined}
            >
              {tab === 'started' ? 'When you open an organiser’s registration page from an event, it shows up here. We cannot tell whether you finished the form.' : tab === 'saved' ? 'Tap the bookmark on any event to keep it here.' : 'Events you saved that have ended will be listed here.'}
            </EmptyState>
          ) : (
            <div className="grid">
              {shown.map((s) => (
                <div key={s.event.id} className="saved">
                  {s.cancelled && <p className="saved__flag">Cancelled</p>}
                  <EventCard event={s.event} />
                  <p className="muted fine">Saved {formatDay(s.saved_at)}, {formatTime(s.saved_at)}</p>
                </div>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}
