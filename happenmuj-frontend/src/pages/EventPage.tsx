import { useEffect } from 'react';
import { api } from '../lib/api';
import { categoryLabel, eventTypeLabel, platformLabel } from '../lib/constants';
import { DETAIL_FIELDS, getPath, isEmptyValue, type DetailField } from '../lib/eventDetails';
import { deadlineLine, formatRange, formatWhen, plural, regState } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { feeDisplay, teamDisplay } from '../lib/rules';
import { Link } from '../lib/router';
import type { EventDetail } from '../lib/types';
import { useApp } from '../state/AppContext';
import { EventRail } from '../components/Carousel';
import { Icon } from '../components/Icon';
import { Poster } from '../components/Poster';
import { Button, ErrorState, Notice, Skeleton, Tag } from '../components/ui';

function renderValue(f: DetailField, v: unknown) {
  if (f.kind === 'bool') return v ? 'Yes' : 'No';
  if (f.kind === 'lines' && Array.isArray(v)) return <ul className="plain-list">{v.map((x, i) => <li key={i}>{String(x)}</li>)}</ul>;
  if (f.kind === 'names' && Array.isArray(v)) return <ul className="plain-list">{v.map((x, i) => <li key={i}>{String((x as { name?: string }).name ?? '')}</li>)}</ul>;
  if (f.kind === 'pairs' && Array.isArray(v) && f.pairKeys) {
    const [a, b] = f.pairKeys;
    return (
      <ul className="plain-list">
        {v.map((x, i) => {
          const r = x as Record<string, unknown>;
          return <li key={i}><strong>{String(r[a] ?? '')}</strong>{r[b] ? ` — ${String(r[b])}` : ''}</li>;
        })}
      </ul>
    );
  }
  if (f.kind === 'number') return String(v);
  return String(v);
}

function Details({ event }: { event: EventDetail }) {
  const rows = (DETAIL_FIELDS[event.event_type] ?? []).map((f) => ({ f, v: getPath(event.details, f.key) })).filter((r) => !isEmptyValue(r.v) && !(r.f.kind === 'bool' && r.v === undefined));
  if (rows.length === 0) return null;
  return (
    <section className="panel" aria-labelledby="details-h">
      <h2 id="details-h" className="panel__title">{eventTypeLabel(event.event_type)} details</h2>
      <dl className="kv">
        {rows.map(({ f, v }) => (
          <div key={f.key}><dt>{f.label}</dt><dd>{renderValue(f, v)}</dd></div>
        ))}
      </dl>
    </section>
  );
}

function Loading() {
  return (
    <div className="container page event" aria-busy="true">
      <Skeleton h={20} w={120} />
      <div className="event__grid">
        <div className="sk sk--poster" />
        <div className="stack stack--tight"><Skeleton h={40} w="70%" /><Skeleton h={20} w="40%" /><Skeleton h={120} /><Skeleton h={48} w={240} /></div>
      </div>
    </div>
  );
}

export function EventPage({ id }: { id: string }) {
  const { isSaved, toggleSave, startRegistration, user } = useApp();
  const ev = useAsync(() => api.getEvent(id), [id]);
  const more = useAsync(async () => {
    if (!ev.data) return [];
    const r = await api.listEvents({ categories: [], clubs: [ev.data.club.id], sort: 'date', page: 1, page_size: 8 });
    return r.items.filter((e) => e.id !== id);
  }, [ev.data?.club.id, id]);
  const posts = useAsync(async () => (ev.data ? api.listPosts({ scope: 'event', ref_id: id, page: 1, page_size: 3 }) : null), [ev.data?.id]);
  useTitle(ev.data?.title ?? 'Event');

  useEffect(() => { api.recordView(id).catch(() => undefined); }, [id]);

  if (ev.error && !ev.data) {
    const notFound = (ev.error as { status?: number }).status === 404;
    return (
      <div className="container page">
        {notFound ? (
          <div className="state"><div className="state__text"><p className="state__title">That event does not exist</p><p className="muted">It may have been removed, or the link is wrong.</p></div><Link to="/explore" className="btn btn--primary btn--sm">Browse events</Link></div>
        ) : <ErrorState error={ev.error} onRetry={ev.reload} title="This event did not load" />}
      </div>
    );
  }
  if (!ev.data) return <Loading />;

  const e = ev.data;
  const reg = regState(e);
  const saved = isSaved(e.id);
  const canRegister = (reg.kind === 'open' || reg.kind === 'closing') && !!e.registration.url;
  const note = deadlineLine(e);
  const venue = [e.venue.name, e.venue.building, e.venue.room].filter(Boolean).join(', ');
  const unpublished = e.status !== 'published' && e.status !== 'cancelled';

  return (
    <div className="container page event">
      <p className="crumbs"><Link to="/explore">Explore events</Link> <Icon name="right" size={14} /> <span>{categoryLabel(e.category)}</span></p>

      {e.status === 'cancelled' && <Notice tone="bad">This event was cancelled.{e.cancel_reason ? ` ${e.cancel_reason}` : ''}</Notice>}
      {reg.kind === 'ended' && <Notice tone="info">This event has ended. You can still read the details below.</Notice>}
      {unpublished && <Notice tone="warn">Only you and platform admins can see this event. Status: {e.status.replace('_', ' ')}.{e.rejection_reason ? ` Reason: ${e.rejection_reason}` : ''}</Notice>}

      <div className="event__grid">
        <div className="event__poster"><Poster event={e} /></div>
        <div className="event__main">
          <div className="event__tags">
            <Tag tone="accent">{categoryLabel(e.category)}</Tag>
            <Tag>{eventTypeLabel(e.event_type)}</Tag>
            {e.tags.filter((t) => t.toLowerCase() !== categoryLabel(e.category).toLowerCase()).slice(0, 4).map((t) => <Tag key={t}>{t}</Tag>)}
          </div>
          <h1 className="event__title">{e.title}</h1>
          <p className="event__club">Hosted by <strong>{e.club.name}</strong></p>
          <p className="event__line">{e.one_liner}</p>

          <dl className="facts">
            <div><dt><Icon name="clock" size={16} /> When</dt><dd>{formatRange(e.schedule.start, e.schedule.end)} <span className="muted">IST</span></dd></div>
            <div><dt><Icon name="pin" size={16} /> Venue</dt><dd>{venue}</dd></div>
            <div><dt><Icon name="tag" size={16} /> Fee</dt><dd>{feeDisplay(e.fee)}</dd></div>
            <div><dt><Icon name="users" size={16} /> Team</dt><dd>{teamDisplay(e.team)}</dd></div>
            <div>
              <dt><Icon name="external" size={16} /> Registration</dt>
              <dd>
                <span className={`reg reg--${reg.kind}`}><span className="reg__dot" aria-hidden="true" />{reg.label}</span>
                {e.registration.required && e.registration.platform && <span className="muted"> on {platformLabel(e.registration.platform)}</span>}
                {note && reg.kind !== 'ended' && reg.kind !== 'cancelled' && <span className="muted"> · {note}</span>}
              </dd>
            </div>
          </dl>

          <div className="event__actions">
            {canRegister && <Button variant="primary" size="lg" onClick={() => startRegistration(e)}>Register on organiser&rsquo;s page <Icon name="external" size={16} /></Button>}
            <Button size="lg" aria-pressed={saved} onClick={() => toggleSave(e)}><Icon name={saved ? 'bookmark-fill' : 'bookmark'} size={18} /> {saved ? 'Saved' : 'Save event'}</Button>
          </div>
          {canRegister && <p className="muted fine">Registration happens on {platformLabel(e.registration.platform)}. HappenMUJ only records that you clicked, so keep your confirmation from the organiser.</p>}
          {!user && <p className="muted fine"><Link to={`/login?next=${encodeURIComponent(`/events/${e.id}`)}`}>Sign in</Link> to save events and add them to your calendar.</p>}
        </div>
      </div>

      <div className="event__cols">
        <div className="stack">
          <section className="panel" aria-labelledby="about-h">
            <h2 id="about-h" className="panel__title">About this event</h2>
            <div className="prose">{e.description.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</div>
          </section>
          <Details event={e} />
        </div>
        <aside className="stack" aria-label="Organiser and discussion">
          {e.contact && (
            <section className="panel">
              <h2 className="panel__title">Questions?</h2>
              <p>{e.contact.name}</p>
              <p className="muted selectable">{e.contact.email}</p>
            </section>
          )}
          <section className="panel" aria-labelledby="disc-h">
            <h2 id="disc-h" className="panel__title">Discussion</h2>
            {posts.data && posts.data.items.length > 0 ? (
              <ul className="plain-list">
                {posts.data.items.map((p) => (
                  <li key={p.id}><Link to={`/community/${p.id}`}>{p.title}</Link> <span className="muted">· {plural(p.comment_count, 'reply', 'replies')}</span></li>
                ))}
              </ul>
            ) : <p className="muted">No one has started a discussion for this event yet.</p>}
            <Link to={`/community?event=${encodeURIComponent(e.id)}`} className="link-btn">Open discussion</Link>
          </section>
        </aside>
      </div>

      {more.data && more.data.length > 0 && (
        <section className="section" aria-labelledby="more-h">
          <div className="section__head"><h2 id="more-h" className="section__title">More from {e.club.name}</h2></div>
          <EventRail label={`More from ${e.club.name}`} items={more.data} loading={more.loading} error={more.error} onRetry={more.reload} empty="" />
        </section>
      )}
      <p className="muted fine">Listed {e.published_at ? formatWhen(e.published_at) : ''}</p>
    </div>
  );
}
