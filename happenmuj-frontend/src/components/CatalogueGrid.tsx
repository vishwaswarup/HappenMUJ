import type { Catalogue } from '../lib/useCatalogue';
import { EventCard } from './EventCard';
import { Button, CardSkeleton, EmptyState, ErrorState } from './ui';

export function CatalogueGrid({ cat, emptyHint }: { cat: Catalogue; emptyHint?: string }) {
  if (cat.error && cat.items.length === 0) return <ErrorState error={cat.error} onRetry={cat.reload} title="Events did not load" />;
  if (cat.loading && cat.items.length === 0) {
    return <div className="grid">{Array.from({ length: 8 }).map((_, i) => <CardSkeleton key={i} />)}</div>;
  }
  if (cat.items.length === 0) {
    return (
      <EmptyState title="No events match" action={cat.filtered ? <Button size="sm" onClick={cat.clear}>Clear filters</Button> : undefined}>
        {emptyHint ?? 'Try fewer filters. Within a group, picking more options widens the results; across groups, each one narrows them.'}
      </EmptyState>
    );
  }
  return (
    <>
      <div className="grid">{cat.items.map((e) => <EventCard key={e.id} event={e} />)}</div>
      <div className="grid__more">
        <p className="muted" role="status">Showing {cat.items.length} of {cat.total}</p>
        {cat.hasMore && <Button loading={cat.loading} onClick={cat.loadMore}>Load more</Button>}
      </div>
    </>
  );
}
