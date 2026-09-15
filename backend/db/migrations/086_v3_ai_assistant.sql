-- V3 AI Assistant: minimal owner-scoped chat and artifact persistence.
--
-- Business data access remains separate: the sandbox receives only its dedicated
-- read-only Retail DSN and never uses these application-write tables directly.

CREATE TABLE ai_assistant_conversations (
    id UUID PRIMARY KEY,
    owner_subject TEXT NOT NULL
        CHECK (btrim(owner_subject) = owner_subject AND length(owner_subject) BETWEEN 1 AND 256),
    title TEXT NOT NULL DEFAULT 'Conversație nouă'
        CHECK (btrim(title) = title AND length(title) BETWEEN 1 AND 80),
    effort TEXT NOT NULL DEFAULT 'high'
        CHECK (effort IN ('none', 'low', 'medium', 'high', 'xhigh', 'max')),
    previous_response_id TEXT NULL
        CHECK (previous_response_id IS NULL OR length(previous_response_id) BETWEEN 1 AND 512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_assistant_conversations_owner_updated
    ON ai_assistant_conversations (owner_subject, updated_at DESC, created_at DESC);

CREATE TABLE ai_assistant_messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL
        REFERENCES ai_assistant_conversations(id) ON DELETE CASCADE,
    ordinal BIGSERIAL NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete'
        CHECK (status IN ('complete', 'streaming', 'error', 'stopped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_ai_assistant_messages_conversation_ordinal
    ON ai_assistant_messages (conversation_id, ordinal);

CREATE INDEX idx_ai_assistant_messages_conversation_created
    ON ai_assistant_messages (conversation_id, ordinal ASC);

CREATE TABLE ai_assistant_artifacts (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL
        REFERENCES ai_assistant_conversations(id) ON DELETE CASCADE,
    message_id UUID NULL
        REFERENCES ai_assistant_messages(id) ON DELETE SET NULL,
    filename TEXT NOT NULL
        CHECK (btrim(filename) = filename AND length(filename) BETWEEN 1 AND 200),
    mime_type TEXT NOT NULL
        CHECK (btrim(mime_type) = mime_type AND length(mime_type) BETWEEN 1 AND 200),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    storage_key TEXT NOT NULL UNIQUE
        CHECK (
            btrim(storage_key) = storage_key
            AND length(storage_key) BETWEEN 1 AND 1024
            AND storage_key !~ '(^/|(^|/)\.\.(/|$))'
        ),
    kind TEXT NOT NULL CHECK (kind IN ('input', 'output')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_assistant_artifacts_conversation_created
    ON ai_assistant_artifacts (conversation_id, created_at ASC, id ASC);

REVOKE ALL ON TABLE ai_assistant_conversations FROM PUBLIC;
REVOKE ALL ON TABLE ai_assistant_messages FROM PUBLIC;
REVOKE ALL ON TABLE ai_assistant_artifacts FROM PUBLIC;
REVOKE ALL ON SEQUENCE ai_assistant_messages_ordinal_seq FROM PUBLIC;

GRANT SELECT ON TABLE ai_assistant_conversations TO unihub_web_read;
GRANT SELECT ON TABLE ai_assistant_messages TO unihub_web_read;
GRANT SELECT ON TABLE ai_assistant_artifacts TO unihub_web_read;

GRANT INSERT, UPDATE, DELETE ON TABLE ai_assistant_conversations TO unihub_business_write;
GRANT INSERT, UPDATE, DELETE ON TABLE ai_assistant_messages TO unihub_business_write;
GRANT INSERT, UPDATE, DELETE ON TABLE ai_assistant_artifacts TO unihub_business_write;
GRANT USAGE, SELECT ON SEQUENCE ai_assistant_messages_ordinal_seq TO unihub_business_write;
