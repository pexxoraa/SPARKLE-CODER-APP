PRAGMA foreign_keys = ON;

-- One-time, admin-issued setup codes let approved legacy accounts create their
-- first password after their old browser session is gone. Plaintext codes are
-- never stored and each account can have only one live code at a time.
CREATE TABLE account_password_setups (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id),
  token_hash TEXT NOT NULL UNIQUE,
  expires INTEGER NOT NULL,
  created INTEGER NOT NULL
);
CREATE INDEX account_password_setups_expiry ON account_password_setups(expires);
