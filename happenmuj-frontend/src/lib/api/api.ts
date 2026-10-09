import type {
  CatalogueParams, CatalogueResult, Category, Club, CommentData, EventCardData, EventDetail, EventInput, EventStatus,
  Paged, Post, PostParams, PostScopeType, RankingConfig, ReactionKind, SavedItem, TopEvents, User,
} from '../types';

export interface NewPost { scope: { type: PostScopeType; ref_id: string | null }; title: string; body: string }
export interface ProfilePatch { name?: string; interests?: string[]; preferred_categories?: Category[] }
export interface RegisterInput { name: string; email: string; password: string; interests: string[] }

/** Everything the UI needs from a backend. Implemented by the sample-data adapter and the HTTP adapter. */
export interface Api {
  readonly mode: 'mock' | 'http';
  setToken(token: string | null): void;

  // auth and profile
  login(email: string, password: string): Promise<{ token: string; user: User }>;
  register(input: RegisterInput): Promise<{ token: string; user: User }>;
  me(): Promise<User>;
  updateProfile(patch: ProfilePatch): Promise<User>;
  followClub(clubId: string): Promise<User>;
  unfollowClub(clubId: string): Promise<User>;

  // reference data
  clubs(q?: string): Promise<Club[]>;

  // home sections
  homeFeatured(): Promise<EventCardData | null>;
  homeSuggested(): Promise<{ items: EventCardData[]; personalised: boolean }>;
  homeTop(): Promise<TopEvents>;
  homeNext7(): Promise<EventCardData[]>;
  homeTomorrow(): Promise<EventCardData[]>;
  rankingConfig(): Promise<RankingConfig>;

  // events
  listEvents(params: CatalogueParams): Promise<CatalogueResult>;
  getEvent(id: string): Promise<EventDetail>;
  recordView(id: string): Promise<void>;
  registrationClick(id: string): Promise<{ url: string }>;

  // saved events
  savedEvents(): Promise<SavedItem[]>;
  saveEvent(eventId: string): Promise<void>;
  unsaveEvent(eventId: string): Promise<void>;

  // community
  listPosts(params: PostParams): Promise<Paged<Post>>;
  getPost(id: string): Promise<Post>;
  createPost(input: NewPost): Promise<Post>;
  deletePost(id: string): Promise<void>;
  listComments(postId: string): Promise<CommentData[]>;
  addComment(postId: string, body: string, parentId: string | null): Promise<CommentData>;
  deleteComment(id: string): Promise<void>;
  react(targetType: 'post' | 'comment', targetId: string, kind: ReactionKind): Promise<{ my_reaction?: ReactionKind | null }>;

  // club admin
  myEvents(clubId?: string): Promise<EventDetail[]>;
  createEvent(input: EventInput, poster?: File | null): Promise<EventDetail>;
  updateEvent(id: string, input: EventInput, poster?: File | null): Promise<EventDetail>;
  submitEvent(id: string): Promise<EventDetail>;
  cancelEvent(id: string, reason: string): Promise<EventDetail>;
  deleteEvent(id: string): Promise<void>;
  requestClub(name: string, description: string, category: Category): Promise<Club>;

  // platform admin
  adminEvents(status: EventStatus): Promise<EventDetail[]>;
  adminApprove(id: string): Promise<void>;
  adminReject(id: string, reason: string): Promise<void>;
  adminFeature(id: string, on: boolean): Promise<void>;
  adminClubs(status: 'pending' | 'verified'): Promise<Club[]>;
  adminVerifyClub(id: string): Promise<void>;
}
