# Database Mastery
Model invariants in the database when possible. Use appropriate keys, unique constraints, foreign keys, indexes and transactions instead of relying only on application checks. Keep migrations forward-safe and deterministic.

Think about concurrency, idempotency, nullability, retention and query shape before adding tables. Avoid unbounded scans and duplicate sources of truth. Never silently rewrite production data during a schema change without a clear migration rule.

Master standard: important invariants survive concurrent requests and process restarts, and migration tests prove both fresh-install and upgrade paths.