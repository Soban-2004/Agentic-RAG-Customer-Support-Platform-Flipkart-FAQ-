-- Postgres schema for the FastAPI backend's own auth + chat history.
--
-- Replaces Chainlit's SQLAlchemyDataLayer schema (users/threads/steps/elements/
-- feedbacks, reverse-engineered from chainlit's internals since it ships no
-- schema file of its own -- see git history for that version if curious). Now
-- that we own both the persistence and the rendering side, there's no vendor
-- schema to stay in lockstep with: `threads`/`steps`/`elements`/`feedbacks`
-- collapse into two simple tables, `threads` and `messages`.
--
-- `users` is unchanged from the Chainlit-era schema -- existing demo users
-- (see src/auth/manage_users.py) and their password hashes keep working with
-- zero migration.
--
-- Run this once against a fresh database, e.g.:
--   psql -d flipkart_chatbot -f db/schema.sql
-- Or, if migrating an existing Chainlit-era database: drop the old
-- threads/steps/elements/feedbacks tables first (their data doesn't map onto
-- the new schema -- see README's Auth & chat history section), then run this.

CREATE TABLE IF NOT EXISTS users (
    "id" TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "createdAt" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "password_hash" TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    "id" TEXT PRIMARY KEY,
    "user_id" TEXT NOT NULL REFERENCES users("id") ON DELETE CASCADE,
    "title" TEXT,
    "created_at" TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    "id" TEXT PRIMARY KEY,
    "thread_id" TEXT NOT NULL REFERENCES threads("id") ON DELETE CASCADE,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "created_at" TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_threads_userid ON threads ("user_id");
CREATE INDEX IF NOT EXISTS idx_messages_threadid ON messages ("thread_id");
