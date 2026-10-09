import { api } from '../lib/api';
import { useAsync, useTitle } from '../lib/hooks';
import { categoryLabel } from '../lib/constants';
import { formatWhen, greeting, regState } from '../lib/format';
import { feeDisplay } from '../lib/rules';
import { Link } from '../lib/router';
import { useCatalogue } from '../lib/useCatalogue';
import { useApp } from '../state/AppContext';
import { EventRail } from '../components/Carousel';
import { CatalogueGrid } from '../components/CatalogueGrid';
import { ActivePills, CategoryChips, ClubChips } from '../components/Filters';
import { Icon } from '../components/Icon';
import { Poster } from '../components/Poster';
import { Button, ErrorState, Skeleton } from '../components/ui';
import type { ReactNode } from 'react';

function Section({ id, title, sub, action, children }: { id: string; title: string; sub?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="section" aria-labelledby={`${id}-h`}>
      <div className="section__head">
        <div>
          <h2 id={`${id}-h`} className="section__title">{title}</h2>
          {sub && <p className="section__sub muted">{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function Hero() {
  const f = useAsync(() => api.homeFeatured(), []);
  const { isSaved, toggleSave, startRegistration } = useApp();
  if (f.error) return <div className="container"><ErrorState error={f.error} onRetry={f.reload} /></div>;
  if (!f.data) {
    return f.loading ? (
      <div className="hero hero--loading" aria-hidden="true"><div className="container"><Skeleton h={36} w="50%" /><Skeleton h={20} w="35%" /></div></div>
    ) : (
      <div className="container"><div className="hero hero--empty"><h1 className="hero__title">No events yet</h1><p className="muted">When a club publishes one, it will show up here.</p></div></div>
    );
  }
  const e = f.data;
  const reg = regState(e);
  const saved = isSaved(e.id);
  const href = `/events/${encodeURIComponent(e.id)}`;
  return (
    <div className="hero">
      <div className="container hero__inner">
        <div className="hero__text">
          <p className="eyebrow">Featured &middot; {categoryLabel(e.category)}</p>
          <h1 className="hero__title">{e.title}</h1>
          <p className="hero__line">{e.one_liner}</p>
          <ul className="hero__facts">
            <li><Icon name="clock" size={16} />{formatWhen(e.schedule.start)}</li>
            <li><Icon name="pin" size={16} />{e.venue.name}</li>
            <li><Icon name="tag" size={16} />{feeDisplay(e.fee)}</li>
            <li className={`reg reg--${reg.kind}`}><span className="reg__dot" aria-hidden="true" />{reg.label}</li>
          </ul>
          <p className="muted">By {e.club.name}</p>
          <div className="hero__actions">
            <Link to={href} className="btn btn--primary btn--lg">See details</Link>
            {reg.kind === 'open' || reg.kind === 'closing' ? (
              <Button size="lg" onClick={() => startRegistration(e)}>Register on organiser&rsquo;s page <Icon name="external" size={16} /></Button>
            ) : null}
            <Button size="lg" variant="quiet" aria-pressed={saved} onClick={() => toggleSave(e)}>
              <Icon name={saved ? 'bookmark-fill' : 'bookmark'} size={18} /> {saved ? 'Saved' : 'Save'}
            </Button>
          </div>
        </div>
        <Link to={href} className="hero__poster" aria-label={`Open ${e.title}`} tabIndex={-1}><Poster event={e} fit="cover" /></Link>
      </div>
    </div>
  );
}

export function HomePage() {
  useTitle('');
  const { user } = useApp();
  const suggested = useAsync(() => api.homeSuggested(), [user?.id]);
  const top = useAsync(() => api.homeTop(), []);
  const next7 = useAsync(() => api.homeNext7(), []);
  const tomorrow = useAsync(() => api.homeTomorrow(), []);
  const clubs = useAsync(() => api.clubs(), []);
  const cat = useCatalogue({ pageSize: 12 });
  const clubList = clubs.data ?? [];

  return (
    <>
      <Hero />
      <div className="container stack">
        <Section
          id="suggested"
          title={user ? `${greeting()}, ${user.name.split(' ')[0]}. Picked for you` : 'Suggested for you'}
          sub={suggested.data && !suggested.data.personalised ? 'Sign in and add interests to tune this row. For now, these are what is coming up soonest.' : 'Based on your interests, categories and the clubs you follow.'}
        >
          <EventRail label="Suggested events" items={suggested.data?.items} loading={suggested.loading} error={suggested.error} onRetry={suggested.reload} empty="Nothing to suggest right now." />
        </Section>

        <Section id="top" title="Top 10 this week" sub={top.data?.disclaimer ?? 'Ranked by saves, views and registration clicks, and how soon the event is.'}>
          <EventRail label="Top 10 events" ranked items={top.data?.items} loading={top.loading} error={top.error} onRetry={top.reload} empty="Not enough activity to rank events yet." />
        </Section>

        <Section id="next7" title="Next 7 days" action={<Link to="/explore" className="link-btn">All events</Link>}>
          <EventRail label="Events in the next 7 days" items={next7.data} loading={next7.loading} error={next7.error} onRetry={next7.reload} empty="No events in the next 7 days." />
        </Section>

        <Section id="tomorrow" title="Tomorrow">
          <EventRail label="Events tomorrow" items={tomorrow.data} loading={tomorrow.loading} error={tomorrow.error} onRetry={tomorrow.reload} emptyTitle="A quiet day" empty="Nothing is scheduled for tomorrow." />
        </Section>

        <Section id="cats" title="Browse by category" sub="Pick more than one to widen the results.">
          <CategoryChips cat={cat} />
        </Section>

        <Section id="clubs" title="Browse by club" sub="Verified clubs only. Mixing categories and clubs narrows the results.">
          {clubs.error ? <ErrorState error={clubs.error} onRetry={clubs.reload} /> : clubs.loading && !clubs.data ? <Skeleton h={40} /> : <ClubChips cat={cat} clubs={clubList} />}
        </Section>

        <Section id="all" title="All upcoming events" sub={cat.total ? `${cat.total} ${cat.total === 1 ? 'event' : 'events'}${cat.filtered ? ' match your filters' : ''}` : undefined}>
          <ActivePills cat={cat} clubs={clubList} />
          <CatalogueGrid cat={cat} />
        </Section>
      </div>
    </>
  );
}
