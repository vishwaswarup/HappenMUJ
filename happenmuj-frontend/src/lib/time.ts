// All day logic uses Asia/Kolkata (UTC+05:30, no DST). Datetimes travel as UTC ISO strings.
// This mirrors backend rules: Tomorrow = [00:00 IST tomorrow, 00:00 IST day after),
// Next 7 days = [now, 00:00 IST of today + 7 days).

export const IST_OFFSET_MIN = 330;
const MIN = 60_000;
const DAY = 86_400_000;

export interface Wall { y: number; m: number; d: number; h: number; min: number; dow: number }

/** Wall-clock parts of a moment in IST. m is 0-based, dow is 0 (Sun) to 6 (Sat). */
export function istWall(date: Date): Wall {
  const s = new Date(date.getTime() + IST_OFFSET_MIN * MIN);
  return { y: s.getUTCFullYear(), m: s.getUTCMonth(), d: s.getUTCDate(), h: s.getUTCHours(), min: s.getUTCMinutes(), dow: s.getUTCDay() };
}

/** Build a UTC Date from an IST wall-clock time. */
export function istDate(y: number, m: number, d: number, h = 0, min = 0): Date {
  return new Date(Date.UTC(y, m, d, h, min) - IST_OFFSET_MIN * MIN);
}

export function startOfDayIST(date: Date): Date {
  const w = istWall(date);
  return istDate(w.y, w.m, w.d);
}

export function addDaysIST(startOfDay: Date, n: number): Date {
  const w = istWall(startOfDay);
  return istDate(w.y, w.m, w.d + n);
}

export function dayKeyIST(date: Date): string {
  const w = istWall(date);
  return `${w.y}-${String(w.m + 1).padStart(2, '0')}-${String(w.d).padStart(2, '0')}`;
}

export interface Range { from: Date; to: Date }

export function todayRange(now: Date): Range {
  const s = startOfDayIST(now);
  return { from: s, to: addDaysIST(s, 1) };
}
export function tomorrowRange(now: Date): Range {
  const s = addDaysIST(startOfDayIST(now), 1);
  return { from: s, to: addDaysIST(s, 1) };
}
export function next7DaysRange(now: Date): Range {
  return { from: now, to: addDaysIST(startOfDayIST(now), 7) };
}
/** From now to the end of the current IST month. */
export function restOfMonthRange(now: Date): Range {
  const w = istWall(now);
  return { from: now, to: istDate(w.y, w.m + 1, 1) };
}
export function monthRange(year: number, month0: number): Range {
  return { from: istDate(year, month0, 1), to: istDate(year, month0 + 1, 1) };
}
/** Parse "YYYY-MM-DD" (from <input type="date">) as an IST day start. */
export function parseDateInputIST(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  return istDate(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}
/** Parse "YYYY-MM-DDTHH:mm" (from <input type="datetime-local">) as IST wall time. */
export function parseDateTimeLocalIST(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!m) return null;
  return istDate(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
}
/** Format a moment as "YYYY-MM-DDTHH:mm" in IST for <input type="datetime-local">. */
export function toDateTimeLocalIST(iso: string | null | undefined): string {
  if (!iso) return '';
  const w = istWall(new Date(iso));
  const p = (n: number) => String(n).padStart(2, '0');
  return `${w.y}-${p(w.m + 1)}-${p(w.d)}T${p(w.h)}:${p(w.min)}`;
}

export function inRange(date: Date, r: Range): boolean {
  return date.getTime() >= r.from.getTime() && date.getTime() < r.to.getTime();
}

export const MS = { MIN, HOUR: 60 * MIN, DAY };
