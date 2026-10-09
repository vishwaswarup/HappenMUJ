import type { DetailsBag, EventType } from './types';

// Each event type carries different fields inside `details`, in the same events collection.
// This config drives both the create-event form and the read-only panel on the event page.

export type FieldKind = 'text' | 'textarea' | 'number' | 'bool' | 'lines' | 'pairs' | 'names' | 'date';

export interface DetailField {
  key: string; // dotted path inside details, e.g. "speaker.name"
  label: string;
  kind: FieldKind;
  hint?: string;
  pairKeys?: [string, string]; // for kind "pairs": object keys, entered as "first: second"
}

export const DETAIL_FIELDS: Record<EventType, DetailField[]> = {
  workshop: [
    { key: 'speaker.name', label: 'Speaker', kind: 'text' },
    { key: 'speaker.bio', label: 'Speaker bio', kind: 'text' },
    { key: 'topics', label: 'Topics covered', kind: 'lines', hint: 'One per line' },
    { key: 'duration_minutes', label: 'Duration in minutes', kind: 'number' },
    { key: 'prerequisites', label: 'Prerequisites', kind: 'lines', hint: 'One per line' },
    { key: 'bring_own_laptop', label: 'Bring your own laptop', kind: 'bool' },
  ],
  competition: [
    { key: 'prizes', label: 'Prizes', kind: 'pairs', pairKeys: ['rank', 'reward'], hint: 'One per line, like "1st: ₹5,000"' },
    { key: 'eligibility', label: 'Who can take part', kind: 'text' },
    { key: 'rounds', label: 'Rounds', kind: 'pairs', pairKeys: ['name', 'description'], hint: 'One per line, like "Prelims: 20 questions"' },
    { key: 'judging_criteria', label: 'Judging criteria', kind: 'lines', hint: 'One per line' },
  ],
  hackathon: [
    { key: 'themes', label: 'Themes', kind: 'lines', hint: 'One per line' },
    { key: 'tracks', label: 'Tracks', kind: 'lines', hint: 'One per line' },
    { key: 'duration_hours', label: 'Duration in hours', kind: 'number' },
    { key: 'prizes', label: 'Prizes', kind: 'lines', hint: 'One per line' },
    { key: 'max_teams', label: 'Maximum teams', kind: 'number' },
  ],
  sports_match: [
    { key: 'sport', label: 'Sport', kind: 'text' },
    { key: 'match_type', label: 'Match type', kind: 'text', hint: 'Knockout, league, friendly' },
    { key: 'format', label: 'Format', kind: 'text', hint: 'For example 11-a-side' },
    { key: 'teams', label: 'Teams', kind: 'names', hint: 'One team per line' },
  ],
  cultural_show: [
    { key: 'performances', label: 'Performances', kind: 'pairs', pairKeys: ['title', 'performer'], hint: 'One per line, like "Opening act: AURA Dance Crew"' },
    { key: 'artists', label: 'Artists', kind: 'lines', hint: 'One per line' },
    { key: 'auditions_required', label: 'Auditions required', kind: 'bool' },
    { key: 'audition_date', label: 'Audition date', kind: 'date' },
  ],
  seminar: [
    { key: 'speaker.name', label: 'Speaker', kind: 'text' },
    { key: 'speaker.affiliation', label: 'Affiliation', kind: 'text' },
    { key: 'topic', label: 'Topic', kind: 'text' },
    { key: 'q_and_a_enabled', label: 'Q&A at the end', kind: 'bool' },
  ],
  social: [{ key: 'extra.notes', label: 'Notes', kind: 'textarea' }],
  other: [{ key: 'extra.notes', label: 'Notes', kind: 'textarea' }],
};

export function getPath(obj: unknown, path: string): unknown {
  let cur: unknown = obj;
  for (const part of path.split('.')) {
    if (cur && typeof cur === 'object' && part in (cur as Record<string, unknown>)) cur = (cur as Record<string, unknown>)[part];
    else return undefined;
  }
  return cur;
}

export function setPath(obj: DetailsBag, path: string, value: unknown): DetailsBag {
  const [head, ...rest] = path.split('.');
  if (rest.length === 0) return { ...obj, [head]: value };
  const child = (obj[head] && typeof obj[head] === 'object' ? obj[head] : {}) as DetailsBag;
  return { ...obj, [head]: setPath(child, rest.join('.'), value) };
}

export function isEmptyValue(v: unknown): boolean {
  if (v === undefined || v === null || v === '') return true;
  if (Array.isArray(v)) return v.length === 0;
  return false;
}

// "first: second" lines to [{k1: first, k2: second}] and back
export function pairsToText(v: unknown, keys: [string, string]): string {
  if (!Array.isArray(v)) return '';
  return v
    .map((o) => {
      const r = o as Record<string, unknown>;
      const a = String(r[keys[0]] ?? '');
      const b = String(r[keys[1]] ?? '');
      return b ? `${a}: ${b}` : a;
    })
    .join('\n');
}
export function textToPairs(text: string, keys: [string, string]): Record<string, string>[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const i = l.indexOf(':');
      return i === -1 ? { [keys[0]]: l, [keys[1]]: '' } : { [keys[0]]: l.slice(0, i).trim(), [keys[1]]: l.slice(i + 1).trim() };
    });
}
export const linesToText = (v: unknown): string => (Array.isArray(v) ? v.map(String).join('\n') : '');
export const textToLines = (t: string): string[] => t.split('\n').map((l) => l.trim()).filter(Boolean);
export const namesToText = (v: unknown): string => (Array.isArray(v) ? v.map((o) => String((o as Record<string, unknown>).name ?? '')).join('\n') : '');
export const textToNames = (t: string): { name: string }[] => textToLines(t).map((name) => ({ name }));
