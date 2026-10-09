import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { useAsync } from './hooks';
import type { CatalogueResult, Category, EventCardData } from './types';

export interface CatalogueOptions {
  pageSize: number;
  q?: string;
  initialCategories?: Category[];
  initialClubs?: string[];
  sort?: 'date' | 'popularity';
  from?: string;
  to?: string;
}

/** Shared by Home (section 8) and Explore. Filters are OR within a group and AND between groups; the API does the matching. */
export function useCatalogue(opts: CatalogueOptions) {
  const [categories, setCategories] = useState<Category[]>(opts.initialCategories ?? []);
  const [clubs, setClubs] = useState<string[]>(opts.initialClubs ?? []);
  const [sort, setSort] = useState<'date' | 'popularity'>(opts.sort ?? 'date');
  const [from, setFrom] = useState<string | undefined>(opts.from);
  const [to, setTo] = useState<string | undefined>(opts.to);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<EventCardData[]>([]);
  const q = opts.q ?? '';
  const key = JSON.stringify([q, categories, clubs, sort, from, to]);

  useEffect(() => { setPage(1); }, [key]);

  const res = useAsync<CatalogueResult>(
    () => api.listEvents({ q: q || undefined, categories, clubs, sort, date_from: from, date_to: to, page, page_size: opts.pageSize }),
    [key, page],
  );

  useEffect(() => {
    const d = res.data;
    if (!d) return;
    setItems((prev) => {
      if (d.page === 1) return d.items;
      const seen = new Set(prev.map((e) => e.id));
      return [...prev, ...d.items.filter((e) => !seen.has(e.id))];
    });
  }, [res.data]);

  const toggleCategory = useCallback((c: Category) => setCategories((l) => (l.includes(c) ? l.filter((x) => x !== c) : [...l, c])), []);
  const toggleClub = useCallback((id: string) => setClubs((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id])), []);
  const clear = useCallback(() => { setCategories([]); setClubs([]); setFrom(undefined); setTo(undefined); }, []);

  const total = res.data?.total ?? 0;
  return useMemo(() => ({
    categories, clubs, sort, from, to, q,
    setSort, setFrom, setTo, toggleCategory, toggleClub, clear,
    items, total, facets: res.data?.facets,
    loading: res.loading, error: res.error, reload: res.reload,
    hasMore: items.length < total,
    loadMore: () => setPage((p) => p + 1),
    filtered: categories.length + clubs.length + (from ? 1 : 0) + (to ? 1 : 0) + (q ? 1 : 0) > 0,
  }), [categories, clubs, sort, from, to, q, items, total, res.data, res.loading, res.error, res.reload, toggleCategory, toggleClub, clear]);
}
export type Catalogue = ReturnType<typeof useCatalogue>;
