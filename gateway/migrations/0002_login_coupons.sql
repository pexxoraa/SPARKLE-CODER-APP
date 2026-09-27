PRAGMA foreign_keys = ON;

CREATE TABLE account_credentials (
  account_id TEXT PRIMARY KEY REFERENCES accounts(id),
  salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  updated INTEGER NOT NULL
);

CREATE TABLE coupons (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE COLLATE NOCASE,
  bonus_tokens INTEGER NOT NULL CHECK(bonus_tokens > 0 AND bonus_tokens <= 10000000),
  expires INTEGER,
  max_uses INTEGER NOT NULL DEFAULT 1 CHECK(max_uses > 0 AND max_uses <= 100000),
  one_per_account INTEGER NOT NULL DEFAULT 1 CHECK(one_per_account IN (0,1)),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX coupons_active ON coupons(active, expires);

CREATE TABLE coupon_redemptions (
  payment_id TEXT PRIMARY KEY REFERENCES payments(id),
  coupon_id TEXT NOT NULL REFERENCES coupons(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  code TEXT NOT NULL,
  bonus_tokens INTEGER NOT NULL CHECK(bonus_tokens > 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','redeemed','released')),
  created INTEGER NOT NULL,
  redeemed INTEGER
);
CREATE INDEX coupon_redemptions_coupon ON coupon_redemptions(coupon_id, status, created);
CREATE INDEX coupon_redemptions_account ON coupon_redemptions(account_id, status, created);

CREATE TRIGGER coupon_redemption_guard BEFORE INSERT ON coupon_redemptions BEGIN SELECT RAISE(ABORT,'Coupon is unavailable') WHERE NOT EXISTS(SELECT 1 FROM coupons c WHERE c.id=NEW.coupon_id AND c.active=1 AND (c.expires IS NULL OR c.expires>NEW.created)); SELECT RAISE(ABORT,'Coupon use limit reached') WHERE (SELECT COUNT(*) FROM coupon_redemptions r WHERE r.coupon_id=NEW.coupon_id AND r.status IN ('pending','redeemed')) >= (SELECT max_uses FROM coupons WHERE id=NEW.coupon_id); SELECT RAISE(ABORT,'Coupon already used by this account') WHERE (SELECT one_per_account FROM coupons WHERE id=NEW.coupon_id)=1 AND EXISTS(SELECT 1 FROM coupon_redemptions r WHERE r.coupon_id=NEW.coupon_id AND r.account_id=NEW.account_id AND r.status IN ('pending','redeemed')); END;
CREATE TRIGGER coupon_payment_credit AFTER UPDATE OF status ON payments WHEN OLD.status='pending' AND NEW.status='approved' AND EXISTS(SELECT 1 FROM coupon_redemptions WHERE payment_id=NEW.id AND status='pending') BEGIN UPDATE accounts SET balance=balance+(SELECT bonus_tokens FROM coupon_redemptions WHERE payment_id=NEW.id) WHERE id=NEW.account_id; INSERT INTO ledger VALUES ('coupon:'||NEW.id,NEW.account_id,(SELECT bonus_tokens FROM coupon_redemptions WHERE payment_id=NEW.id),'coupon','coupon:'||NEW.id,NEW.reviewed,(SELECT 'Coupon '||code FROM coupon_redemptions WHERE payment_id=NEW.id)); UPDATE coupon_redemptions SET status='redeemed',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
CREATE TRIGGER coupon_payment_release AFTER UPDATE OF status ON payments WHEN OLD.status='pending' AND NEW.status='rejected' BEGIN UPDATE coupon_redemptions SET status='released',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
