import { CATEGORIES, categoryLabel } from '../lib/constants';
import type { Catalogue } from '../lib/useCatalogue';
import type { Club } from '../lib/types';
import { Icon } from './Icon';

export function Chip({ on, onClick, children, count }: { on: boolean; onClick: () => void; children: React.ReactNode; count?: number }) {
  return (
    <button type="button" className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={onClick}>
      {children}
      {count !== undefined && <span className="chip__count">{count}</span>}
    </button>
  );
}

export function CategoryChips({ cat, showCounts }: { cat: Catalogue; showCounts?: boolean }) {
  return (
    <div className="chips" role="group" aria-label="Filter by category">
      {CATEGORIES.map((c) => (
        <Chip key={c.id} on={cat.categories.includes(c.id)} onClick={() => cat.toggleCategory(c.id)} count={showCounts ? cat.facets?.category[c.id] ?? 0 : undefined}>{c.label}</Chip>
      ))}
    </div>
  );
}

export function ClubChips({ cat, clubs, showCounts }: { cat: Catalogue; clubs: Club[]; showCounts?: boolean }) {
  return (
    <div className="chips" role="group" aria-label="Filter by club">
      {clubs.map((c) => (
        <Chip key={c.id} on={cat.clubs.includes(c.id)} onClick={() => cat.toggleClub(c.id)} count={showCounts ? cat.facets?.club[c.id] ?? 0 : undefined}>{c.name}</Chip>
      ))}
    </div>
  );
}

export function ActivePills({ cat, clubs }: { cat: Catalogue; clubs: Club[] }) {
  if (!cat.filtered) return null;
  const name = (id: string) => clubs.find((c) => c.id === id)?.name ?? id;
  return (
    <div className="pills" aria-label="Active filters">
      {cat.categories.map((c) => (
        <button key={c} type="button" className="pill" onClick={() => cat.toggleCategory(c)}>{categoryLabel(c)}<Icon name="x" size={14} /><span className="sr">Remove filter</span></button>
      ))}
      {cat.clubs.map((c) => (
        <button key={c} type="button" className="pill" onClick={() => cat.toggleClub(c)}>{name(c)}<Icon name="x" size={14} /><span className="sr">Remove filter</span></button>
      ))}
      <button type="button" className="link-btn" onClick={cat.clear}>Clear all</button>
    </div>
  );
}
