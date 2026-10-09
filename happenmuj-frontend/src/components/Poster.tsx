import { useState } from 'react';
import { clubCode, dayParts } from '../lib/format';
import { eventTypeLabel } from '../lib/constants';
import type { Category, EventCardData } from '../lib/types';

// Default poster. Every event without an uploaded image gets the same kind of artwork,
// generated from its own data: a colour pair per category and a shape chosen from the event id.

interface Palette { bg: string; a: string; b: string; fg: string }
const FG = '#f7f2e8';
const PALETTES: Record<Category, Palette> = {
  technical: { bg: '#16324f', a: '#4c9be8', b: '#f2c14e', fg: FG },
  cultural: { bg: '#5a1e2a', a: '#e56b5d', b: '#f6d8ae', fg: FG },
  debating: { bg: '#2b2f36', a: '#d9a441', b: '#8fa3b5', fg: FG },
  sports: { bg: '#134b3a', a: '#8bd450', b: '#f5f1dc', fg: FG },
  academic: { bg: '#2e4a4f', a: '#9fd8cb', b: '#f2e9d0', fg: FG },
  career: { bg: '#4a3b1f', a: '#e8b04a', b: '#f7efd8', fg: FG },
  hackathon: { bg: '#22252b', a: '#ff7a45', b: '#3ddbd9', fg: FG },
  workshop: { bg: '#1e4d5c', a: '#f7b538', b: '#e8f1f2', fg: FG },
  competition: { bg: '#5b2a1e', a: '#f4a259', b: '#fff1dc', fg: FG },
  seminar: { bg: '#3b2f2f', a: '#e0a96d', b: '#f4ede4', fg: FG },
  social: { bg: '#1f4d44', a: '#f28f3b', b: '#fce5c0', fg: FG },
  gaming: { bg: '#1a2e3b', a: '#ff5e5b', b: '#ffd6a5', fg: FG },
  other: { bg: '#2a2f34', a: '#b8c4cf', b: '#e6ecf1', fg: FG },
};

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function Motif({ kind, p }: { kind: number; p: Palette }) {
  switch (kind) {
    case 0:
      return (
        <g>
          <circle cx="270" cy="190" r="120" fill={p.a} />
          <rect y="318" width="400" height="14" fill={p.b} opacity="0.9" />
          <rect y="342" width="400" height="9" fill={p.b} opacity="0.7" />
          <rect y="362" width="400" height="5" fill={p.b} opacity="0.5" />
        </g>
      );
    case 1:
      return (
        <g>
          <path d="M400 500V250A250 250 0 00150 500z" fill={p.b} opacity="0.22" />
          {Array.from({ length: 7 }).flatMap((_, r) =>
            Array.from({ length: 6 }).map((__, c) => <circle key={`${r}-${c}`} cx={60 + c * 56} cy={96 + r * 44} r="6" fill={p.a} />),
          )}
        </g>
      );
    case 2:
      return (
        <g>
          <g transform="rotate(-24 200 250)">
            {Array.from({ length: 9 }).map((_, i) => <rect key={i} x="-120" y={-20 + i * 46} width="640" height="22" fill={p.a} opacity="0.85" />)}
          </g>
          <circle cx="116" cy="170" r="58" fill={p.b} />
        </g>
      );
    case 3:
      return (
        <g>
          <circle cx="200" cy="250" r="170" fill={p.a} />
          <circle cx="200" cy="250" r="126" fill={p.bg} />
          <circle cx="200" cy="250" r="84" fill={p.b} />
          <circle cx="200" cy="250" r="40" fill={p.bg} />
        </g>
      );
    case 4:
      return (
        <g>
          <rect x="40" y="96" width="170" height="170" fill={p.a} />
          <rect x="150" y="160" width="210" height="150" fill={p.b} opacity="0.88" />
          <rect x="88" y="230" width="120" height="120" fill={p.a} opacity="0.4" />
        </g>
      );
    default:
      return (
        <g fill="none" stroke={p.a} strokeWidth="16">
          <circle cx="262" cy="180" r="150" />
          <circle cx="262" cy="180" r="106" />
          <circle cx="262" cy="180" r="62" />
          <circle cx="262" cy="180" r="24" fill={p.b} stroke="none" />
        </g>
      );
  }
}

type PosterEvent = Pick<EventCardData, 'id' | 'category' | 'event_type' | 'club' | 'schedule' | 'poster_url'>;

export function Poster({ event, fit = 'contain' }: { event: PosterEvent; fit?: 'contain' | 'cover' }) {
  const [broken, setBroken] = useState(false);
  const className = `poster${fit === 'cover' ? ' poster--cover' : ''}`;

  if (event.poster_url && !broken) {
    return (
      <div className={className}>
        <img className="poster__img" src={event.poster_url} alt="" loading="lazy" decoding="async" onError={() => setBroken(true)} />
      </div>
    );
  }

  const p = PALETTES[event.category] ?? PALETTES.other;
  const kind = hash(event.id) % 6;
  const label = eventTypeLabel(event.event_type).toUpperCase();
  const size = Math.min(76, 300 / (label.length * 0.5));
  const d = dayParts(event.schedule.start);

  return (
    <div className={className}>
      <svg viewBox="0 0 400 500" preserveAspectRatio={fit === 'cover' ? 'xMidYMid slice' : 'xMidYMid meet'} aria-hidden="true" focusable="false">
        <rect width="400" height="500" fill={p.bg} />
        <Motif kind={kind} p={p} />
        <text x="28" y="56" fontSize="30" fontWeight="700" letterSpacing="1.500" fill={p.fg} style={{ fontFamily: 'var(--font-display)' }}>{clubCode(event.club.name)}</text>
        <text x="28" y="440" fontSize={size} fontWeight="800" textLength={Math.min(344, label.length * size * 0.55)} lengthAdjust="spacingAndGlyphs" fill={p.fg} style={{ fontFamily: 'var(--font-display)' }}>{label}</text>
        <text x="28" y="478" fontSize="26" fontWeight="600" letterSpacing="1" fill={p.fg} opacity="0.85" style={{ fontFamily: 'var(--font-display)' }}>{`${d.day} ${d.month.toUpperCase()}`}</text>
      </svg>
    </div>
  );
}

export const posterBackground = (category: Category): string => (PALETTES[category] ?? PALETTES.other).bg;
