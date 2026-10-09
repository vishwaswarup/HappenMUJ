-- HappenMUJ modelled relationally (PostgreSQL), as a strict third-normal-form design:
-- no arrays, no JSON columns. The point is to show what the document model absorbs.
-- It is the SAME data as the MongoDB design: 9 collections + GridFS.
-- Verified to load and query on PostgreSQL 16 (see docs/SQL_COMPARISON.md).

-- ============================================================ people and clubs
CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    name          text NOT NULL,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role          text NOT NULL CHECK (role IN ('student', 'club_admin', 'platform_admin')),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE clubs (
    id           bigserial PRIMARY KEY,
    name         text NOT NULL,
    slug         text NOT NULL UNIQUE,
    description  text NOT NULL DEFAULT '',
    category     text NOT NULL,
    verified     boolean NOT NULL DEFAULT false,
    verified_at  timestamptz,
    verified_by  bigint REFERENCES users (id),
    requested_by bigint REFERENCES users (id),
    created_at   timestamptz NOT NULL DEFAULT now()
);
-- Mongo: users.interests / users.preferred_categories / users.followed_club_ids and clubs.admin_ids are embedded arrays.
CREATE TABLE user_interests            (user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE, interest text NOT NULL, PRIMARY KEY (user_id, interest));
CREATE TABLE user_preferred_categories (user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE, category text NOT NULL, PRIMARY KEY (user_id, category));
CREATE TABLE user_followed_clubs       (user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE, club_id bigint NOT NULL REFERENCES clubs (id) ON DELETE CASCADE, PRIMARY KEY (user_id, club_id));
CREATE TABLE club_admins               (club_id bigint NOT NULL REFERENCES clubs (id) ON DELETE CASCADE, user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE, PRIMARY KEY (club_id, user_id));

-- ============================================================ events (the 1:1 groups flatten into columns)
-- Mongo: GridFS (fs.files + fs.chunks). Here: a bytea table (or an external object store).
CREATE TABLE event_posters (
    id           bigserial PRIMARY KEY,
    content_type text NOT NULL CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
    data         bytea NOT NULL CHECK (octet_length(data) <= 5 * 1024 * 1024),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE events (
    id               bigserial PRIMARY KEY,
    title            text NOT NULL,
    one_liner        varchar(160) NOT NULL,
    description      text NOT NULL DEFAULT '',
    club_id          bigint NOT NULL REFERENCES clubs (id),
    creator_id       bigint NOT NULL REFERENCES users (id),
    category         text NOT NULL CHECK (category IN ('technical','cultural','debating','sports','academic','career','hackathon','workshop','competition','seminar','social','gaming','other')),
    event_type       text NOT NULL CHECK (event_type IN ('workshop','competition','hackathon','sports_match','cultural_show','seminar','social','other')),
    poster_id        bigint REFERENCES event_posters (id),
    start_at         timestamptz NOT NULL,
    end_at           timestamptz NOT NULL,
    venue_name       text NOT NULL,
    venue_building   text,
    venue_room       text,
    fee_type         text NOT NULL DEFAULT 'not_specified' CHECK (fee_type IN ('free','fixed','per_participant','per_team','not_specified')),
    fee_amount       numeric(10, 2) CHECK (fee_amount >= 0),
    fee_currency     char(3) NOT NULL DEFAULT 'INR',
    team_type        text NOT NULL DEFAULT 'not_specified' CHECK (team_type IN ('individual','range','fixed','not_applicable','not_specified')),
    team_min         int CHECK (team_min >= 1),
    team_max         int CHECK (team_max >= 1),
    reg_required     boolean NOT NULL DEFAULT false,
    reg_platform     text CHECK (reg_platform IN ('google_forms','unstop','devfolio','website','other')),
    reg_url          text CHECK (reg_url ~ '^https?://'),
    reg_deadline     timestamptz,
    contact_name     text,
    contact_email    text,
    status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','pending_review','published','rejected','cancelled')),
    rejection_reason text,
    cancel_reason    text,
    cancelled_at     timestamptz,
    is_featured      boolean NOT NULL DEFAULT false,
    featured_at      timestamptz,
    views            int NOT NULL DEFAULT 0,   -- Mongo: stats.* (computed pattern); in SQL you could also COUNT(*) per read
    saves            int NOT NULL DEFAULT 0,
    registration_clicks int NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz,
    CONSTRAINT end_after_start CHECK (end_at > start_at),
    -- The fee and team rules the Python models enforce, expressed declaratively:
    CONSTRAINT fee_amount_rule CHECK ((fee_type IN ('fixed','per_participant','per_team')) = (fee_amount IS NOT NULL)),
    CONSTRAINT team_size_rule CHECK (CASE team_type
        WHEN 'range' THEN team_min IS NOT NULL AND team_max IS NOT NULL AND team_min <= team_max
        WHEN 'fixed' THEN team_min IS NOT NULL AND team_min = team_max
        ELSE team_min IS NULL AND team_max IS NULL END)
);
CREATE TABLE event_tags (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, tag text NOT NULL, PRIMARY KEY (event_id, tag));
CREATE TABLE event_change_log (id bigserial PRIMARY KEY, event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, at timestamptz NOT NULL, by_user_id bigint NOT NULL REFERENCES users (id));
CREATE TABLE event_change_log_fields (change_id bigint NOT NULL REFERENCES event_change_log (id) ON DELETE CASCADE, field text NOT NULL, PRIMARY KEY (change_id, field));
-- "keep the last 20" has no one-operator equivalent: needs a trigger or a scheduled DELETE.

-- ============================================================ per-type details: 18 tables
-- Mongo: ONE embedded `details` sub-document, validated by a discriminated union.
-- workshop (3)
CREATE TABLE workshop_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, speaker_name text, speaker_bio text, duration_minutes int CHECK (duration_minutes > 0), bring_own_laptop boolean NOT NULL DEFAULT false);
CREATE TABLE workshop_topics (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, topic text NOT NULL, PRIMARY KEY (event_id, position));
CREATE TABLE workshop_prerequisites (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, item text NOT NULL, PRIMARY KEY (event_id, position));
-- competition (4)
CREATE TABLE competition_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, eligibility text);
CREATE TABLE competition_prizes (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, rank text NOT NULL, reward text NOT NULL, PRIMARY KEY (event_id, rank));
CREATE TABLE competition_rounds (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, name text NOT NULL, description text NOT NULL DEFAULT '', PRIMARY KEY (event_id, position));
CREATE TABLE competition_judging_criteria (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, criterion text NOT NULL, PRIMARY KEY (event_id, position));
-- hackathon (4)
CREATE TABLE hackathon_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, duration_hours int CHECK (duration_hours > 0), max_teams int CHECK (max_teams > 0));
CREATE TABLE hackathon_themes (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, theme text NOT NULL, PRIMARY KEY (event_id, position));
CREATE TABLE hackathon_tracks (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, track text NOT NULL, PRIMARY KEY (event_id, position));
CREATE TABLE hackathon_prizes (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, rank text NOT NULL, reward text NOT NULL, PRIMARY KEY (event_id, rank));
-- sports match (2)
CREATE TABLE sports_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, sport text, match_type text, format text);
CREATE TABLE sports_teams (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, name text NOT NULL, PRIMARY KEY (event_id, position));
-- cultural show (3)
CREATE TABLE cultural_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, auditions_required boolean NOT NULL DEFAULT false, audition_date timestamptz);
CREATE TABLE cultural_performances (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, title text NOT NULL, performer text, PRIMARY KEY (event_id, position));
CREATE TABLE cultural_artists (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, position int NOT NULL, artist text NOT NULL, PRIMARY KEY (event_id, position));
-- seminar (1)
CREATE TABLE seminar_details (event_id bigint PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE, speaker_name text, speaker_affiliation text, topic text, q_and_a_enabled boolean NOT NULL DEFAULT false);
-- social / other (1): a free-form dict is entity-attribute-value in a strict relational design (values become untyped text)
CREATE TABLE event_extra (event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE, key text NOT NULL, value text NOT NULL, PRIMARY KEY (event_id, key));

-- ============================================================ engagement
CREATE TABLE saved_events (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    event_id   bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    status     text NOT NULL DEFAULT 'saved' CHECK (status IN ('saved', 'registration_initiated')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, event_id)
    -- No event_start copy: the calendar JOINs events (Mongo keeps a denormalised copy to avoid the join).
);
CREATE TABLE event_interactions (
    id       bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    user_id  bigint REFERENCES users (id) ON DELETE SET NULL,
    type     text NOT NULL CHECK (type IN ('view', 'save', 'registration_click')),
    ts       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX event_interactions_event_type_ts ON event_interactions (event_id, type, ts);
-- Mongo expires these with a TTL index. PostgreSQL has none: needs pg_cron or an external job running
--   DELETE FROM event_interactions WHERE ts < now() - interval '90 days';

-- ============================================================ community
CREATE TABLE posts (
    id              bigserial PRIMARY KEY,
    -- Polymorphic scope. Mongo: scope {type, ref_id}. SQL keeps FK integrity only with one nullable FK per target + a CHECK.
    scope_type      text NOT NULL CHECK (scope_type IN ('global', 'event', 'club')),
    scope_event_id  bigint REFERENCES events (id),
    scope_club_id   bigint REFERENCES clubs (id),
    author_id       bigint NOT NULL REFERENCES users (id),
    title           text NOT NULL,
    body            text NOT NULL,
    pinned          boolean NOT NULL DEFAULT false,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT scope_matches_target CHECK (
        (scope_type = 'global' AND scope_event_id IS NULL AND scope_club_id IS NULL) OR
        (scope_type = 'event'  AND scope_event_id IS NOT NULL AND scope_club_id IS NULL) OR
        (scope_type = 'club'   AND scope_club_id  IS NOT NULL AND scope_event_id IS NULL))
);
CREATE TABLE post_tags (post_id bigint NOT NULL REFERENCES posts (id) ON DELETE CASCADE, tag text NOT NULL, PRIMARY KEY (post_id, tag));
CREATE TABLE comments (
    id         bigserial PRIMARY KEY,
    post_id    bigint NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    parent_id  bigint REFERENCES comments (id) ON DELETE CASCADE,  -- depth <= 2 needs a trigger; a CHECK cannot look at another row
    author_id  bigint NOT NULL REFERENCES users (id),
    body       text NOT NULL,
    status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX comments_post_created ON comments (post_id, created_at);
CREATE INDEX comments_parent ON comments (parent_id);
CREATE TABLE reactions (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    post_id    bigint REFERENCES posts (id) ON DELETE CASCADE,       -- polymorphic target again: one FK per target type
    comment_id bigint REFERENCES comments (id) ON DELETE CASCADE,
    kind       text NOT NULL CHECK (kind IN ('like', 'insightful')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT exactly_one_target CHECK ((post_id IS NULL) <> (comment_id IS NULL))
);
CREATE UNIQUE INDEX reactions_one_per_user_post    ON reactions (user_id, post_id)    WHERE post_id IS NOT NULL;
CREATE UNIQUE INDEX reactions_one_per_user_comment ON reactions (user_id, comment_id) WHERE comment_id IS NOT NULL;

-- ============================================================ configuration
CREATE TABLE ranking_settings (
    id          int PRIMARY KEY CHECK (id = 1),   -- singleton row
    w_saves     numeric NOT NULL DEFAULT 0.30,
    w_views     numeric NOT NULL DEFAULT 0.20,
    w_clicks    numeric NOT NULL DEFAULT 0.20,
    w_proximity numeric NOT NULL DEFAULT 0.20,
    w_urgency   numeric NOT NULL DEFAULT 0.10,
    window_days int NOT NULL DEFAULT 7
);
INSERT INTO ranking_settings (id) VALUES (1);

-- ============================================================ indexes that mirror the Mongo ones
CREATE INDEX events_status_start   ON events (status, start_at);
CREATE INDEX events_club_start     ON events (club_id, start_at);
CREATE INDEX events_category_start ON events (category, start_at);
CREATE INDEX events_featured       ON events (featured_at DESC) WHERE is_featured;            -- partial
CREATE INDEX events_fts ON events USING gin (to_tsvector('english', title || ' ' || one_liner || ' ' || description));
CREATE INDEX saved_events_user ON saved_events (user_id);
CREATE INDEX posts_scope_created ON posts (scope_type, scope_event_id, scope_club_id, created_at DESC);
