import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { relativeTime, plural } from '../lib/format';
import { useAsync, useDebounced, useTitle } from '../lib/hooks';
import { Link, useLocation } from '../lib/router';
import type { Post, PostScopeType } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Reactions } from '../components/Reactions';
import { Avatar, Button, EmptyState, ErrorState, Field, PageHead, Skeleton, Tabs } from '../components/ui';
import { Icon } from '../components/Icon';

type Tab = 'all' | PostScopeType;

export function PostCard({ post, onDeleted }: { post: Post; onDeleted?: () => void }) {
  const { user, toast } = useApp();
  const can = user && (user.id === post.author.id || user.role === 'platform_admin');
  const remove = async () => {
    try { await api.deletePost(post.id); toast('Post removed.', 'ok'); onDeleted?.(); } catch (e) { toast(e instanceof Error ? e.message : 'Could not remove the post.', 'error'); }
  };
  return (
    <article className="post">
      <header className="post__head">
        <Avatar name={post.author.name} />
        <div>
          <p className="post__author">{post.author.name}</p>
          <p className="muted post__meta">
            {relativeTime(post.created_at)}
            {post.scope.type !== 'global' && <> · {post.scope.type === 'event' ? 'Event' : 'Club'}: {post.scope.ref_label ?? 'unknown'}</>}
            {post.pinned && <> · Pinned</>}
          </p>
        </div>
      </header>
      <h3 className="post__title"><Link to={`/community/${post.id}`}>{post.title}</Link></h3>
      <p className="post__body">{post.body.length > 260 ? `${post.body.slice(0, 260)}…` : post.body}</p>
      <footer className="post__foot">
        <Reactions target="post" id={post.id} counts={post.reaction_counts} mine={post.my_reaction} />
        <Link to={`/community/${post.id}`} className="link-btn"><Icon name="message" size={16} /> {plural(post.comment_count, 'comment')}</Link>
        {can && <button type="button" className="link-btn link-btn--bad" onClick={remove}>Delete</button>}
      </footer>
    </article>
  );
}

function Composer({ presetEvent, onPosted }: { presetEvent: string | null; onPosted: () => void }) {
  const { user, requireLogin, toast } = useApp();
  const [open, setOpen] = useState(!!presetEvent);
  const [scope, setScope] = useState<PostScopeType>(presetEvent ? 'event' : 'global');
  const [ref, setRef] = useState<string>(presetEvent ?? '');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Record<string, string>>({});
  const events = useAsync(() => (open && scope === 'event' ? api.listEvents({ categories: [], clubs: [], sort: 'date', page: 1, page_size: 50 }).then((r) => r.items) : Promise.resolve([])), [open, scope]);
  const clubs = useAsync(() => (open && scope === 'club' ? api.clubs() : Promise.resolve([])), [open, scope]);

  if (!open) {
    return <Button variant="primary" onClick={() => { if (requireLogin('Sign in to start a discussion.')) setOpen(true); }}><Icon name="plus" size={16} /> Start a discussion</Button>;
  }
  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (title.trim().length < 3) errs.title = 'Give it a title of at least 3 characters.';
    if (body.trim().length < 3) errs.body = 'Write at least a few words.';
    if (scope !== 'global' && !ref) errs.ref = scope === 'event' ? 'Choose an event.' : 'Choose a club.';
    setErr(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      await api.createPost({ scope: { type: scope, ref_id: scope === 'global' ? null : ref }, title: title.trim(), body: body.trim() });
      toast('Posted.', 'ok');
      setTitle(''); setBody(''); setOpen(false);
      onPosted();
    } catch (ex) { toast(ex instanceof Error ? ex.message : 'Could not post.', 'error'); } finally { setBusy(false); }
  };

  return (
    <form className="composer panel" onSubmit={submit} noValidate>
      <h2 className="panel__title">New discussion</h2>
      <div className="form-row">
        <Field id="c-scope" label="Where does it belong?">
          <select id="c-scope" value={scope} onChange={(e) => { setScope(e.target.value as PostScopeType); setRef(''); }}>
            <option value="global">Everyone on campus</option>
            <option value="event">A specific event</option>
            <option value="club">A specific club</option>
          </select>
        </Field>
        {scope !== 'global' && (
          <Field id="c-ref" label={scope === 'event' ? 'Event' : 'Club'} error={err.ref}>
            <select id="c-ref" value={ref} onChange={(e) => setRef(e.target.value)} aria-invalid={!!err.ref}>
              <option value="">Choose…</option>
              {scope === 'event' ? (events.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.title}</option>) : (clubs.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </Field>
        )}
      </div>
      <Field id="c-title" label="Title" error={err.title}><input id="c-title" value={title} maxLength={140} onChange={(e) => setTitle(e.target.value)} aria-invalid={!!err.title} /></Field>
      <Field id="c-body" label="What do you want to say?" error={err.body}><textarea id="c-body" rows={4} value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} aria-invalid={!!err.body} /></Field>
      <div className="form-actions">
        <Button type="submit" variant="primary" loading={busy}>Post</Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>
  );
}

export function CommunityPage() {
  useTitle('MUJ-COMMUNITY');
  const { query } = useLocation();
  const presetEvent = query.get('event');
  const [tab, setTab] = useState<Tab>(presetEvent ? 'event' : 'all');
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Post[]>([]);
  const res = useAsync(() => api.listPosts({ scope: tab === 'all' ? undefined : tab, ref_id: presetEvent && tab === 'event' ? presetEvent : undefined, q: dq || undefined, page, page_size: 10 }), [tab, dq, page, presetEvent]);

  useEffect(() => { setPage(1); }, [tab, dq]);
  useEffect(() => {
    const d = res.data;
    if (!d) return;
    setItems((prev) => (d.page === 1 ? d.items : [...prev, ...d.items.filter((x) => !prev.some((p) => p.id === x.id))]));
  }, [res.data]);

  const refresh = () => { if (page === 1) res.reload(); else setPage(1); };
  const hasMore = res.data ? items.length < res.data.total : false;

  return (
    <div className="container page page--narrow">
      <PageHead title="MUJ-COMMUNITY" sub="Ask, answer and plan around campus events. Be kind; posts can be removed by their author or by admins." />
      <Composer presetEvent={presetEvent} onPosted={refresh} />
      <div className="community__bar">
        <Tabs label="Discussion scope" value={tab} onChange={setTab} tabs={[{ id: 'all', label: 'All' }, { id: 'global', label: 'Campus' }, { id: 'event', label: 'Events' }, { id: 'club', label: 'Clubs' }]} />
        <label className="search-inline"><span className="sr">Search discussions</span><Icon name="search" size={16} /><input type="search" placeholder="Search discussions" value={q} onChange={(e) => setQ(e.target.value)} /></label>
      </div>
      {res.error && items.length === 0 ? <ErrorState error={res.error} onRetry={res.reload} title="Discussions did not load" /> :
        res.loading && items.length === 0 ? <div className="stack">{[0, 1, 2].map((i) => <Skeleton key={i} h={120} />)}</div> :
        items.length === 0 ? <EmptyState title="No discussions here yet">Be the first to start one.</EmptyState> : (
          <div className="stack">
            {items.map((p) => <PostCard key={p.id} post={p} onDeleted={refresh} />)}
            {hasMore && <Button loading={res.loading} onClick={() => setPage((n) => n + 1)}>Load more</Button>}
          </div>
        )}
    </div>
  );
}
