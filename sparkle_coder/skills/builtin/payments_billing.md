# Payments & Billing Mastery
Treat money, credits and entitlements as ledgered state transitions. Use immutable transaction records, idempotency keys, atomic settlement and explicit pending/failed/reversed states. Never derive authoritative balance only from client input or mutable payment rows.

Separate quoted price from settled payment. Handle retries, duplicate callbacks, partial failure and reconciliation. Record enough metadata to explain every balance change without exposing private payment data.

Master standard: the same payment event cannot credit twice, failed settlement cannot lose funds/state, balances are reconstructable, and administrative corrections are auditable.