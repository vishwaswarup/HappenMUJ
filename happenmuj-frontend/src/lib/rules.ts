import { money } from './format';
import type { Fee, Team } from './types';

export function feeDisplay(fee: Pick<Fee, 'type' | 'amount'>): string {
  const a = fee.amount ?? 0;
  switch (fee.type) {
    case 'free': return 'Free';
    case 'fixed': return money(a);
    case 'per_participant': return `${money(a)} per participant`;
    case 'per_team': return `${money(a)} per team`;
    default: return 'Fee not specified'; // never assume an unspecified fee is free
  }
}

export function teamDisplay(team: Pick<Team, 'type' | 'min' | 'max'>): string {
  switch (team.type) {
    case 'individual': return 'Individual';
    case 'range': return `${team.min ?? '?'}–${team.max ?? '?'} members`;
    case 'fixed': return `Exactly ${team.min ?? team.max ?? '?'} members`;
    case 'not_applicable': return 'No team format';
    default: return 'Team size not specified';
  }
}

export function registrationOpen(
  reg: { required: boolean; deadline: string | null },
  startIso: string,
  now: Date,
): boolean {
  if (!reg.required) return false;
  if (new Date(startIso).getTime() <= now.getTime()) return false;
  return !reg.deadline || new Date(reg.deadline).getTime() > now.getTime();
}

export interface Overlap { day: string; a: string; b: string }

/** Pairs of saved events whose time ranges overlap, with the IST day they fall on. */
export function findOverlaps(
  events: { id: string; schedule: { start: string; end: string } }[],
  dayKey: (iso: string) => string,
): Overlap[] {
  const t = (iso: string) => new Date(iso).getTime();
  const sorted = [...events].sort((x, y) => t(x.schedule.start) - t(y.schedule.start));
  const out: Overlap[] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      const a = sorted[i];
      const b = sorted[j];
      if (new Date(b.schedule.start).getTime() >= new Date(a.schedule.end).getTime()) break;
      out.push({ day: dayKey(b.schedule.start), a: a.id, b: b.id });
    }
  }
  return out;
}
