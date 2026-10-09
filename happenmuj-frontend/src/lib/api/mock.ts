import { categoryLabel, DEFAULT_RANKING, RANKING_DISCLAIMER } from '../constants';
import { feeDisplay, registrationOpen, teamDisplay } from '../rules';
import { inRange, next7DaysRange, tomorrowRange, MS } from '../time';
import {
  ApiError,
  type CatalogueParams, type CatalogueResult, type Category, type Club, type CommentData, type EventCardData,
  type EventDetail, type EventInput, type EventStatus, type Paged, type Post, type PostParams, type RankedEvent,
  type ReactionKind, type SavedItem, type User,
} from '../types';
import type { Api, NewPost, ProfilePatch, RegisterInput } from './api';
import { buildSeed, type MockEvent, type StoredUser } from './mockData';

export interface MockOptions {
  /** Simulated network delay range in ms. Tests use [0, 0]. */
  latencyMs?: [number, number];
  now?: () => Date;
  seed?: Date;
}

const t = (iso: string) => new Date(iso).getTime();
const clone = <T,>(v: T): T => structuredClone(v);

export function createMockApi(opts: MockOptions = {}): Api {
  const clock = opts.now ?? (() => new Date());
  const db = buildSeed(opts.seed ?? clock());
  const [minLag, maxLag] = opts.latencyMs ?? [0, 0];
  let token: string | null = null;
  let seq = 100;

  const wait = async () => {
    if (maxLag > 0) await new Promise((r) => setTimeout(r, minLag + Math.random() * (maxLag - minLag)));
  };
  const fail = (status: number, code: string, message: string): never => { throw new ApiError(status, code, message); };

  const current = (): StoredUser | undefined => (token ? db.users.find((u) => `tok-${u.id}` === token) : undefined);
  const needUser = (): StoredUser => current() ?? fail(401, 'unauthenticated', 'Sign in to continue.');
  const publicUser = (u: StoredUser): User => {
    const { password: _password, ...rest } = u;
    return clone({ ...rest, managed_club_ids: db.clubs.filter((c) => c.admin_ids.includes(u.id)).map((c) => c.id) });
  };
  const clubOf = (id: string) => db.clubs.find((c) => c.id === id);
  const isPublic = (e: MockEvent) => e.status === 'published';
  const isUpcoming = (e: MockEvent) => t(e.schedule.start) > clock().getTime();
  const savedList = (uid?: string) => (uid ? db.saved[uid] ?? (db.saved[uid] = []) : []);

  const toCard = (e: MockEvent): EventCardData => {
    const now = clock();
    return {
      id: e.id, title: e.title, one_liner: e.one_liner, club: clone(e.club), category: e.category, event_type: e.event_type,
      tags: [...e.tags], poster_url: e.poster_url, schedule: { ...e.schedule },
      venue: { name: e.venue.name, building: e.venue.building ?? null },
      fee: { ...e.fee }, team: { ...e.team },
      registration: { required: e.registration.required, platform: e.registration.platform, deadline: e.registration.deadline },
      registration_open: registrationOpen(e.registration, e.schedule.start, now) && e.status === 'published',
      featured: e.featured, status: e.status, stats: { ...e.stats },
      is_saved: savedList(current()?.id).some((s) => s.event_id === e.id),
    };
  };
  const toDetail = (e: MockEvent): EventDetail => ({
    ...toCard(e), description: e.description, details: clone(e.details), contact: clone(e.contact),
    registration: { ...e.registration }, venue: { ...e.venue }, rejection_reason: e.rejection_reason, cancel_reason: e.cancel_reason, published_at: e.published_at,
  });
  const findEvent = (id: string): MockEvent => db.events.find((e) => e.id === id) ?? fail(404, 'not_found', 'That event does not exist.');
  const byStart = (a: MockEvent, b: MockEvent) => t(a.schedule.start) - t(b.schedule.start);
  const engagement = (e: MockEvent) => e.win.saves * 3 + e.win.registration_clicks * 2 + e.win.views;

  // ---------- catalogue ----------
  const haystack = (e: MockEvent) =>
    [e.title, e.tags.join(' '), e.club.name, e.one_liner, e.venue.name, e.venue.building ?? '', e.description, categoryLabel(e.category)].join(' ').toLowerCase();

  const matches = (e: MockEvent, p: CatalogueParams, skip?: 'category' | 'club'): boolean => {
    if (!isPublic(e) || !isUpcoming(e)) return false;
    if (p.q) {
      const h = haystack(e);
      if (!p.q.toLowerCase().split(/\s+/).filter(Boolean).every((tok) => h.includes(tok))) return false;
    }
    if (skip !== 'category' && p.categories.length && !p.categories.includes(e.category)) return false;
    if (skip !== 'club' && p.clubs.length && !p.clubs.some((c) => c === e.club.id || c === e.club.slug)) return false;
    if (p.date_from && t(e.schedule.start) < t(p.date_from)) return false;
    if (p.date_to && t(e.schedule.start) >= t(p.date_to)) return false;
    return true;
  };

  const count = <K extends string>(list: MockEvent[], key: (e: MockEvent) => K) => {
    const out: Record<string, number> = {};
    for (const e of list) out[key(e)] = (out[key(e)] ?? 0) + 1;
    return out;
  };

  // ---------- ranking ----------
  const eligibleForRanking = (): MockEvent[] => {
    const now = clock().getTime();
    return db.events.filter((e) => isPublic(e) && t(e.schedule.start) > now && !(e.registration.required && e.registration.deadline && t(e.registration.deadline) < now));
  };

  const rankEvents = (): RankedEvent[] => {
    const now = clock();
    const w = db.ranking.weights;
    const pool = eligibleForRanking();
    const max = (k: 'saves' | 'views' | 'registration_clicks') => Math.max(0, ...pool.map((e) => e.win[k]));
    const mSaves = max('saves'), mViews = max('views'), mClicks = max('registration_clicks');
    const norm = (v: number, m: number) => (m > 0 ? v / m : 0);
    return pool
      .map((e) => {
        const days = (t(e.schedule.start) - now.getTime()) / MS.DAY;
        const open = registrationOpen(e.registration, e.schedule.start, now);
        const left = e.registration.deadline ? t(e.registration.deadline) - now.getTime() : Infinity;
        const breakdown = {
          saves: w.saves * norm(e.win.saves, mSaves),
          views: w.views * norm(e.win.views, mViews),
          registration_clicks: w.registration_clicks * norm(e.win.registration_clicks, mClicks),
          proximity: w.proximity * Math.exp(-days / 7),
          urgency: w.urgency * (open && left <= 72 * MS.HOUR ? 1 : open ? 0.5 : 0),
        };
        const score = Object.values(breakdown).reduce((a, b) => a + b, 0);
        return { e, score, breakdown };
      })
      .sort((a, b) => b.score - a.score || byStart(a.e, b.e))
      .slice(0, 10)
      .map(({ e, breakdown }, i) => ({ ...toCard(e), rank: i + 1, score_breakdown: breakdown, window: { ...e.win } }));
  };

  const suggest = (u?: StoredUser): { items: EventCardData[]; personalised: boolean } => {
    const now = clock();
    const pool = eligibleForRanking();
    const hasSignals = !!u && (u.interests.length > 0 || u.preferred_categories.length > 0 || u.followed_club_ids.length > 0);
    if (!u || !hasSignals) {
      return { items: pool.sort((a, b) => engagement(b) - engagement(a) || byStart(a, b)).slice(0, 12).map(toCard), personalised: false };
    }
    const mine = new Set(u.interests.map((i) => i.toLowerCase()));
    const savedIds = new Set(savedList(u.id).map((s) => s.event_id));
    const scored = pool
      .filter((e) => !savedIds.has(e.id))
      .map((e) => {
        const overlap = e.tags.filter((tag) => mine.has(tag.toLowerCase())).length;
        const interest = overlap / Math.max(1, mine.size);
        const category = u.preferred_categories.includes(e.category) ? 1 : 0;
        const club = u.followed_club_ids.includes(e.club.id) ? 1 : 0;
        const days = (t(e.schedule.start) - now.getTime()) / MS.DAY;
        const left = e.registration.deadline ? t(e.registration.deadline) - now.getTime() : Infinity;
        const deadline = registrationOpen(e.registration, e.schedule.start, now) && left <= 5 * MS.DAY ? 1 : 0;
        return { e, score: 0.35 * interest + 0.2 * category + 0.2 * club + 0.15 * Math.exp(-days / 10) + 0.1 * deadline };
      })
      .sort((a, b) => b.score - a.score || byStart(a.e, b.e));
    return { items: scored.slice(0, 12).map((s) => toCard(s.e)), personalised: true };
  };

  // ---------- community helpers ----------
  const reactionKey = (uid: string, type: string, id: string) => `${uid}|${type}|${id}`;
  const myReaction = (type: 'post' | 'comment', id: string): ReactionKind | null => {
    const u = current();
    return u ? db.reactions[reactionKey(u.id, type, id)] ?? null : null;
  };
  const toPost = (p: (typeof db.posts)[number]): Post => ({
    ...clone(p),
    my_reaction: myReaction('post', p.id),
    recent_comments: db.comments
      .filter((c) => c.post_id === p.id && c.status === 'active')
      .sort((a, b) => t(a.created_at) - t(b.created_at))
      .slice(-3)
      .map((c) => ({ ...clone(c), my_reaction: myReaction('comment', c.id) })),
  });
  const refLabel = (type: string, ref: string | null) =>
    type === 'event' ? db.events.find((e) => e.id === ref)?.title ?? null : type === 'club' ? clubOf(ref ?? '')?.name ?? null : null;

  const canManage = (u: StoredUser, clubId: string) => u.role === 'platform_admin' || (u.role === 'club_admin' && !!clubOf(clubId)?.admin_ids.includes(u.id));
  const applyInput = (e: MockEvent, input: EventInput) => {
    const club = clubOf(input.club_id) ?? fail(400, 'invalid_club', 'Choose a club.');
    const fee = { ...input.fee };
    const team = { ...input.team };
    Object.assign(e, {
      title: input.title, one_liner: input.one_liner, description: input.description, club_id: club.id,
      club: { id: club.id, name: club.name, slug: club.slug }, category: input.category, event_type: input.event_type, tags: input.tags,
      schedule: { ...input.schedule }, venue: { ...input.venue },
      fee: { ...fee, display: feeDisplay(fee) }, team: { ...team, display: teamDisplay(team) },
      registration: { ...input.registration }, contact: input.contact, details: input.details,
    });
  };

  const api: Api = {
    mode: 'mock',
    setToken(value) { token = value; },

    // ----- auth -----
    async login(email, password) {
      await wait();
      const u = db.users.find((x) => x.email === email.trim().toLowerCase() && x.password === password);
      if (!u) fail(401, 'invalid_credentials', 'That email and password do not match.');
      token = `tok-${u!.id}`;
      return { token, user: publicUser(u!) };
    },
    async register(input: RegisterInput) {
      await wait();
      const email = input.email.trim().toLowerCase();
      if (db.users.some((u) => u.email === email)) fail(409, 'email_taken', 'An account with this email already exists. Sign in instead.');
      if (input.password.length < 8) fail(422, 'weak_password', 'Use a password with at least 8 characters.');
      const u: StoredUser = {
        id: `u-${++seq}`, name: input.name.trim(), email, role: 'student', password: input.password,
        interests: input.interests, preferred_categories: [], followed_club_ids: [], managed_club_ids: [],
      };
      db.users.push(u);
      token = `tok-${u.id}`;
      return { token, user: publicUser(u) };
    },
    async me() { await wait(); return publicUser(needUser()); },
    async updateProfile(patch: ProfilePatch) {
      await wait();
      const u = needUser();
      if (patch.name !== undefined) u.name = patch.name.trim() || u.name;
      if (patch.interests) u.interests = patch.interests;
      if (patch.preferred_categories) u.preferred_categories = patch.preferred_categories;
      return publicUser(u);
    },
    async followClub(id) {
      await wait();
      const u = needUser();
      if (!clubOf(id)?.verified) fail(404, 'not_found', 'That club does not exist.');
      if (!u.followed_club_ids.includes(id)) u.followed_club_ids.push(id);
      return publicUser(u);
    },
    async unfollowClub(id) {
      await wait();
      const u = needUser();
      u.followed_club_ids = u.followed_club_ids.filter((c) => c !== id);
      return publicUser(u);
    },

    // ----- reference -----
    async clubs(q) {
      await wait();
      const needle = q?.toLowerCase().trim();
      return clone(db.clubs.filter((c) => c.verified && (!needle || c.name.toLowerCase().includes(needle))).sort((a, b) => a.name.localeCompare(b.name)));
    },

    // ----- home -----
    async homeFeatured() {
      await wait();
      const pool = db.events.filter((e) => isPublic(e) && isUpcoming(e));
      const featured = pool.filter((e) => e.featured_at).sort((a, b) => t(b.featured_at!) - t(a.featured_at!))[0];
      const fallback = pool.filter((e) => registrationOpen(e.registration, e.schedule.start, clock())).sort(byStart)[0] ?? pool.sort(byStart)[0];
      const pick = featured ?? fallback;
      return pick ? toCard(pick) : null;
    },
    async homeSuggested() { await wait(); return suggest(current()); },
    async homeTop() { await wait(); return { items: rankEvents(), disclaimer: RANKING_DISCLAIMER }; },
    async homeNext7() {
      await wait();
      const r = next7DaysRange(clock());
      return db.events.filter((e) => isPublic(e) && inRange(new Date(e.schedule.start), r)).sort(byStart).map(toCard);
    },
    async homeTomorrow() {
      await wait();
      const r = tomorrowRange(clock());
      return db.events.filter((e) => isPublic(e) && inRange(new Date(e.schedule.start), r)).sort(byStart).map(toCard);
    },
    async rankingConfig() { await wait(); return clone(db.ranking ?? DEFAULT_RANKING); },

    // ----- events -----
    async listEvents(p): Promise<CatalogueResult> {
      await wait();
      const base = db.events.filter((e) => matches(e, p));
      const sorted = [...base].sort(p.sort === 'popularity' ? (a, b) => engagement(b) - engagement(a) || byStart(a, b) : byStart);
      const start = (p.page - 1) * p.page_size;
      return {
        items: sorted.slice(start, start + p.page_size).map(toCard),
        total: sorted.length, page: p.page, page_size: p.page_size,
        facets: {
          category: count(db.events.filter((e) => matches(e, p, 'category')), (e) => e.category),
          club: count(db.events.filter((e) => matches(e, p, 'club')), (e) => e.club.id),
        },
      };
    },
    async getEvent(id) {
      await wait();
      const e = findEvent(id);
      const u = current();
      const visible = e.status === 'published' || e.status === 'cancelled' || (!!u && canManage(u, e.club_id));
      if (!visible) fail(404, 'not_found', 'That event does not exist.');
      return toDetail(e);
    },
    async recordView(id) {
      const e = db.events.find((x) => x.id === id);
      if (e && isPublic(e)) { e.stats.views++; e.win.views++; }
    },
    async registrationClick(id) {
      await wait();
      const e = findEvent(id);
      if (!e.registration.required || !e.registration.url) fail(400, 'no_registration', 'This event does not use online registration.');
      e.win.registration_clicks++;
      const u = current();
      const s = savedList(u?.id).find((x) => x.event_id === id);
      if (s) s.status = 'registration_initiated';
      return { url: e.registration.url! };
    },

    // ----- saved -----
    async savedEvents(): Promise<SavedItem[]> {
      await wait();
      const u = needUser();
      return savedList(u.id)
        .map((s) => ({ s, e: db.events.find((x) => x.id === s.event_id) }))
        .filter((x): x is { s: (typeof x)['s']; e: MockEvent } => !!x.e)
        .sort((a, b) => byStart(a.e, b.e))
        .map(({ s, e }) => ({ event: toCard(e), status: s.status, saved_at: s.saved_at, cancelled: e.status === 'cancelled' }));
    },
    async saveEvent(eventId) {
      await wait();
      const u = needUser();
      const e = findEvent(eventId);
      if (!isPublic(e)) fail(404, 'not_found', 'That event cannot be saved.');
      const list = savedList(u.id);
      if (list.some((s) => s.event_id === eventId)) return; // idempotent
      list.push({ event_id: eventId, status: 'saved', saved_at: clock().toISOString() });
      e.stats.saves++;
      e.win.saves++;
    },
    async unsaveEvent(eventId) {
      await wait();
      const u = needUser();
      const list = savedList(u.id);
      const i = list.findIndex((s) => s.event_id === eventId);
      if (i === -1) return;
      list.splice(i, 1);
      const e = db.events.find((x) => x.id === eventId);
      if (e) { e.stats.saves = Math.max(0, e.stats.saves - 1); e.win.saves = Math.max(0, e.win.saves - 1); }
    },

    // ----- community -----
    async listPosts(p: PostParams): Promise<Paged<Post>> {
      await wait();
      const q = p.q?.toLowerCase().trim();
      const rows = db.posts
        .filter((x) => x.status === 'active')
        .filter((x) => !p.scope || x.scope.type === p.scope)
        .filter((x) => !p.ref_id || x.scope.ref_id === p.ref_id)
        .filter((x) => !q || `${x.title} ${x.body}`.toLowerCase().includes(q))
        .sort((a, b) => Number(b.pinned) - Number(a.pinned) || t(b.created_at) - t(a.created_at));
      const start = (p.page - 1) * p.page_size;
      return { items: rows.slice(start, start + p.page_size).map(toPost), total: rows.length, page: p.page, page_size: p.page_size };
    },
    async getPost(id) {
      await wait();
      const p = db.posts.find((x) => x.id === id && x.status === 'active') ?? fail(404, 'not_found', 'That discussion was removed or does not exist.');
      return toPost(p);
    },
    async createPost(input: NewPost) {
      await wait();
      const u = needUser();
      if (input.title.trim().length < 3) fail(422, 'invalid', 'Add a title of at least 3 characters.');
      if (input.scope.type !== 'global' && !refLabel(input.scope.type, input.scope.ref_id)) fail(422, 'invalid_scope', 'Choose where this discussion belongs.');
      const post = {
        id: `p${++seq}`, scope: { type: input.scope.type, ref_id: input.scope.type === 'global' ? null : input.scope.ref_id, ref_label: refLabel(input.scope.type, input.scope.ref_id) },
        author: { id: u.id, name: u.name }, title: input.title.trim(), body: input.body.trim(), created_at: clock().toISOString(),
        comment_count: 0, reaction_counts: { like: 0, insightful: 0 }, pinned: false, status: 'active' as const,
      };
      db.posts.unshift(post);
      return toPost(post);
    },
    async deletePost(id) {
      await wait();
      const u = needUser();
      const p = db.posts.find((x) => x.id === id) ?? fail(404, 'not_found', 'That discussion does not exist.');
      if (p.author.id !== u.id && u.role !== 'platform_admin') fail(403, 'forbidden', 'You can only delete your own discussions.');
      p.status = 'removed';
    },
    async listComments(postId) {
      await wait();
      const all = db.comments.filter((c) => c.post_id === postId).sort((a, b) => t(a.created_at) - t(b.created_at))
        .map((c) => ({ ...clone(c), my_reaction: myReaction('comment', c.id) }));
      const top = all.filter((c) => !c.parent_id);
      return top
        .map((c) => ({ ...c, replies: all.filter((r) => r.parent_id === c.id) }))
        .filter((c) => c.status === 'active' || (c.replies?.some((r) => r.status === 'active') ?? false))
        .map((c) => ({ ...c, replies: c.replies?.filter((r) => r.status === 'active') }));
    },
    async addComment(postId, body, parentId) {
      await wait();
      const u = needUser();
      const post = db.posts.find((p) => p.id === postId && p.status === 'active') ?? fail(404, 'not_found', 'That discussion does not exist.');
      if (!body.trim()) fail(422, 'invalid', 'Write something before posting.');
      let parent = parentId ? db.comments.find((c) => c.id === parentId) : undefined;
      if (parent?.parent_id) parent = db.comments.find((c) => c.id === parent!.parent_id); // threads stop at two levels
      const c: CommentData = {
        id: `cm${++seq}`, post_id: postId, parent_id: parent?.id ?? null, author: { id: u.id, name: u.name }, body: body.trim(),
        created_at: clock().toISOString(), reaction_counts: { like: 0, insightful: 0 }, my_reaction: null, status: 'active',
      };
      db.comments.push(c);
      post.comment_count++;
      return clone(c);
    },
    async deleteComment(id) {
      await wait();
      const u = needUser();
      const c = db.comments.find((x) => x.id === id) ?? fail(404, 'not_found', 'That comment does not exist.');
      if (c.author.id !== u.id && u.role !== 'platform_admin') fail(403, 'forbidden', 'You can only delete your own comments.');
      if (c.status === 'active') {
        c.status = 'removed';
        const post = db.posts.find((p) => p.id === c.post_id);
        if (post) post.comment_count = Math.max(0, post.comment_count - 1);
      }
    },
    async react(targetType, targetId, kind) {
      await wait();
      const u = needUser();
      const target = targetType === 'post' ? db.posts.find((p) => p.id === targetId) : db.comments.find((c) => c.id === targetId);
      if (!target) fail(404, 'not_found', 'That item does not exist.');
      const key = reactionKey(u.id, targetType, targetId);
      const prev = db.reactions[key];
      const counts = target!.reaction_counts;
      if (prev) counts[prev] = Math.max(0, counts[prev] - 1);
      if (prev === kind) { delete db.reactions[key]; return { my_reaction: null }; }
      db.reactions[key] = kind;
      counts[kind]++;
      return { my_reaction: kind };
    },

    // ----- club admin -----
    async myEvents(clubId) {
      await wait();
      const u = needUser();
      if (u.role === 'student') fail(403, 'forbidden', 'Only club admins can manage events.');
      return db.events
        .filter((e) => canManage(u, e.club_id) && (!clubId || e.club_id === clubId))
        .sort((a, b) => t(b.schedule.start) - t(a.schedule.start))
        .map(toDetail);
    },
    async createEvent(input, poster) {
      await wait();
      const u = needUser();
      if (!canManage(u, input.club_id)) fail(403, 'forbidden', 'You can only create events for clubs you manage.');
      if (!clubOf(input.club_id)?.verified) fail(403, 'club_unverified', 'This club has not been verified yet.');
      const e = { id: `e${++seq}`, created_by: u.id, status: 'draft' as EventStatus, poster_url: null, featured: false, featured_at: null, stats: { saves: 0, views: 0 },
        win: { saves: 0, views: 0, registration_clicks: 0 }, rejection_reason: null, cancel_reason: null, published_at: null, registration_open: false } as unknown as MockEvent;
      applyInput(e, input);
      if (poster && typeof URL.createObjectURL === 'function') e.poster_url = URL.createObjectURL(poster);
      db.events.push(e);
      return toDetail(e);
    },
    async updateEvent(id, input, poster) {
      await wait();
      const u = needUser();
      const e = findEvent(id);
      if (!canManage(u, e.club_id)) fail(403, 'forbidden', 'You can only edit events for clubs you manage.');
      if (e.status === 'cancelled') fail(409, 'cancelled', 'A cancelled event cannot be edited.');
      applyInput(e, input);
      if (poster && typeof URL.createObjectURL === 'function') e.poster_url = URL.createObjectURL(poster);
      return toDetail(e);
    },
    async submitEvent(id) {
      await wait();
      const u = needUser();
      const e = findEvent(id);
      if (!canManage(u, e.club_id)) fail(403, 'forbidden', 'You can only submit events for clubs you manage.');
      if (e.status !== 'draft' && e.status !== 'rejected') fail(409, 'invalid_state', 'Only drafts and rejected events can be submitted.');
      e.status = 'pending_review';
      e.rejection_reason = null;
      return toDetail(e);
    },
    async cancelEvent(id, reason) {
      await wait();
      const u = needUser();
      const e = findEvent(id);
      if (!canManage(u, e.club_id)) fail(403, 'forbidden', 'You can only cancel events for clubs you manage.');
      if (e.status !== 'published') fail(409, 'invalid_state', 'Only published events can be cancelled.');
      e.status = 'cancelled';
      e.cancel_reason = reason.trim() || 'The organisers cancelled this event.';
      return toDetail(e);
    },
    async deleteEvent(id) {
      await wait();
      const u = needUser();
      const e = findEvent(id);
      if (!canManage(u, e.club_id)) fail(403, 'forbidden', 'You can only delete events for clubs you manage.');
      if (e.status !== 'draft') fail(409, 'invalid_state', 'Only drafts can be deleted. Cancel a published event instead.');
      db.events.splice(db.events.indexOf(e), 1);
    },
    async requestClub(name, description, category: Category) {
      await wait();
      const u = needUser();
      const club: Club = { id: `c-${++seq}`, name: name.trim(), slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'), description, category, verified: false, admin_ids: [], requested_by: u.id };
      db.clubs.push(club);
      return clone(club);
    },

    // ----- platform admin -----
    async adminEvents(status) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      return db.events.filter((e) => e.status === status).sort(byStart).map(toDetail);
    },
    async adminApprove(id) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      const e = findEvent(id);
      if (e.status !== 'pending_review') fail(409, 'invalid_state', 'Only events waiting for review can be approved.');
      e.status = 'published';
      e.published_at = clock().toISOString();
    },
    async adminReject(id, reason) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      const e = findEvent(id);
      if (e.status !== 'pending_review') fail(409, 'invalid_state', 'Only events waiting for review can be rejected.');
      if (!reason.trim()) fail(422, 'reason_required', 'Tell the club why the event was rejected.');
      e.status = 'rejected';
      e.rejection_reason = reason.trim();
    },
    async adminFeature(id, on) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      const e = findEvent(id);
      if (e.status !== 'published') fail(409, 'invalid_state', 'Only published events can be featured.');
      e.featured = on;
      e.featured_at = on ? clock().toISOString() : null;
    },
    async adminClubs(status) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      return clone(db.clubs.filter((c) => c.verified === (status === 'verified')));
    },
    async adminVerifyClub(id) {
      await wait();
      if (needUser().role !== 'platform_admin') fail(403, 'forbidden', 'Platform admins only.');
      const c = clubOf(id) ?? fail(404, 'not_found', 'That club does not exist.');
      c.verified = true;
      if (c.requested_by && !c.admin_ids.includes(c.requested_by)) {
        c.admin_ids.push(c.requested_by);
        const requester = db.users.find((u) => u.id === c.requested_by);
        if (requester && requester.role === 'student') requester.role = 'club_admin';
      }
    },
  };
  return api;
}
