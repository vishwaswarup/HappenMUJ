import { useState } from 'react';
import { api } from '../lib/api';
import type { ReactionCounts, ReactionKind } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Icon } from './Icon';

export function Reactions({ target, id, counts, mine }: { target: 'post' | 'comment'; id: string; counts: ReactionCounts; mine: ReactionKind | null }) {
  const { requireLogin, toast } = useApp();
  const [c, setC] = useState(counts);
  const [m, setM] = useState(mine);
  const [busy, setBusy] = useState(false);

  const press = async (kind: ReactionKind) => {
    if (busy || !requireLogin('Sign in to react.')) return;
    const prevC = c; const prevM = m;
    const next = { ...c };
    if (m) next[m] = Math.max(0, next[m] - 1);
    const nextMine = m === kind ? null : kind;
    if (nextMine) next[nextMine] += 1;
    setC(next); setM(nextMine); setBusy(true);
    try { await api.react(target, id, kind); } catch (err) {
      setC(prevC); setM(prevM);
      toast(err instanceof Error ? err.message : 'Could not save your reaction.', 'error');
    } finally { setBusy(false); }
  };

  return (
    <div className="reactions">
      <button type="button" className={`react${m === 'like' ? ' react--on' : ''}`} aria-pressed={m === 'like'} onClick={() => press('like')}><Icon name="thumb" size={16} /> Like <span className="react__n">{c.like}</span></button>
      <button type="button" className={`react${m === 'insightful' ? ' react--on' : ''}`} aria-pressed={m === 'insightful'} onClick={() => press('insightful')}><Icon name="bulb" size={16} /> Insightful <span className="react__n">{c.insightful}</span></button>
    </div>
  );
}
