import type { Category, EventType, FeeType, RegPlatform, TeamType } from './types';

export const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'technical', label: 'Technical' },
  { id: 'cultural', label: 'Cultural' },
  { id: 'debating', label: 'Debating' },
  { id: 'sports', label: 'Sports' },
  { id: 'academic', label: 'Academic' },
  { id: 'career', label: 'Career' },
  { id: 'hackathon', label: 'Hackathon' },
  { id: 'workshop', label: 'Workshop' },
  { id: 'competition', label: 'Competition' },
  { id: 'seminar', label: 'Seminar' },
  { id: 'social', label: 'Social' },
  { id: 'gaming', label: 'Gaming' },
  { id: 'other', label: 'Other' },
];

export const categoryLabel = (id: string): string => CATEGORIES.find((c) => c.id === id)?.label ?? id;

export const EVENT_TYPES: { id: EventType; label: string }[] = [
  { id: 'workshop', label: 'Workshop' },
  { id: 'competition', label: 'Competition' },
  { id: 'hackathon', label: 'Hackathon' },
  { id: 'sports_match', label: 'Sports match' },
  { id: 'cultural_show', label: 'Cultural show' },
  { id: 'seminar', label: 'Seminar' },
  { id: 'social', label: 'Social' },
  { id: 'other', label: 'Other' },
];
export const eventTypeLabel = (id: string): string => EVENT_TYPES.find((t) => t.id === id)?.label ?? id;

export const PLATFORMS: { id: RegPlatform; label: string }[] = [
  { id: 'google_forms', label: 'Google Forms' },
  { id: 'unstop', label: 'Unstop' },
  { id: 'devfolio', label: 'Devfolio' },
  { id: 'website', label: 'Club website' },
  { id: 'other', label: 'Other site' },
];
export const platformLabel = (id: string | null | undefined): string => PLATFORMS.find((p) => p.id === id)?.label ?? 'the organiser’s site';

export const FEE_TYPES: { id: FeeType; label: string }[] = [
  { id: 'not_specified', label: 'Not specified' },
  { id: 'free', label: 'Free' },
  { id: 'fixed', label: 'Fixed fee' },
  { id: 'per_participant', label: 'Per participant' },
  { id: 'per_team', label: 'Per team' },
];

export const TEAM_TYPES: { id: TeamType; label: string }[] = [
  { id: 'not_specified', label: 'Not specified' },
  { id: 'individual', label: 'Individual' },
  { id: 'range', label: 'Team, min to max members' },
  { id: 'fixed', label: 'Team, exact size' },
  { id: 'not_applicable', label: 'Not applicable' },
];

export const INTEREST_SUGGESTIONS = [
  'AI', 'Machine Learning', 'Web Development', 'Cloud', 'Robotics', 'Cybersecurity', 'Startups',
  'Hackathons', 'Music', 'Dance', 'Debate', 'Photography', 'Football', 'Cricket', 'Chess', 'Gaming',
];

/** Same weights the backend stores in `settings`; only used by the sample-data adapter. */
export const DEFAULT_RANKING = {
  weights: { saves: 0.3, views: 0.2, registration_clicks: 0.2, proximity: 0.2, urgency: 0.1 },
  window_days: 7,
};

export const RANKING_DISCLAIMER =
  'Ranked by what students saved, viewed and clicked in the last 7 days, and how soon the event is. It is not an endorsement by the university.';
