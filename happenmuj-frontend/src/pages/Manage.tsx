import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { formatWhen } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { Link } from '../lib/router';
import type { Category, EventDetail, EventStatus } from '../lib/types';
import { CATEGORIES } from '../lib/constants';
import { useApp } from '../state/AppContext';
import { Button, EmptyState, ErrorState, Field, Notice, PageHead, Skeleton, Tag } from '../components/ui';
import { EventForm } from './EventForm';

const STATUS: Record<EventStatus, { label: string; tone: 'plain' | 'ok' | 'warn' | 'bad' | 'accent' }> = {
  draft: { label: 'Draft', tone: 'plain' },
  pending_review: { label: 'In review', tone: 'warn' },
  published: { label: 'Published', tone: 'ok' },
  rejected: { label: 'Rejected', tone: 'bad' },
  cancelled: { label: 'Cancelled', tone: 'bad' },
};

function useGate(): { ok: boolean; wait: boolean } {
  const { user, authReady, requireLogin } = useApp();
  useEffect(() => { if (authReady && !user) requireLogin('Sign in to manage events.'); }, [authReady, user, requireLogin]);
  return { ok: !!user && user.role !== 'student', wait: !authReady };
}

function NoAccess({ wait }: { wait: boolean }) {
  const { user, toast } = useApp();
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [cat, setCat] = useState<Category>('technical');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  if (wait || !user) return <div className="container page"><Skeleton h={120} /></div>;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim().length < 3 || desc.trim().length < 10) { setErr('Add the club name and a short description.'); return; }
    setErr(''); setBusy(true);
    try { await api.requestClub(name.trim(), desc.trim(), cat); toast('Request sent. An admin will verify your club.', 'ok'); setName(''); setDesc(''); } catch (ex) { toast(ex instanceof Error ? ex.message : 'Could not send the request.', 'error'); } finally { setBusy(false); }
  };
  return (
    <div className="container page page--narrow">
      <PageHead title="For clubs" sub="Only club admins can publish events. Ask for your club to be added and verified." />
      <form className="panel form" onSubmit={submit} noValidate>
        <Field id="rc-name" label="Club name"><input id="rc-name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field id="rc-cat" label="Main category"><select id="rc-cat" value={cat} onChange={(e) => setCat(e.target.value as Category)}>{CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
        <Field id="rc-desc" label="What does the club do?" error={err}><textarea id="rc-desc" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        <div><Button type="submit" variant="primary" loading={busy}>Request verification</Button></div>
      </form>
    </div>
  );
}

export function ManagePage() {
  useTitle('Manage events');
  const gate = useGate();
  const list = useAsync(() => (gate.ok ? api.myEvents() : Promise.resolve([] as EventDetail[])), [gate.ok]);
  const { toast } = useApp();
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!gate.ok) return <NoAccess wait={gate.wait} />;

  const act = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusyId(id);
    try { await fn(); toast(ok, 'ok'); list.reload(); } catch (e) { toast(e instanceof Error ? e.message : 'That did not work.', 'error'); } finally { setBusyId(null); }
  };

  return (
    <div className="container page">
      <PageHead title="Manage events" sub="Events from the clubs you run." actions={<Link to="/manage/new" className="btn btn--primary"><span>New event</span></Link>} />
      {list.error && !list.data ? <ErrorState error={list.error} onRetry={list.reload} /> :
        !list.data ? <div className="stack">{[0, 1, 2].map((i) => <Skeleton key={i} h={72} />)}</div> :
        list.data.length === 0 ? <EmptyState title="No events yet" action={<Link to="/manage/new" className="btn btn--primary btn--sm">Create your first event</Link>}>Drafts stay private until you send them for review.</EmptyState> : (
          <ul className="rows">
            {list.data.map((e) => (
              <li key={e.id} className="row">
                <div className="row__main">
                  <p className="row__title"><Link to={`/events/${e.id}`}>{e.title}</Link></p>
                  <p className="muted">{e.club.name} · {formatWhen(e.schedule.start)}</p>
                  {e.status === 'rejected' && e.rejection_reason && <Notice tone="bad">Rejected: {e.rejection_reason}</Notice>}
                  {e.status === 'published' && <p className="muted fine">{e.stats.views} views · {e.stats.saves} saves</p>}
                </div>
                <Tag tone={STATUS[e.status].tone}>{STATUS[e.status].label}</Tag>
                <div className="row__actions">
                  {e.status !== 'cancelled' && <Link to={`/manage/${e.id}/edit`} className="btn btn--sm">Edit</Link>}
                  {(e.status === 'draft' || e.status === 'rejected') && <Button size="sm" variant="primary" loading={busyId === e.id} onClick={() => act(e.id, () => api.submitEvent(e.id), 'Sent for review.')}>Send for review</Button>}
                  {e.status === 'published' && <Button size="sm" onClick={() => { setCancelId(cancelId === e.id ? null : e.id); setReason(''); }}>Cancel event</Button>}
                  {(e.status === 'draft' || e.status === 'rejected') && <Button size="sm" variant="danger" onClick={() => act(e.id, () => api.deleteEvent(e.id), 'Draft deleted.')}>Delete</Button>}
                </div>
                {cancelId === e.id && (
                  <div className="row__extra">
                    <Field id={`cr-${e.id}`} label="Reason shown to students" hint="Everyone who saved the event will see this."><input id={`cr-${e.id}`} value={reason} onChange={(ev) => setReason(ev.target.value)} /></Field>
                    <div className="form-actions">
                      <Button variant="danger" size="sm" disabled={reason.trim().length < 3} loading={busyId === e.id} onClick={() => act(e.id, async () => { await api.cancelEvent(e.id, reason.trim()); setCancelId(null); }, 'Event cancelled.')}>Confirm cancellation</Button>
                      <Button size="sm" variant="quiet" onClick={() => setCancelId(null)}>Keep it</Button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}

export function EventEditorPage({ id }: { id?: string }) {
  useTitle(id ? 'Edit event' : 'New event');
  const gate = useGate();
  const { user } = useApp();
  const clubs = useAsync(() => (gate.ok ? api.clubs() : Promise.resolve([])), [gate.ok]);
  const ev = useAsync(() => (id && gate.ok ? api.getEvent(id) : Promise.resolve(undefined)), [id, gate.ok]);
  if (!gate.ok) return <NoAccess wait={gate.wait} />;
  const mine = (clubs.data ?? []).filter((c) => user && (user.role === 'platform_admin' || user.managed_club_ids.includes(c.id)));
  const loading = (!clubs.data && !clubs.error) || (!!id && !ev.data && !ev.error);
  return (
    <div className="container page page--narrow">
      <PageHead title={id ? 'Edit event' : 'New event'} sub="Drafts are private. Events appear publicly after an admin approves them." />
      {clubs.error ? <ErrorState error={clubs.error} onRetry={clubs.reload} /> : ev.error ? <ErrorState error={ev.error} onRetry={ev.reload} /> : loading ? <Skeleton h={400} /> :
        mine.length === 0 ? <EmptyState title="You do not run a verified club yet">Ask for your club to be verified from the For clubs page.</EmptyState> :
        <EventForm key={id ?? 'new'} existing={ev.data} clubs={mine} />}
    </div>
  );
}
