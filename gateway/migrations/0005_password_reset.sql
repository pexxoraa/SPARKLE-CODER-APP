PRAGMA foreign_keys = ON;

-- One-time, admin-issued reset codes for accounts that already have a password.
-- Plaintext codes are never stored. A reset revokes old browser sessions.
CREATE TABLE account_password_resets (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id),
  token_hash TEXT NOT NULL UNIQUE,
  expires INTEGER NOT NULL,
  created INTEGER NOT NULL
);
CREATE INDEX account_password_resets_expiry ON account_password_resets(expires);
