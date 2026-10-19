ALTER TABLE messages ADD COLUMN IF NOT EXISTS turn_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS superseded BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    client_message_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    content TEXT NOT NULL,
    response TEXT,
    sources JSONB NOT NULL DEFAULT '[]',
    target_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(thread_id, client_message_id)
);
CREATE INDEX IF NOT EXISTS idx_turns_thread_created ON turns(thread_id,created_at);
CREATE INDEX IF NOT EXISTS idx_messages_thread_order ON messages(thread_id,created_at,id);
CREATE TABLE IF NOT EXISTS quota_buckets (
    key TEXT PRIMARY KEY,
    hits INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quotas_expiry ON quota_buckets(expires_at);
CREATE TABLE IF NOT EXISTS tool_actions (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_actor_resource ON tool_actions(actor_id,resource_id,created_at);
