-- Queries from docs/SQL_COMPARISON.md. Run with psql variables, e.g.:
--   psql -v now="'2026-10-09T06:30:00Z'" -v event_id=1 -v post_id=1 -f queries.sql

-- Q1: one workshop event, fully assembled (the application must already know it is a workshop)
\echo '== Q1 workshop detail'
SELECT e.id, e.title, e.venue_name, e.fee_type, e.fee_amount,
       c.name AS club_name, c.slug AS club_slug,
       w.speaker_name, w.speaker_bio, w.duration_minutes, w.bring_own_laptop,
       ARRAY(SELECT tag   FROM event_tags t              WHERE t.event_id = e.id)                    AS tags,
       ARRAY(SELECT topic FROM workshop_topics x         WHERE x.event_id = e.id ORDER BY position)  AS topics,
       ARRAY(SELECT item  FROM workshop_prerequisites x  WHERE x.event_id = e.id ORDER BY position)  AS prerequisites,
       ARRAY(SELECT l.at || ' ' || string_agg(f.field, ',')
               FROM event_change_log l JOIN event_change_log_fields f ON f.change_id = l.id
              WHERE l.event_id = e.id GROUP BY l.id, l.at ORDER BY l.at DESC LIMIT 20)               AS change_log
FROM events e
JOIN clubs c               ON c.id = e.club_id
LEFT JOIN workshop_details w ON w.event_id = e.id
WHERE e.id = :event_id;

-- Q2: Top 10 events to participate in (same scoring as the Mongo pipeline)
\echo '== Q2 top 10'
WITH cfg AS (SELECT * FROM ranking_settings WHERE id = 1),
eligible AS (
    SELECT e.* FROM events e
    WHERE e.status = 'published' AND e.cancelled_at IS NULL AND e.start_at > :now::timestamptz
      AND (NOT e.reg_required OR e.reg_deadline IS NULL OR e.reg_deadline > :now::timestamptz)
),
windowed AS (
    SELECT i.event_id,
           count(*) FILTER (WHERE i.type = 'save')               AS saves,
           count(*) FILTER (WHERE i.type = 'view')               AS views,
           count(*) FILTER (WHERE i.type = 'registration_click') AS clicks
    FROM event_interactions i
    JOIN eligible e ON e.id = i.event_id
    CROSS JOIN cfg
    WHERE i.ts >= :now::timestamptz - make_interval(days => cfg.window_days)
    GROUP BY i.event_id
),
raw AS (
    SELECT e.id, e.title, e.start_at, e.reg_required, e.reg_deadline,
           coalesce(w.saves, 0) AS saves, coalesce(w.views, 0) AS views, coalesce(w.clicks, 0) AS clicks,
           max(coalesce(w.saves, 0))  OVER () AS max_saves,      -- max-normalisation across the eligible set
           max(coalesce(w.views, 0))  OVER () AS max_views,
           max(coalesce(w.clicks, 0)) OVER () AS max_clicks
    FROM eligible e LEFT JOIN windowed w ON w.event_id = e.id
),
scored AS (
    SELECT r.*,
           CASE WHEN max_saves  > 0 THEN saves::float  / max_saves  ELSE 0 END AS saves_n,
           CASE WHEN max_views  > 0 THEN views::float  / max_views  ELSE 0 END AS views_n,
           CASE WHEN max_clicks > 0 THEN clicks::float / max_clicks ELSE 0 END AS clicks_n,
           exp(-extract(epoch FROM (start_at - :now::timestamptz)) / 86400 / 7) AS proximity,
           CASE WHEN reg_required AND reg_deadline IS NOT NULL AND reg_deadline <= :now::timestamptz + interval '72 hours' THEN 1.0
                WHEN reg_required THEN 0.5 ELSE 0 END AS urgency
    FROM raw r
)
SELECT row_number() OVER (ORDER BY score DESC, start_at, id) AS rank, id, title, round(score::numeric, 4) AS score
FROM (SELECT s.*, cfg.w_saves * saves_n + cfg.w_views * views_n + cfg.w_clicks * clicks_n
                + cfg.w_proximity * proximity + cfg.w_urgency * urgency AS score
      FROM scored s CROSS JOIN cfg) q
ORDER BY score DESC, start_at, id
LIMIT 10;

-- Q3: a comment thread: top-level comments, each with up to 3 replies and the true reply count
\echo '== Q3 comment thread'
SELECT c.id, c.body, count_r.n AS reply_count, r.id AS reply_id, r.body AS reply_body
FROM comments c
LEFT JOIN LATERAL (SELECT * FROM comments r WHERE r.parent_id = c.id ORDER BY r.created_at LIMIT 3) r ON true
LEFT JOIN LATERAL (SELECT count(*) AS n FROM comments r WHERE r.parent_id = c.id AND r.status = 'active') count_r ON true
WHERE c.post_id = :post_id AND c.parent_id IS NULL
ORDER BY c.created_at, r.created_at
LIMIT 20;
-- NB: rows multiply (one per reply) so the application must regroup them; Mongo returns nested documents.
