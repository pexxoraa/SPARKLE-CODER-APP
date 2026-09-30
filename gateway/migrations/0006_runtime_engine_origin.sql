PRAGMA foreign_keys = ON;

-- Owner-controlled runtime settings that may change without a Worker redeploy.
-- Values are never user-writable; the engine-origin endpoint requires ENGINE_SECRET.
CREATE TABLE runtime_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated INTEGER NOT NULL
);
