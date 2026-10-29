-- Hanin admin dashboard — additive Postgres DDL for EasyPanel.
-- Safe to paste: CREATE TABLE/INDEX IF NOT EXISTS only. No DROP, no DELETE.
-- Does not alter orders / money columns. Does not touch alembic_version.
-- After this file, optional: alembic upgrade head (revision 20261028_0004).

CREATE TABLE IF NOT EXISTS admin_sessions (
    id UUID PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    username VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS ix_admin_sessions_expires_at
    ON admin_sessions (expires_at);

CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    path VARCHAR(500) NOT NULL,
    product_slug VARCHAR(160) NULL,
    visitor_hash VARCHAR(64) NOT NULL,
    ip_hash VARCHAR(64) NOT NULL,
    country VARCHAR(2) NULL,
    vpn_flag BOOLEAN NULL,
    proxy_flag BOOLEAN NULL,
    anonymous_flag BOOLEAN NULL,
    hosting_flag BOOLEAN NULL,
    accepted BOOLEAN NOT NULL DEFAULT false,
    source VARCHAR(40) NOT NULL DEFAULT 'first_party',
    reject_reason VARCHAR(80) NULL
);

CREATE INDEX IF NOT EXISTS ix_analytics_events_accepted_created
    ON analytics_events (accepted, created_at);
CREATE INDEX IF NOT EXISTS ix_analytics_events_path_created
    ON analytics_events (path, created_at);
CREATE INDEX IF NOT EXISTS ix_analytics_events_visitor_created
    ON analytics_events (visitor_hash, created_at);
