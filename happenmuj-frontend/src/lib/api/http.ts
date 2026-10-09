import { feeDisplay, teamDisplay } from '../rules';
import {
  ApiError,
  type CatalogueParams, type CatalogueResult, type Club, type CommentData, type EventCardData, type EventDetail,
  type EventStatus, type Paged, type Post, type PostParams, type RankingConfig, type SavedItem, type TopEvents, type User,
} from '../types';
import type { Api } from './api';

// Adapter for the FastAPI backend (see the backend prompt, section 5). Field names are normalised here,
// so the rest of the app never touches raw responses. If the backend differs, change this file only.

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function createHttpApi(baseUrl: string): Api {
  const base = baseUrl.replace(/\/$/, '');
  let token: string | null = null;
  const origin = (() => {
    try { return new URL(base, window.location.origin).origin; } catch { return ''; }
  })();

  const absolute = (u: string | null | undefined) => (u ? (u.startsWith('/') ? `${origin}${u}` : u) : null);

  async function req<T = Json>(method: string, path: string, o: { query?: Record<string, unknown>; body?: unknown; form?: FormData } = {}): Promise<T> {
    const url = new URL(`${base}${path}`, window.location.origin);
    for (const [k, v] of Object.entries(o.query ?? {})) {
      if (v === undefined || v === null || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
      else url.searchParams.set(k, String(v));
    }
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    let body: BodyInit | undefined;
    if (o.form) body = o.form;
    else if (o.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(o.body); }

    let res: Response;
    try {
      res = await fetch(url.toString(), { method, headers, body });
    } catch {
      throw new ApiError(0, 'network', 'Could not reach the HappenMUJ server. Check your connection and try again.');
    }
    if (res.status === 204) return undefined as T;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const err = data?.error ?? {};
      const detail = typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map((d: Json) => d.msg).join(' ') : '';
      throw new ApiError(res.status, err.code ?? `http_${res.status}`, err.message ?? detail ?? `Request failed (${res.status}).`);
    }
    return data as T;
  }

  const items = <T,>(r: unknown): T[] => (Array.isArray(r) ? (r as T[]) : ((r as Json)?.items ?? []));

  const card = (e: Json): EventCardData => ({
    id: String(e.id ?? e._id),
    title: e.title,
    one_liner: e.one_liner ?? '',
    club: e.club ?? { id: String(e.club_id ?? ''), name: e.club_snapshot?.name ?? '', slug: e.club_snapshot?.slug ?? '' },
    category: e.category,
    event_type: e.event_type ?? 'other',
    tags: e.tags ?? [],
    poster_url: absolute(e.poster_url),
    schedule: e.schedule,
    venue: { name: e.venue?.name ?? '', building: e.venue?.building ?? null },
    fee: { ...e.fee, display: e.fee?.display ?? feeDisplay(e.fee ?? { type: 'not_specified' }) },
    team: { ...e.team, display: e.team?.display ?? teamDisplay(e.team ?? { type: 'not_specified' }) },
    registration: { required: !!e.registration?.required, platform: e.registration?.platform ?? null, deadline: e.registration?.deadline ?? null },
    registration_open: !!e.registration_open,
    featured: typeof e.featured === 'object' ? !!e.featured?.is_featured : !!e.featured,
    status: e.status ?? 'published',
    stats: { saves: e.stats?.saves ?? 0, views: e.stats?.views ?? 0 },
    is_saved: e.is_saved,
  });
  const detail = (e: Json): EventDetail => ({
    ...card(e),
    description: e.description ?? '',
    details: e.details ?? {},
    contact: e.contact ?? null,
    registration: { ...card(e).registration, url: e.registration?.url ?? null },
    venue: { name: e.venue?.name ?? '', building: e.venue?.building ?? null, room: e.venue?.room ?? null },
    rejection_reason: e.rejection_reason ?? null,
    cancel_reason: e.cancel_reason ?? null,
    published_at: e.published_at ?? null,
  });
  const user = (u: Json): User => ({
    id: String(u.id ?? u._id), name: u.name, email: u.email, role: u.role,
    interests: u.interests ?? [], preferred_categories: u.preferred_categories ?? [],
    followed_club_ids: (u.followed_club_ids ?? []).map(String), managed_club_ids: (u.managed_club_ids ?? []).map(String),
  });
  const club = (c: Json): Club => ({
    id: String(c.id ?? c._id), name: c.name, slug: c.slug, description: c.description ?? '', category: c.category ?? 'other',
    verified: !!c.verified, admin_ids: (c.admin_ids ?? []).map(String), requested_by: c.requested_by ? String(c.requested_by) : undefined,
  });
  const author = (x: Json) => x.author ?? { id: String(x.author_id ?? ''), name: x.author_snapshot?.name ?? 'Student' };
  const comment = (c: Json): CommentData => ({
    id: String(c.id ?? c._id), post_id: String(c.post_id), parent_id: c.parent_id ? String(c.parent_id) : null, author: author(c),
    body: c.body, created_at: c.created_at, reaction_counts: { like: 0, insightful: 0, ...(c.reaction_counts ?? {}) },
    my_reaction: c.my_reaction ?? null, status: c.status ?? 'active', replies: c.replies?.map(comment),
  });
  const post = (p: Json): Post => ({
    id: String(p.id ?? p._id), scope: { type: p.scope?.type ?? 'global', ref_id: p.scope?.ref_id ? String(p.scope.ref_id) : null, ref_label: p.scope?.ref_label ?? null },
    author: author(p), title: p.title, body: p.body, created_at: p.created_at, comment_count: p.comment_count ?? 0,
    reaction_counts: { like: 0, insightful: 0, ...(p.reaction_counts ?? {}) }, my_reaction: p.my_reaction ?? null,
    recent_comments: (p.recent_comments ?? []).map((c: Json) => comment({ post_id: p.id, ...c })), pinned: !!p.pinned, status: p.status ?? 'active',
  });

  const api: Api = {
    mode: 'http',
    setToken(t) { token = t; },

    async login(email, password) {
      const r = await req('POST', '/auth/login', { body: { email, password } });
      token = r.access_token;
      return { token: token!, user: user(await req('GET', '/auth/me')) };
    },
    async register(input) {
      await req('POST', '/auth/register', { body: input });
      return api.login(input.email, input.password);
    },
    async me() { return user(await req('GET', '/auth/me')); },
    async updateProfile(patch) { return user(await req('PATCH', '/users/me', { body: patch })); },
    async followClub(id) { await req('POST', `/users/me/follow/${id}`); return api.me(); },
    async unfollowClub(id) { await req('DELETE', `/users/me/follow/${id}`); return api.me(); },

    async clubs(q) { return items<Json>(await req('GET', '/clubs', { query: { q, page_size: 50 } })).map(club); },

    async homeFeatured() { const r = await req('GET', '/home/featured'); return r && (r.id || r._id) ? card(r) : null; },
    async homeSuggested() {
      const r = await req('GET', '/home/suggested');
      return { items: items<Json>(r).map(card), personalised: !!(r as Json)?.personalised };
    },
    async homeTop(): Promise<TopEvents> {
      const r = await req('GET', '/home/top-events');
      return {
        items: items<Json>(r).map((e, i) => ({ ...card(e), rank: e.rank ?? i + 1, score_breakdown: e.score_breakdown ?? {}, window: e.window ?? { saves: 0, views: 0, registration_clicks: 0 } })),
        disclaimer: (r as Json)?.disclaimer ?? 'Ranked by student engagement. It is not an endorsement by the university.',
      };
    },
    async homeNext7() { return items<Json>(await req('GET', '/home/next-7-days')).map(card); },
    async homeTomorrow() { return items<Json>(await req('GET', '/home/tomorrow')).map(card); },
    async rankingConfig(): Promise<RankingConfig> {
      const r = await req('GET', '/home/top-events/config');
      return { weights: r.weights ?? {}, window_days: r.window_days ?? 7 };
    },

    async listEvents(p: CatalogueParams): Promise<CatalogueResult> {
      const r = await req('GET', '/events', {
        query: { q: p.q, category: p.categories, club: p.clubs, date_from: p.date_from, date_to: p.date_to, sort: p.sort, page: p.page, page_size: p.page_size },
      });
      return {
        items: items<Json>(r).map(card), total: r.total ?? 0, page: r.page ?? p.page, page_size: r.page_size ?? p.page_size,
        facets: { category: r.facets?.category ?? {}, club: r.facets?.club ?? {} },
      };
    },
    async getEvent(id) { return detail(await req('GET', `/events/${id}`)); },
    async recordView(id) { try { await req('POST', `/events/${id}/view`); } catch { /* views are best effort */ } },
    async registrationClick(id) { const r = await req('POST', `/events/${id}/registration-click`); return { url: r.url }; },

    async savedEvents(): Promise<SavedItem[]> {
      return items<Json>(await req('GET', '/saved-events')).map((r) => {
        const e = card(r.event ?? r);
        return { event: e, status: r.status === 'registration_initiated' ? 'registration_initiated' : 'saved', saved_at: r.created_at ?? r.saved_at ?? '', cancelled: r.cancelled ?? e.status === 'cancelled' };
      });
    },
    async saveEvent(id) { await req('POST', '/saved-events', { body: { event_id: id } }); },
    async unsaveEvent(id) { await req('DELETE', `/saved-events/${id}`); },

    async listPosts(p: PostParams): Promise<Paged<Post>> {
      const r = await req('GET', '/posts', { query: { scope: p.scope, ref_id: p.ref_id, q: p.q, page: p.page, page_size: p.page_size } });
      return { items: items<Json>(r).map(post), total: r.total ?? 0, page: r.page ?? p.page, page_size: r.page_size ?? p.page_size };
    },
    async getPost(id) { return post(await req('GET', `/posts/${id}`)); },
    async createPost(input) { return post(await req('POST', '/posts', { body: input })); },
    async deletePost(id) { await req('DELETE', `/posts/${id}`); },
    async listComments(postId) { return items<Json>(await req('GET', `/posts/${postId}/comments`, { query: { page_size: 50 } })).map((c) => comment({ post_id: postId, ...c })); },
    async addComment(postId, body, parentId) { return comment({ post_id: postId, ...(await req('POST', `/posts/${postId}/comments`, { body: { body, parent_id: parentId } })) }); },
    async deleteComment(id) { await req('DELETE', `/comments/${id}`); },
    async react(targetType, targetId, kind) {
      const r = await req('PUT', '/reactions', { body: { target_type: targetType, target_id: targetId, kind } });
      return r && 'my_reaction' in r ? { my_reaction: r.my_reaction } : {};
    },

    async myEvents(clubId) { return items<Json>(await req('GET', '/events/mine', { query: { club_id: clubId, page_size: 50 } })).map(detail); },
    async createEvent(input, poster) {
      const created = await req('POST', '/events', { body: input });
      if (poster) { const f = new FormData(); f.append('file', poster); await req('POST', `/events/${created.id ?? created._id}/poster`, { form: f }); }
      return detail(await req('GET', `/events/${created.id ?? created._id}`));
    },
    async updateEvent(id, input, poster) {
      await req('PATCH', `/events/${id}`, { body: input });
      if (poster) { const f = new FormData(); f.append('file', poster); await req('POST', `/events/${id}/poster`, { form: f }); }
      return detail(await req('GET', `/events/${id}`));
    },
    async submitEvent(id) { await req('POST', `/events/${id}/submit`); return detail(await req('GET', `/events/${id}`)); },
    async cancelEvent(id, reason) { await req('POST', `/events/${id}/cancel`, { body: { reason } }); return detail(await req('GET', `/events/${id}`)); },
    async deleteEvent(id) { await req('DELETE', `/events/${id}`); },
    async requestClub(name, description, category) { return club(await req('POST', '/clubs', { body: { name, description, category } })); },

    async adminEvents(status: EventStatus) { return items<Json>(await req('GET', '/admin/events', { query: { status, page_size: 50 } })).map(detail); },
    async adminApprove(id) { await req('POST', `/admin/events/${id}/approve`); },
    async adminReject(id, reason) { await req('POST', `/admin/events/${id}/reject`, { body: { reason } }); },
    async adminFeature(id, on) { await req(on ? 'POST' : 'DELETE', `/admin/events/${id}/feature`); },
    async adminClubs(status) {
      if (status === 'verified') return api.clubs();
      return items<Json>(await req('GET', '/admin/clubs', { query: { status: 'pending' } })).map(club);
    },
    async adminVerifyClub(id) { await req('POST', `/admin/clubs/${id}/verify`); },
  };
  return api;
}
