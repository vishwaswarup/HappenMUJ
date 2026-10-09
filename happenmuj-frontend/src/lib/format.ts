import { istWall, startOfDayIST, MS } from './time';
import type { EventCardData } from './types';

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const MONTH_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const DOW_MON_FIRST = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const pad = (n: number) => String(n).padStart(2, '0');

export function formatTime(iso: string): string {
  const w = istWall(new Date(iso));
  const h12 = w.h % 12 === 0 ? 12 : w.h % 12;
  return `${h12}:${pad(w.min)} ${w.h < 12 ? 'AM' : 'PM'}`;
}

/** "Sat 10 Oct" */
export function formatDay(iso: string): string {
  const w = istWall(new Date(iso));
  return `${DOW[w.dow]} ${w.d} ${MONTH[w.m]}`;
}

export function dayParts(iso: string): { dow: string; day: number; month: string } {
  const w = istWall(new Date(iso));
  return { dow: DOW[w.dow], day: w.d, month: MONTH[w.m] };
}

/** "Sat 10 Oct, 4:00 PM" */
export function formatWhen(iso: string): string {
  return `${formatDay(iso)}, ${formatTime(iso)}`;
}

/** "Sat 10 Oct, 4:00 to 6:00 PM" or across days "Sat 10 Oct, 10:00 AM to Sun 11 Oct, 10:00 AM" */
export function formatRange(startIso: string, endIso: string): string {
  const a = istWall(new Date(startIso));
  const b = istWall(new Date(endIso));
  if (a.y === b.y && a.m === b.m && a.d === b.d) {
    const sameHalf = (a.h < 12) === (b.h < 12);
    const startText = sameHalf ? formatTime(startIso).replace(/ (AM|PM)$/, '') : formatTime(startIso);
    return `${formatDay(startIso)}, ${startText} to ${formatTime(endIso)}`;
  }
  return `${formatWhen(startIso)} to ${formatWhen(endIso)}`;
}

export function formatShortDate(iso: string): string {
  const w = istWall(new Date(iso));
  return `${w.d} ${MONTH[w.m]} ${w.y}`;
}

export function relativeTime(iso: string, now = new Date()): string {
  const diff = new Date(iso).getTime() - now.getTime();
  const abs = Math.abs(diff);
  const unit = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
  let text: string;
  if (abs < MS.MIN) return 'just now';
  if (abs < MS.HOUR) text = unit(Math.round(abs / MS.MIN), 'minute');
  else if (abs < MS.DAY) text = unit(Math.round(abs / MS.HOUR), 'hour');
  else if (abs < 14 * MS.DAY) text = unit(Math.round(abs / MS.DAY), 'day');
  else text = unit(Math.round(abs / (7 * MS.DAY)), 'week');
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

export function money(amount: number): string {
  return `₹${amount.toLocaleString('en-IN')}`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Short code printed on the generated poster: "ACM", "AWS Cloud Club" becomes "ACC". */
export function clubCode(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 1) return name.slice(0, 5).toUpperCase();
  const first = words[0];
  if (first === first.toUpperCase() && first.length <= 5) return first;
  return words.map((w) => w[0]).join('').slice(0, 4).toUpperCase();
}

export type RegKind = 'open' | 'closing' | 'closed' | 'none' | 'ended' | 'cancelled';
export interface RegState { kind: RegKind; label: string }

/** Registration state shown on cards and the detail page. We only ever say "open" or "closed", never "registered". */
export function regState(e: Pick<EventCardData, 'registration' | 'registration_open' | 'schedule' | 'status'>, now = new Date()): RegState {
  if (e.status === 'cancelled') return { kind: 'cancelled', label: 'Cancelled' };
  if (new Date(e.schedule.end).getTime() < now.getTime()) return { kind: 'ended', label: 'Ended' };
  if (!e.registration.required) return { kind: 'none', label: 'No registration needed' };
  if (!e.registration_open) return { kind: 'closed', label: 'Registration closed' };
  if (e.registration.deadline) {
    const left = new Date(e.registration.deadline).getTime() - now.getTime();
    if (left <= 72 * MS.HOUR) {
      const sameDay = istWall(new Date(e.registration.deadline)).d === istWall(now).d && left < MS.DAY;
      if (sameDay) return { kind: 'closing', label: 'Closes today' };
      const days = Math.max(1, Math.round(left / MS.DAY));
      return { kind: 'closing', label: left < MS.DAY ? 'Closes tomorrow' : `Closes in ${days} days` };
    }
  }
  return { kind: 'open', label: 'Registration open' };
}

export function deadlineLine(e: Pick<EventCardData, 'registration'>): string | null {
  const d = e.registration.deadline;
  if (!e.registration.required || !d) return null;
  return `Register by ${formatWhen(d)}`;
}

export function isPast(e: Pick<EventCardData, 'schedule'>, now = new Date()): boolean {
  return new Date(e.schedule.end).getTime() < now.getTime();
}

export function isSameDayIST(a: Date, b: Date): boolean {
  return startOfDayIST(a).getTime() === startOfDayIST(b).getTime();
}

export function greeting(now = new Date()): string {
  const h = istWall(now).h;
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Only http(s) links are ever opened. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}
