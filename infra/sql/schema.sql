CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Only install pgvector extension if available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        CREATE EXTENSION IF NOT EXISTS vector;
        RAISE NOTICE 'pgvector extension installed';
    ELSE
        RAISE NOTICE 'pgvector extension not available, vector features will be disabled';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS feeds
(
    id           INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    url          VARCHAR(255) UNIQUE NOT NULL,
    title        VARCHAR(64)         NOT NULL,
    description  VARCHAR(512)        NOT NULL,
    last_updated TIMESTAMP           NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(16)         NOT NULL DEFAULT 'active',
    created_at   TIMESTAMP           NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP           NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_items
(
    id         VARCHAR(256) PRIMARY KEY,
    feed_id    INTEGER      NOT NULL,
    title      VARCHAR(256) NOT NULL,
    link       VARCHAR(256) NOT NULL,
    summary    VARCHAR(512) NOT NULL DEFAULT '',
    pub_date   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_item_contents
(
    id           INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    feed_item_id VARCHAR(256) UNIQUE NOT NULL,
    content      TEXT                NOT NULL,
    created_at   TIMESTAMP           NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP           NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_groups
(
    id         INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    title
               VARCHAR(64) UNIQUE NOT NULL,
    "desc"
               VARCHAR(512)       NOT NULL,
    created_at TIMESTAMP          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP          NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_group_items
(
    id            INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    feed_group_id INTEGER   NOT NULL,
    feed_id       INTEGER   NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_brief
(
    id         INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    group_ids  INTEGER[]      NOT NULL,
    content    TEXT         NOT NULL,
    summary    TEXT         NOT NULL DEFAULT '',
    overview   TEXT         NOT NULL DEFAULT '',
    ext_info   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summary_memories
(
    id         INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    topic      VARCHAR(256) NOT NULL,
    reasoning  VARCHAR(512) NOT NULL,
    content    TEXT         NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS excluded_feed_item_ids
(
    id              INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    item_id         VARCHAR(256) NOT NULL,
    group_ids       INTEGER[]    NOT NULL,
    pub_date        TIMESTAMP    NOT NULL,
    focus           VARCHAR(512) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedules
(
    id         VARCHAR(8) PRIMARY KEY,
    time       TIME        NOT NULL,
    focus      VARCHAR(512) NOT NULL DEFAULT '',
    group_ids  INTEGER[]   NOT NULL,
    enabled    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_feed_items_feed_id_pub_date ON feed_items (feed_id, pub_date);
CREATE UNIQUE INDEX idx_group_items_group_feed_id ON feed_group_items (feed_group_id, feed_id);
CREATE INDEX idx_feed_brief_group_ids ON feed_brief USING GIN (group_ids);
CREATE INDEX idx_summary_memories_topic ON summary_memories USING GIN (topic gin_trgm_ops);
CREATE INDEX idx_excluded_feed_item_ids_item_id ON excluded_feed_item_ids (item_id);
CREATE INDEX idx_excluded_feed_item_ids_group_ids ON excluded_feed_item_ids USING GIN (group_ids);
CREATE INDEX idx_excluded_feed_item_ids_pub_date ON excluded_feed_item_ids (pub_date);
CREATE INDEX idx_excluded_feed_item_ids_focus ON excluded_feed_item_ids (focus, pub_date);
CREATE INDEX idx_excluded_feed_item_ids_item_focus ON excluded_feed_item_ids (item_id, focus, pub_date);
CREATE INDEX IF NOT EXISTS feed_item_contents_feed_item_id_idx ON feed_item_contents (feed_item_id);

-- Add vector columns and indexes only if pgvector is installed
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        -- Add embedding columns to feed_items
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'feed_items' AND column_name = 'title_embedding'
        ) THEN
            ALTER TABLE feed_items ADD COLUMN title_embedding vector(1536);
            RAISE NOTICE 'Added feed_items.title_embedding column';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'feed_items' AND column_name = 'summary_embedding'
        ) THEN
            ALTER TABLE feed_items ADD COLUMN summary_embedding vector(1536);
            RAISE NOTICE 'Added feed_items.summary_embedding column';
        END IF;

        -- Add embedding column to summary_memories
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'summary_memories' AND column_name = 'embedding'
        ) THEN
            ALTER TABLE summary_memories ADD COLUMN embedding vector(1536);
            RAISE NOTICE 'Added summary_memories.embedding column';
        END IF;

        -- Add focus_embedding column to excluded_feed_item_ids
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'excluded_feed_item_ids' AND column_name = 'focus_embedding'
        ) THEN
            ALTER TABLE excluded_feed_item_ids ADD COLUMN focus_embedding vector(1536);
            RAISE NOTICE 'Added excluded_feed_item_ids.focus_embedding column';
        END IF;

        -- Create vector indexes
        CREATE INDEX IF NOT EXISTS idx_summary_memories_embedding
            ON summary_memories USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 128);

        CREATE INDEX IF NOT EXISTS idx_excluded_feed_item_ids_focus_embedding
            ON excluded_feed_item_ids USING hnsw (focus_embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 128)
            WHERE focus_embedding IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_feed_items_title_embedding
            ON feed_items USING hnsw (title_embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 128)
            WHERE title_embedding IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_feed_items_summary_embedding
            ON feed_items USING hnsw (summary_embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 128)
            WHERE summary_embedding IS NOT NULL;

        RAISE NOTICE 'Vector indexes created';
    END IF;
END $$;

-- Comments for documentation
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        COMMENT ON COLUMN feed_items.title_embedding IS 'Vector embedding (1536 dim) for article title semantic prefilter.';
        COMMENT ON COLUMN feed_items.summary_embedding IS 'Vector embedding (1536 dim) for article summary semantic prefilter.';
        COMMENT ON COLUMN summary_memories.embedding IS 'Vector embedding (1536 dim) for semantic search. Generated using OpenAI text-embedding-3-small.';
        COMMENT ON COLUMN excluded_feed_item_ids.focus_embedding IS 'Vector embedding (1536 dim) for semantic focus matching. Generated using OpenAI text-embedding-3-small. Allows "AI安全" and "人工智能安全" to be treated as the same focus. NULL if embedding service not configured.';
    END IF;
END $$;

COMMENT ON COLUMN excluded_feed_item_ids.focus IS 'User focus/topic for this exclusion. Empty string means no specific focus. Articles excluded for one focus can be reused for different focuses.';
COMMENT ON COLUMN feed_brief.summary IS '简报概要，提取自内容中的所有二级标题';
COMMENT ON COLUMN feed_brief.ext_info IS '使用的外部搜索结果，JSON格式存储';