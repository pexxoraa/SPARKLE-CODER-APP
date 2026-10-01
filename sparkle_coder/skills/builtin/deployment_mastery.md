# Deployment & Operations Mastery
Treat deployment as a repeatable state transition, not a manual ritual. Validate configuration, migrations, health dependencies and rollback or failure behavior before publishing. Keep private configuration out of source and user-visible output.

Make deployment idempotent where possible. Distinguish application health from tunnel, DNS or provider availability. After deploy, verify the exact live hostname, critical APIs, static assets and recovery services rather than trusting a CLI success message.

Master standard: a new maintainer can run the deployment safely, failures leave useful state, and health and recovery behavior are tested rather than assumed.