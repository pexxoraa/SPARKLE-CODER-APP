# External API Integration Mastery
Treat external APIs as unreliable dependencies. Centralize authentication, request construction, timeouts, retries, pagination, rate-limit handling and response validation. Do not scatter provider-specific assumptions throughout the product.

Respect idempotency for writes and never retry unsafe mutations blindly. Detect schema and error changes and preserve provider request identifiers for support and debugging without exposing private data.

Master standard: provider outages degrade predictably, retries are bounded, integration behavior is testable with fixtures or fakes, and provider changes are isolated.