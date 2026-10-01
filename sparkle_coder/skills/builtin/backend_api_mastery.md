# Backend & API Mastery
Design APIs around explicit contracts: authenticated identity, authorization, validated input, stable error semantics, idempotency where retries can happen, and atomic state transitions. Keep business rules in one authoritative layer rather than duplicated across endpoints.

Treat network responses as untrusted. Bound payloads, timeouts and retries. Separate client mistakes from server failures. For important state-changing operations, make partial failure and concurrency behavior explicit.

Master standard: the API is hard to misuse accidentally, retries do not duplicate side effects, cross-account access is impossible, and tests cover authorization plus failure rollback.