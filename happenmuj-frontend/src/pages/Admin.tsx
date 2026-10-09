import { useState } from 'react';
import { api } from '../lib/api';
import { categoryLabel } from '../lib/constants';
import { formatWhen } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { Link } from '../lib/router';
import type { EventDetail } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Button, EmptyState, ErrorState, Field, PageHead, Skeleton, Tabs, Tag } from '../components/ui';

type Tab = 'events' | 'clubs' | 'featured';

export function AdminPage() {
  useTitle('Admin');
  const { user, authReady, requireLogin, toast } = useApp();
  const [tab, setTab] = useState<Tab>('events');
  const allowed = user?.role === 'platform_admin';
  const pending = useAsync(() => (allowed ? api.adminEvents('pending_review') : Promise.resolve([] as EventDetail[])), [allowed]);
  const clubs = useAsync(() => (allowed ? api.adminClubs('pending') : Promise.resolve([])), [allowed]);
  const live = useAsync(() => (allowed ? api.adminEvents('published') : Promise.resolve([] as EventDetail[])), [allowed]);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  if (authReady && !user) { requireLogin('Sign in to continue.'); return null; }
  if (!authReady) return <div className="container page"><Skeleton h={160} /></div>;
  if (!allowed) return <div className="container page page--narrow"><EmptyState title="Admins only">This page is for platform admins.</EmptyState></div>;

  const act = async (key: string, fn: () => Promise<unknown>, ok: string, after: () => void) => {
    setBusy(key);
    try { await fn(); toast(ok, 'ok'); after(); } catch (e) { toast(e instanceof Error ? e.message : 'That did not work.', 'error'); } finally { setBusy(null); }
  };

  return (
    <div className="container page">
      <PageHead title="Admin" sub="Review what clubs submit before students see it." />
      <Tabs label="Admin sections" value={tab} onChange={setTab} tabs={[
        { id: 'events', label: 'Event approvals', count: pending.data?.length },
        { id: 'clubs', label: 'Club requests', count: clubs.data?.length },
        { id: 'featured', label: 'Featured event' },
      ]} />
      <div className="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === 'events' && (pending.error ? <ErrorState error={pending.error} onRetry={pending.reload} /> : !pending.data ? <Skeleton h={120} /> : pending.data.length === 0 ? <EmptyState title="Queue is empty">Nothing is waiting for review.</EmptyState> : (
          <ul className="rows">
            {pending.data.map((e) => (
              <li key={e.id} className="row">
                <div className="row__main">
                  <p className="row__title"><Link to={`/events/${e.id}`}>{e.title}</Link></p>
                  <p className="muted">{e.club.name} · {categoryLabel(e.category)} · {formatWhen(e.schedule.start)}</p>
                  <p className="fine">{e.one_liner}</p>
                </div>
                <div className="row__actions">
                  <Button size="sm" variant="primary" loading={busy === e.id} onClick={() => act(e.id, () => api.adminApprove(e.id), 'Approved and published.', pending.reload)}>Approve</Button>
                  <Button size="sm" variant="danger" onClick={() => { setRejecting(rejecting === e.id ? null : e.id); setReason(''); }}>Reject</Button>
                </div>
                {rejecting === e.id && (
                  <div className="row__extra">
                    <Field id={`rj-${e.id}`} label="Reason for the club" hint="They see this and can fix and resubmit."><input id={`rj-${e.id}`} value={reason} onChange={(ev) => setReason(ev.target.value)} /></Field>
                    <div className="form-actions">
                      <Button size="sm" variant="danger" disabled={reason.trim().length < 3} loading={busy === e.id} onClick={() => act(e.id, async () => { await api.adminReject(e.id, reason.trim()); setRejecting(null); }, 'Rejected.', pending.reload)}>Send rejection</Button>
                      <Button size="sm" variant="quiet" onClick={() => setRejecting(null)}>Cancel</Button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ))}
        {tab === 'clubs' && (clubs.error ? <ErrorState error={clubs.error} onRetry={clubs.reload} /> : !clubs.data ? <Skeleton h={120} /> : clubs.data.length === 0 ? <EmptyState title="No club requests">Every club is verified.</EmptyState> : (
          <ul className="rows">
            {clubs.data.map((c) => (
              <li key={c.id} className="row">
                <div className="row__main"><p className="row__title">{c.name}</p><p className="muted">{categoryLabel(c.category)}</p><p className="fine">{c.description}</p></div>
                <Tag tone="warn">Unverified</Tag>
                <div className="row__actions"><Button size="sm" variant="primary" loading={busy === c.id} onClick={() => act(c.id, () => api.adminVerifyClub(c.id), `${c.name} is verified.`, clubs.reload)}>Verify club</Button></div>
              </li>
            ))}
          </ul>
        ))}
        {tab === 'featured' && (live.error ? <ErrorState error={live.error} onRetry={live.reload} /> : !live.data ? <Skeleton h={120} /> : (
          <ul className="rows">
            {live.data.map((e) => {
              const on = !!(e as EventDetail & { featured?: boolean }).featured;
              return (
                <li key={e.id} className="row">
                  <div className="row__main"><p className="row__title"><Link to={`/events/${e.id}`}>{e.title}</Link></p><p className="muted">{e.club.name} · {formatWhen(e.schedule.start)}</p></div>
                  {on && <Tag tone="accent">Featured</Tag>}
                  <div className="row__actions"><Button size="sm" aria-pressed={on} loading={busy === e.id} onClick={() => act(e.id, () => api.adminFeature(e.id, !on), on ? 'Removed from the banner.' : 'Featured on the home page.', live.reload)}>{on ? 'Unfeature' : 'Feature'}</Button></div>
                </li>
              );
            })}
          </ul>
        ))}
      </div>
    </div>
  );
}
