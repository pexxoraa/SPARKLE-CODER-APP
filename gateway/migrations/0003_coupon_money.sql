PRAGMA foreign_keys = ON;

-- V2 purchase tables preserve all existing payment/coupon history while allowing
-- coupons to discount the ₹15 price, add bonus tokens, or do both.
CREATE TABLE payments_v2 (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
  device_id TEXT NOT NULL REFERENCES devices(id), utr TEXT NOT NULL UNIQUE,
  amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0 AND amount_paise <= 1500),
  credits INTEGER NOT NULL DEFAULT 1000000 CHECK(credits = 1000000),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  created INTEGER NOT NULL, reviewed INTEGER, note TEXT NOT NULL DEFAULT ''
);
INSERT INTO payments_v2 SELECT id,account_id,device_id,utr,amount_paise,credits,status,created,reviewed,note FROM payments;
CREATE INDEX payments_v2_account ON payments_v2(account_id, created DESC);
CREATE INDEX payments_v2_pending ON payments_v2(status, created);
CREATE UNIQUE INDEX payments_v2_one_pending ON payments_v2(account_id) WHERE status='pending';

CREATE TABLE coupons_v2 (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE COLLATE NOCASE,
  bonus_tokens INTEGER NOT NULL DEFAULT 0 CHECK(bonus_tokens >= 0 AND bonus_tokens <= 10000000),
  discount_paise INTEGER NOT NULL DEFAULT 0 CHECK(discount_paise >= 0 AND discount_paise <= 1500),
  expires INTEGER,
  max_uses INTEGER NOT NULL DEFAULT 1 CHECK(max_uses > 0 AND max_uses <= 100000),
  one_per_account INTEGER NOT NULL DEFAULT 1 CHECK(one_per_account IN (0,1)),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  CHECK(bonus_tokens > 0 OR discount_paise > 0)
);
INSERT INTO coupons_v2(id,code,bonus_tokens,discount_paise,expires,max_uses,one_per_account,active,created,note)
SELECT id,code,bonus_tokens,0,expires,max_uses,one_per_account,active,created,note FROM coupons;
CREATE INDEX coupons_v2_active ON coupons_v2(active, expires);

CREATE TABLE coupon_redemptions_v2 (
  payment_id TEXT PRIMARY KEY REFERENCES payments_v2(id),
  coupon_id TEXT NOT NULL REFERENCES coupons_v2(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  code TEXT NOT NULL,
  bonus_tokens INTEGER NOT NULL DEFAULT 0 CHECK(bonus_tokens >= 0),
  discount_paise INTEGER NOT NULL DEFAULT 0 CHECK(discount_paise >= 0 AND discount_paise <= 1500),
  amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0 AND amount_paise <= 1500),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','redeemed','released')),
  created INTEGER NOT NULL,
  redeemed INTEGER
);
INSERT INTO coupon_redemptions_v2(payment_id,coupon_id,account_id,code,bonus_tokens,discount_paise,amount_paise,status,created,redeemed)
SELECT r.payment_id,r.coupon_id,r.account_id,r.code,r.bonus_tokens,0,p.amount_paise,r.status,r.created,r.redeemed
FROM coupon_redemptions r JOIN payments p ON p.id=r.payment_id;
CREATE INDEX coupon_redemptions_v2_coupon ON coupon_redemptions_v2(coupon_id, status, created);
CREATE INDEX coupon_redemptions_v2_account ON coupon_redemptions_v2(account_id, status, created);

CREATE TRIGGER payment_v2_credit AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='approved' BEGIN INSERT INTO ledger VALUES ('payment:'||NEW.id,NEW.account_id,NEW.credits,'payment','payment:'||NEW.id,NEW.reviewed,NEW.utr); UPDATE accounts SET balance=balance+NEW.credits,status='active' WHERE id=NEW.account_id AND status!='suspended'; SELECT RAISE(ABORT,'Account is suspended') WHERE changes()!=1; UPDATE devices SET status='active' WHERE id=NEW.device_id AND status='pending' AND kind='signup'; END;
CREATE TRIGGER payment_v2_final BEFORE UPDATE OF status ON payments_v2 WHEN OLD.status!='pending' AND NEW.status!=OLD.status BEGIN SELECT RAISE(ABORT,'Payment already reviewed'); END;
CREATE TRIGGER coupon_v2_redemption_guard BEFORE INSERT ON coupon_redemptions_v2 BEGIN SELECT RAISE(ABORT,'Coupon is unavailable') WHERE NOT EXISTS(SELECT 1 FROM coupons_v2 c WHERE c.id=NEW.coupon_id AND c.active=1 AND (c.expires IS NULL OR c.expires>NEW.created)); SELECT RAISE(ABORT,'Coupon use limit reached') WHERE (SELECT COUNT(*) FROM coupon_redemptions_v2 r WHERE r.coupon_id=NEW.coupon_id AND r.status IN ('pending','redeemed')) >= (SELECT max_uses FROM coupons_v2 WHERE id=NEW.coupon_id); SELECT RAISE(ABORT,'Coupon already used by this account') WHERE (SELECT one_per_account FROM coupons_v2 WHERE id=NEW.coupon_id)=1 AND EXISTS(SELECT 1 FROM coupon_redemptions_v2 r WHERE r.coupon_id=NEW.coupon_id AND r.account_id=NEW.account_id AND r.status IN ('pending','redeemed')); END;
CREATE TRIGGER coupon_v2_payment_credit AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='approved' AND EXISTS(SELECT 1 FROM coupon_redemptions_v2 WHERE payment_id=NEW.id AND status='pending') BEGIN UPDATE accounts SET balance=balance+(SELECT bonus_tokens FROM coupon_redemptions_v2 WHERE payment_id=NEW.id) WHERE id=NEW.account_id; INSERT INTO ledger SELECT 'coupon:'||NEW.id,NEW.account_id,bonus_tokens,'coupon','coupon:'||NEW.id,NEW.reviewed,'Coupon '||code FROM coupon_redemptions_v2 WHERE payment_id=NEW.id AND bonus_tokens>0; UPDATE coupon_redemptions_v2 SET status='redeemed',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
CREATE TRIGGER coupon_v2_payment_release AFTER UPDATE OF status ON payments_v2 WHEN OLD.status='pending' AND NEW.status='rejected' BEGIN UPDATE coupon_redemptions_v2 SET status='released',redeemed=NEW.reviewed WHERE payment_id=NEW.id AND status='pending'; END;
