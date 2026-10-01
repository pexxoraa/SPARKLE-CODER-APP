# Security Mastery
Start from trust boundaries: user input, account identity, external services, filesystem paths, private configuration and administrative actions. Validate and normalize before use, authorize every object access, and keep private values out of normal logs and responses.

Prefer deny-by-default for privileged operations. Guard browser-origin boundaries where relevant, prevent path and symlink escape, bound uploads and outbound fetches, and avoid forwarding private headers across redirects.

Master standard: another account cannot read or mutate the resource, private values do not leak through normal error paths, and risky inputs fail closed without weakening the product workflow.