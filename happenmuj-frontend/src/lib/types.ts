// Types mirror the API contract in the backend prompt (event card shape, section 6).

export type Category =
  | 'technical' | 'cultural' | 'debating' | 'sports' | 'academic' | 'career' | 'hackathon'
  | 'workshop' | 'competition' | 'seminar' | 'social' | 'gaming' | 'other';

export type EventType =
  | 'workshop' | 'competition' | 'hackathon' | 'sports_match' | 'cultural_show' | 'seminar' | 'social' | 'other';

export type EventStatus = 'draft' | 'pending_review' | 'published' | 'rejected' | 'cancelled';
export type FeeType = 'free' | 'fixed' | 'per_participant' | 'per_team' | 'not_specified';
export type TeamType = 'individual' | 'range' | 'fixed' | 'not_applicable' | 'not_specified';
export type RegPlatform = 'google_forms' | 'unstop' | 'devfolio' | 'website' | 'other';
export type Role = 'student' | 'club_admin' | 'platform_admin';

export interface ClubRef { id: string; name: string; slug: string }

export interface Club extends ClubRef {
  description: string;
  category: Category;
  verified: boolean;
  admin_ids: string[];
  requested_by?: string;
}

export interface Fee { type: FeeType; amount?: number | null; currency: 'INR'; display: string }
export interface Team { type: TeamType; min?: number | null; max?: number | null; display: string }

export interface Registration {
  required: boolean;
  platform: RegPlatform | null;
  deadline: string | null;
}

export interface EventCardData {
  id: string;
  title: string;
  one_liner: string;
  club: ClubRef;
  category: Category;
  event_type: EventType;
  tags: string[];
  poster_url: string | null;
  schedule: { start: string; end: string };
  venue: { name: string; building?: string | null };
  fee: Fee;
  team: Team;
  registration: Registration;
  registration_open: boolean;
  featured: boolean;
  status: EventStatus;
  stats: { saves: number; views: number };
  is_saved?: boolean;
}

export type DetailsBag = Record<string, unknown>;

export interface EventDetail extends EventCardData {
  description: string;
  details: DetailsBag;
  contact: { name: string; email: string } | null;
  registration: Registration & { url: string | null };
  venue: { name: string; building?: string | null; room?: string | null };
  rejection_reason?: string | null;
  cancel_reason?: string | null;
  published_at?: string | null;
}

export interface RankedEvent extends EventCardData {
  rank: number;
  score_breakdown: Record<string, number>;
  window: { saves: number; views: number; registration_clicks: number };
}

export interface TopEvents { items: RankedEvent[]; disclaimer: string }
export interface RankingConfig { weights: Record<string, number>; window_days: number }

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  interests: string[];
  preferred_categories: Category[];
  followed_club_ids: string[];
  managed_club_ids: string[];
}

export interface SavedItem {
  event: EventCardData;
  status: 'saved' | 'registration_initiated';
  saved_at: string;
  cancelled: boolean;
}

export interface Paged<T> { items: T[]; total: number; page: number; page_size: number }

export interface CatalogueResult extends Paged<EventCardData> {
  facets: { category: Record<string, number>; club: Record<string, number> };
}

export interface CatalogueParams {
  q?: string;
  categories: Category[];
  clubs: string[];
  date_from?: string;
  date_to?: string;
  sort: 'date' | 'popularity';
  page: number;
  page_size: number;
}

export type ReactionKind = 'like' | 'insightful';
export type PostScopeType = 'global' | 'event' | 'club';

export interface PostScope { type: PostScopeType; ref_id: string | null; ref_label?: string | null }
export interface Author { id: string; name: string }
export interface ReactionCounts { like: number; insightful: number }

export interface CommentData {
  id: string;
  post_id: string;
  parent_id: string | null;
  author: Author;
  body: string;
  created_at: string;
  reaction_counts: ReactionCounts;
  my_reaction: ReactionKind | null;
  status: 'active' | 'removed';
  replies?: CommentData[];
}

export interface Post {
  id: string;
  scope: PostScope;
  author: Author;
  title: string;
  body: string;
  created_at: string;
  comment_count: number;
  reaction_counts: ReactionCounts;
  my_reaction: ReactionKind | null;
  recent_comments: CommentData[];
  pinned: boolean;
  status: 'active' | 'removed';
}

export interface PostParams { scope?: PostScopeType; ref_id?: string; q?: string; page: number; page_size: number }

export interface EventInput {
  title: string;
  one_liner: string;
  description: string;
  club_id: string;
  category: Category;
  event_type: EventType;
  tags: string[];
  schedule: { start: string; end: string };
  venue: { name: string; building: string | null; room: string | null };
  fee: { type: FeeType; amount: number | null; currency: 'INR' };
  team: { type: TeamType; min: number | null; max: number | null };
  registration: { required: boolean; platform: RegPlatform | null; url: string | null; deadline: string | null };
  contact: { name: string; email: string } | null;
  details: DetailsBag;
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}
