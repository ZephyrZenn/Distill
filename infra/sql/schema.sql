CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    item_id VARCHAR(256) NOT NULL,
    group_ids INTEGER[] NOT NULL,
    pub_date TIMESTAMP NOT NULL
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
CREATE INDEX IF NOT EXISTS feed_item_contents_feed_item_id_idx ON feed_item_contents (feed_item_id);