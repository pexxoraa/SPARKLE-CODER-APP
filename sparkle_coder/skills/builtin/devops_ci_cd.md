# CI/CD Mastery
Make builds and deployments reproducible from versioned source. CI should run fast high-signal checks first, then heavier integration/security/release checks as needed. Pin important toolchains and cache without hiding dependency changes.

Separate build artifact creation from environment deployment. Protect production with reviewed configuration, migration ordering, health checks and rollback strategy. Do not put long-lived private values into logs or repository workflows.

Master standard: the same revision produces the same artifact, failed checks prevent release, and deployment state can be traced to a commit and configuration.