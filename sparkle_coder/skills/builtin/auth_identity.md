# Authentication & Identity Mastery
Separate identity proof, session/device state, authorization and account lifecycle. Store passwords with a modern password hash and unique salt; use one-time codes with expiry and single-use semantics. Rotate/revoke sessions after sensitive credential changes.

Do not expose whether protected accounts exist when that creates enumeration risk. Bind recovery and privileged actions to explicit verification. Authorization must be checked server-side for every resource operation.

Master standard: credentials are never stored or logged in plaintext, old sessions can be revoked, recovery cannot be replayed, and authenticated identity cannot be confused with client-supplied account fields.