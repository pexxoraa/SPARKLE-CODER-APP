# SaaS Architecture Mastery
Design SaaS around tenant boundaries, identity, billing/entitlements, configuration, lifecycle and operability. Decide what is global, tenant-scoped and user-scoped, and enforce that scope consistently in storage, cache, jobs and logs.

Model plan limits and feature entitlements as authoritative server-side rules. Make onboarding, suspension, cancellation, export and deletion states explicit. Avoid per-customer forks unless isolation/regulation truly requires them.

Master standard: tenant data cannot cross boundaries, entitlement changes are consistent, lifecycle states are recoverable, and operations can diagnose one tenant without exposing another.