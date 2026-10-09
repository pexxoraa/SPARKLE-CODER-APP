# Milestone 10 — release readiness and engineering acceptance

This release gate makes repeatable claims about source versions, local smoke-test
performance, installed applications, and artifact integrity. It does **not**
deploy SPARKLE CODER, certify production capacity, or perform live paid model
calls. No tag or production release is created automatically.

## What blocks a release

1. Version parity: Python package, Python desktop, web package, gateway health
   endpoint and Windows installer must all report the same semantic version.
   A release tag must equal the version with a leading v, and point to a
   commit in main history.
2. Cloud/desktop UI parity: bundled agent.js and agent.css must byte-for-byte
   match their shared source files. Rebuild the gateway UI after every change.
3. Python, UI, gateway, D1 and metadata/performance verification jobs must pass.
4. The performance smoke creates 160 source files, measures one cold and six
   repeated fingerprints, and verifies same-size edits and deletion detection.
   Limits (5 seconds cold, 1.5 seconds median warm) are conservative CI smoke
   bounds, NOT production performance SLAs or model throughput claims.
5. Windows, Linux and macOS must package a working Python runtime, pass real
   executable smoke tests, and upload assets. Windows also runs installer,
   upgrade, uninstall and existing-user-data preservation checks.
6. Every platform produces an acceptance JSON manifest with release version,
   OS/arch, edition, gateway URL, asset name, size and SHA-256. Tagged release
   publishing verifies all three hashes and refuses mixed editions, invalid
   version tags, or a personal edition disguised as a tester release.
   Tagged tester builds require the owner-configured SPARKLE_PILOT_URL and
   a root HTTPS endpoint.

Manifests provide artifact mix-up and corruption detection, NOT independent
cryptographic authorship signatures. Builds remain unsigned and not notarized.

## Local reproducibility (does not change cloud resources)

Run these from the repository root:

    python3 scripts/release_acceptance.py source
    python3 scripts/release_acceptance.py performance
    python3 -m unittest discover -s tests -q
    npm test
    npm ci --prefix gateway
    npm test --prefix gateway
    npm run test:migrations --prefix gateway

For completed Windows, Linux or macOS out folders run respectively:

    python scripts/release_acceptance.py artifact --platform Windows --arch X64
    python scripts/release_acceptance.py artifact --platform Linux --arch X64
    python scripts/release_acceptance.py artifact --platform macOS --arch ARM64

After gathering the three platforms and manifests into one folder:

    python scripts/release_acceptance.py aggregate --directory release

The artifact command requires the real packaged binary, bundled Python,
installer or archive, and matching EDITION.txt.

## Approval and manual checks still needed

- Live production rollout, domain updates, provider secrets and any paid
  resource changes need separate explicit owner approval.
- Six concurrently coding members and 30–50 testers need live measurements
  on the actual cloud VM. Local gateway queue tests do not establish VM
  performance or uptime.
- Live model latency, invoices/token settlement, multi-hour recovery,
  DNS/TLS, deploy/rollback drills, and sustained user-load remain unverified.
- Physical Windows/macOS UX, Windows SmartScreen and code signing, macOS
  signing/notarization, and full security penetration testing remain manual.
- A single Windows passing workflow does not prove intermittent OS filesystem
  races cannot recur.

Milestone 10 delivers an auditable GitHub release candidate, not an
authorized production deployment or release tag.
