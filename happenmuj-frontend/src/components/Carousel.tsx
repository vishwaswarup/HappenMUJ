import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import type { EventCardData } from '../lib/types';
import { EventCard } from './EventCard';
import { Icon } from './Icon';
import { CardSkeleton, EmptyState, ErrorState } from './ui';
import { prefersReducedMotion } from '../lib/hooks';

export function Rail({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [can, setCan] = useState({ left: false, right: false });

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const next = { left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 };
    setCan((c) => (c.left === next.left && c.right === next.right ? c : next));
  }, []);

  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el) return;
    el.addEventListener('scroll', measure, { passive: true });
    window.addEventListener('resize', measure);
    return () => { el.removeEventListener('scroll', measure); window.removeEventListener('resize', measure); };
  });

  const go = (dir: 1 | -1) => {
    const el = ref.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.85, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  };

  return (
    <div className="rail">
      {can.left && <button type="button" className="rail__btn rail__btn--left" aria-label={`Scroll ${label} left`} onClick={() => go(-1)}><Icon name="left" /></button>}
      <div className="rail__track" ref={ref} role="list" aria-label={label} tabIndex={0}>
        {children}
      </div>
      {can.right && <button type="button" className="rail__btn rail__btn--right" aria-label={`Scroll ${label} right`} onClick={() => go(1)}><Icon name="right" /></button>}
    </div>
  );
}

interface EventRailProps {
  label: string;
  items: EventCardData[] | undefined;
  loading: boolean;
  error: Error | undefined;
  onRetry: () => void;
  empty: ReactNode;
  emptyTitle?: string;
  ranked?: boolean;
}

export function EventRail({ label, items, loading, error, onRetry, empty, emptyTitle = 'Nothing here yet', ranked }: EventRailProps) {
  if (error && !items) return <ErrorState error={error} onRetry={onRetry} />;
  if (!items && loading) {
    return (
      <Rail label={label}>
        {Array.from({ length: 4 }).map((_, i) => <div role="listitem" className="rail__item" key={i}><CardSkeleton /></div>)}
      </Rail>
    );
  }
  if (!items || items.length === 0) return <EmptyState title={emptyTitle}>{empty}</EmptyState>;
  return (
    <Rail label={label}>
      {items.map((e, i) => (
        <div role="listitem" className={`rail__item${ranked ? ' rail__item--ranked' : ''}`} key={e.id}>
          <EventCard event={e} rank={ranked ? i + 1 : undefined} />
        </div>
      ))}
    </Rail>
  );
}
