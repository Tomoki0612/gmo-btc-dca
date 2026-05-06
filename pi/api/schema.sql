PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    user_id        TEXT PRIMARY KEY,
    amount         INTEGER,
    frequency      TEXT,
    schedule_day   INTEGER,
    schedule_time  INTEGER,
    api_key        TEXT,
    api_secret     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL,
    at          TEXT NOT NULL,
    status      TEXT,
    amount      INTEGER,
    btc         REAL,
    rate        REAL,
    reason      TEXT,
    field       TEXT,
    before_val  TEXT,
    after_val   TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_history_user_at      ON history(user_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user_type_at ON history(user_id, type, at DESC);
