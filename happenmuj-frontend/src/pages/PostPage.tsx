import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { relativeTime } from '../lib/format';
import { useAsync, useTitle } from '../lib/hooks';
import { Link } from '../lib/router';
import type { CommentData } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Reactions } from '../components/Reactions';
import { Avatar, Button, EmptyState, ErrorState, Skeleton } from '../components/ui';

function CommentForm({ postId, parentId, onDone, autoFocus, label }: { postId: string; parentId: string | null; onDone: () => void; autoFocus?: boolean; label: string }) {
  const { requireLogin, toast } = useApp();
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!requireLogin('Sign in to comment.')) return;
    if (body.trim().length < 1) { setErr('Write something first.'); return; }
    setBusy(true); setErr('');
    try { await api.addComment(postId, body.trim(), parentId); setBody(''); onDone(); } catch (ex) { toast(ex instanceof Error ? ex.message : 'Could not post your comment.', 'error'); } finally { setBusy(false); }
  };
  const id = `cf-${parentId ?? 'top'}`;
  return (
    <form className="cform" onSubmit={submit} noValidate>
      <label className="sr" htmlFor={id}>{label}</label>
      <textarea id={id} rows={parentId ? 2 : 3} placeholder={label} value={body} autoFocus={autoFocus} maxLength={2000} onChange={(e) => setBody(e.target.value)} aria-invalid={!!err} aria-describedby={err ? `${id}-err` : undefined} />
      {err && <p className="field__error" id={`${id}-err`} role="alert">{err}</p>}
      <Button type="submit" variant="primary" size="sm" loading={busy}>{parentId ? 'Reply' : 'Comment'}</Button>
    </form>
  );
}

function Comment({ c, postId, depth, onChange }: { c: CommentData; postId: string; depth: number; onChange: () => void }) {
  const { user, toast } = useApp();
  const [replying, setReplying] = useState(false);
  const can = user && (user.id === c.author.id || user.role === 'platform_admin');
  const remove = async () => {
    try { await api.deleteComment(c.id); onChange(); } catch (e) { toast(e instanceof Error ? e.message : 'Could not remove the comment.', 'error'); }
  };
  return (
    <li className="comment">
      <Avatar name={c.author.name} />
      <div className="comment__main">
        <p><strong>{c.author.name}</strong> <span className="muted">· {relativeTime(c.created_at)}</span></p>
        {c.status === 'removed' ? <p className="muted"><em>This comment was removed.</em></p> : <p className="comment__body">{c.body}</p>}
        {c.status !== 'removed' && (
          <div className="comment__tools">
            <Reactions target="comment" id={c.id} counts={c.reaction_counts} mine={c.my_reaction} />
            {depth === 0 && <button type="button" className="link-btn" onClick={() => setReplying((v) => !v)}>{replying ? 'Cancel' : 'Reply'}</button>}
            {can && <button type="button" className="link-btn link-btn--bad" onClick={remove}>Delete</button>}
          </div>
        )}
        {replying && <CommentForm postId={postId} parentId={c.id} autoFocus label={`Reply to ${c.author.name}`} onDone={() => { setReplying(false); onChange(); }} />}
        {c.replies && c.replies.length > 0 && (
          <ul className="comments comments--nested">{c.replies.map((r) => <Comment key={r.id} c={r} postId={postId} depth={1} onChange={onChange} />)}</ul>
        )}
      </div>
    </li>
  );
}

export function PostPage({ id }: { id: string }) {
  const post = useAsync(() => api.getPost(id), [id]);
  const comments = useAsync(() => api.listComments(id), [id]);
  useTitle(post.data?.title ?? 'Discussion');

  if (post.error && !post.data) return <div className="container page page--narrow"><ErrorState error={post.error} onRetry={post.reload} title="This discussion did not load" /></div>;
  if (!post.data) return <div className="container page page--narrow"><Skeleton h={200} /></div>;
  const p = post.data;
  return (
    <div className="container page page--narrow">
      <p className="crumbs"><Link to="/community">MUJ-COMMUNITY</Link></p>
      <article className="post post--full">
        <header className="post__head">
          <Avatar name={p.author.name} />
          <div>
            <p className="post__author">{p.author.name}</p>
            <p className="muted post__meta">{relativeTime(p.created_at)}{p.scope.type !== 'global' && <> · {p.scope.type === 'event' ? 'Event' : 'Club'}: {p.scope.ref_label}</>}</p>
          </div>
        </header>
        <h1 className="post__title">{p.title}</h1>
        <div className="prose">{p.body.split(/\n{2,}/).map((t, i) => <p key={i}>{t}</p>)}</div>
        <footer className="post__foot"><Reactions target="post" id={p.id} counts={p.reaction_counts} mine={p.my_reaction} /></footer>
      </article>
      <section aria-labelledby="comments-h" className="stack">
        <h2 id="comments-h" className="section__title">Comments</h2>
        <CommentForm postId={id} parentId={null} label="Add a comment" onDone={() => { comments.reload(); post.reload(); }} />
        {comments.error && !comments.data ? <ErrorState error={comments.error} onRetry={comments.reload} /> :
          !comments.data ? <Skeleton h={80} /> :
          comments.data.length === 0 ? <EmptyState title="No comments yet">Start the conversation.</EmptyState> : (
            <ul className="comments">{comments.data.map((c) => <Comment key={c.id} c={c} postId={id} depth={0} onChange={() => { comments.reload(); post.reload(); }} />)}</ul>
          )}
      </section>
    </div>
  );
}
