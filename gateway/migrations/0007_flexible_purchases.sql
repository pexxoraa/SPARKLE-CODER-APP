-- Allow members to choose whole-million token purchases while preserving all
-- existing payment and coupon history. The public rate remains ₹15 per 1M.
DROP TRIGGER IF EXISTS payment_v2_credit;
DROP TRIGGER IF EXISTS payment_v2_final;
DROP TRIGGER IF EXISTS coupon_v2_redemption_guard;
DROP TRIGGER IF EXISTS coupon_v2_payment_credit;
DROP TRIGGER IF EXISTS coupon_v2_payment_release;

ALTER TABLE coupon_redemptions_v2 RENAME TO coupon_redemptions_v2_old;
ALTER TABLE payments_v2 RENAME TO payments_v2_old;
ALTER TABLE coupons_v2 RENAME TO coupons_v2_old;

CREATE TABLE payments_v2 (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
  device_id TEXT NOT NULL REFERENCES devices(id), utr TEXT NOT NULL UNIQUE,
  amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0 AND amount_paise <= 150000),
  credits INTEGER NOT NULL DEFAULT 1000000 CHECK(credits >= 1000000 AND credits <= 100000000 AND credits % 1000000 = 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  created INTEGER NOT NULL, reviewed INTEGER, note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE coupons_v2 (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE COLLATE NOCASE,
  bonus_tokens INTEGER NOT NULL DEFAULT 0 CHECK(bonus_tokens >= 0 AND bonus_tokens <= 10000000),
  discount_paise INTEGER NOT NULL DEFAULT 0 CHECK(discount_paise >= 0 AND discount_paise <= 150000),
  expires INTEGER,
  max_uses INTEGER NOT NULL DEFAULT 1 CHECK(max_uses > 0 AND max_uses <= 100000),
  one_per_account INTEGER NOT NULL DEFAULT 1 CHECK(one_per_account IN (0,1)),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  CHECK(bonus_tokens > 0 OR discount_paise > 0)
);

CREATE TABLE coupon_redemptions_v2 (
  payment_id TEXT PRIMARY KEY REFERENCES payments_v2(id),
  coupon_id TEXT NOT NULL REFERENCES coupons_v2(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  code TEXT NOT NULL,
  bonus_tokens INTEGER NOT NULL DEFAULT 0 CHECK(bonus_tokens >= 0),
  discount_paise INTEGER NOT NULL DEFAULT 0 CHECK(discount_paise >= 0 AND discount_paise <= 150000),
  amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0 AND amount_paise <= 150000),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','redeemed','released')),
  created INTEGER NOT NULL,
  redeemed INTEGER
);

INSERT INTO payments_v2 SELECT * FROM payments_v2_old;
INSERT INTO coupons_v2 SELECT * FROM coupons_v2_old;
INSERT INTO coupon_redemptions_v2 SELECT * FROM coupon_redemptions_v2_old;

DROP TABLE coupon_redemptions_v2_old;
DROP TABLE payments_v2_old;
DROP TABLE coupons_v2_old;

CREATE INDEX payments_v2_account ON payments_v2(account_id, created DESC);
CREATE INDEX payments_v2_pending ON payments_v2(status, created);
CREATE UNIQUE INDEX payments_v2_one_pending ON payments_v2(account_id) WHERE status='pending';
CREATE INDEX coupons_v2_active ON coupons_v2(active, expires);
CREATE INDEX coupon_redemptions_v2_coupon ON coupon_redemptions_v2(coupon_id, status, created);
CREATE INDEX coupon_redemptions_v2_account ON coupon_redemptions_v2(account_id, status, created);

CREATE TRIGGER payment_v2_credit AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='approved' BEGIN INSERT INTO ledger VALUES ('payment:'||NEW.id,NEW.account_id,NEW.credits,'payment','payment:'||NEW.id,NEW.reviewed,NEW.utr); UPDATE accounts SET balance=balance+NEW.credits,status='active' WHERE id=NEW.account_id AND status!='suspended'; SELECT RAISE(ABORT,'Account is suspended') WHERE changes()!=1; UPDATE devices SET status='active' WHERE id=NEW.device_id AND status='pending' AND kind='signup'; END;
CREATE TRIGGER payment_v2_final BEFORE UPDATE OF status ON payments_v2 WHEN OLD.status!='pending' AND NEW.status!=OLD.status BEGIN SELECT RAISE(ABORT,'Payment already reviewed'); END;
CREATE TRIGGER coupon_v2_redemption_guard BEFORE INSERT ON coupon_redemptions_v2 BEGIN SELECT RAISE(ABORT,'Coupon is unavailable') WHERE NOT EXISTS(SELECT 1 FROM coupons_v2 c WHERE c.id=NEW.coupon_id AND c.active=1 AND (c.expires IS NULL OR c.expires>NEW.created)); SELECT RAISE(ABORT,'Coupon use limit reached') WHERE (SELECT COUNT(*) FROM coupon_redemptions_v2 r WHERE r.coupon_id=NEW.coupon_id AND r.status IN ('pending','redeemed')) >= (SELECT max_uses FROM coupons_v2 WHERE id=NEW.coupon_id); SELECT RAISE(ABORT,'Coupon already used by this account') WHERE (SELECT one_per_account FROM coupons_v2 WHERE id=NEW.coupon_id)=1 AND EXISTS(SELECT 1 FROM coupon_redemptions_v2 r WHERE r.coupon_id=NEW.coupon_id AND r.account_id=NEW.account_id AND r.status IN ('pending','redeemed')); END;
CREATE TRIGGER coupon_v2_payment_credit AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='approved' AND EXISTS(SELECT 1 FROM coupon_redemptions_v2 WHERE payment_id=NEW.id AND status='pending') BEGIN UPDATE accounts SET balance=balance+(SELECT bonus_tokens FROM coupon_redemptions_v2 WHERE payment_id=NEW.id) WHERE id=NEW.account_id; INSERT INTO ledger SELECT 'coupon:'||NEW.id,NEW.account_id,bonus_tokens,'coupon','coupon:'||NEW.id,NEW.reviewed,'Coupon '||code FROM coupon_redemptions_v2 WHERE payment_id=NEW.id AND bonus_tokens>0; UPDATE coupon_redemptions_v2 SET status='redeemed',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
CREATE TRIGGER coupon_v2_payment_release AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='rejected' BEGIN UPDATE coupon_redemptions_v2 SET status='released',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
