import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useAsync, useTitle } from '../lib/hooks';
import { next7DaysRange, todayRange, restOfMonthRange } from '../lib/time';
import { navigate, qs, useLocation } from '../lib/router';
import { useCatalogue } from '../lib/useCatalogue';
import { CatalogueGrid } from '../components/CatalogueGrid';
import { ActivePills, CategoryChips, ClubChips } from '../components/Filters';
import { Icon } from '../components/Icon';
import { Button, PageHead } from '../components/ui';

type Preset = 'any' | 'today' | 'week' | 'month';

export function ExplorePage() {
  useTitle('Explore events');
  const { query } = useLocation();
  const q = query.get('q') ?? '';
  const base = useCatalogue({ pageSize: 12, q });
  const [preset, setPreset] = useState<Preset>('any');
  const cat = { ...base, clear: () => { base.clear(); setPreset('any'); } };
  const clubs = useAsync(() => api.clubs(), []);
  const [drawer, setDrawer] = useState(false);
  const clubList = clubs.data ?? [];
  const { setFrom, setTo } = cat;

  useEffect(() => {
    const now = new Date();
    if (preset === 'any') { setFrom(undefined); setTo(undefined); return; }
    const r = preset === 'today' ? todayRange(now) : preset === 'week' ? next7DaysRange(now) : restOfMonthRange(now);
    setFrom(r.from.toISOString());
    setTo(r.to.toISOString());
  }, [preset, setFrom, setTo]);

  useEffect(() => {
    if (!drawer) return;
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawer(false); };
    document.addEventListener('keydown', k);
    return () => document.removeEventListener('keydown', k);
  }, [drawer]);

  const filters = (
    <div className="filters">
      <fieldset className="filters__group">
        <legend>When</legend>
        <div className="chips">
          {([['any', 'Any date'], ['today', 'Today'], ['week', 'Next 7 days'], ['month', 'Rest of month']] as [Preset, string][]).map(([id, label]) => (
            <button key={id} type="button" className={`chip${preset === id ? ' chip--on' : ''}`} aria-pressed={preset === id} onClick={() => setPreset(id)}>{label}</button>
          ))}
        </div>
      </fieldset>
      <fieldset className="filters__group">
        <legend>Category</legend>
        <CategoryChips cat={cat} showCounts />
      </fieldset>
      <fieldset className="filters__group">
        <legend>Club</legend>
        <ClubChips cat={cat} clubs={clubList} showCounts />
      </fieldset>
    </div>
  );

  return (
    <div className="container page">
      <PageHead
        title={q ? `Results for “${q}”` : 'Explore events'}
        sub="Upcoming events from verified clubs. Within a group, filters widen the results; across groups, they narrow."
        actions={q ? <Button size="sm" onClick={() => navigate(`/explore${qs({})}`)}>Clear search</Button> : undefined}
      />
      <div className="explore">
        <aside className="explore__side" aria-label="Filters">{filters}</aside>
        <div className="explore__main">
          <div className="explore__bar">
            <Button className="explore__filter-btn" onClick={() => setDrawer(true)}><Icon name="filter" size={16} /> Filters{cat.filtered ? ` (${cat.categories.length + cat.clubs.length + (preset !== 'any' ? 1 : 0)})` : ''}</Button>
            <label className="sort">
              <span className="muted">Sort</span>
              <select value={cat.sort} onChange={(e) => cat.setSort(e.target.value as 'date' | 'popularity')}>
                <option value="date">Soonest first</option>
                <option value="popularity">Most popular</option>
              </select>
            </label>
          </div>
          <ActivePills cat={cat} clubs={clubList} />
          <CatalogueGrid cat={cat} />
        </div>
      </div>
      {drawer && (
        <div className="drawer-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setDrawer(false); }}>
          <div className="drawer" role="dialog" aria-modal="true" aria-label="Filters">
            <div className="drawer__head"><h2>Filters</h2><button type="button" className="icon-btn" aria-label="Close filters" onClick={() => setDrawer(false)}><Icon name="x" /></button></div>
            <div className="drawer__body">{filters}</div>
            <div className="drawer__foot"><Button variant="primary" block onClick={() => setDrawer(false)}>Show {cat.total} {cat.total === 1 ? 'event' : 'events'}</Button></div>
          </div>
        </div>
      )}
    </div>
  );
}
