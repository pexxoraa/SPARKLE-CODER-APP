# SPARKLE CODER Web/PWA deployment — 0.8.0

The Worker root now serves the full shared agent interface. Testers need only the
Worker URL. The owner's account panel remains at `/admin`.

## Deploy over an existing pilot

Keep your existing `gateway/.owner`, `PROJECTS`, `APP_DATA` and `HOSTED_DATA`.
This release requires no D1 schema reset. In your existing configured checkout:

```sh
bash Deploy_Web_App.sh
```

The script installs locked gateway dependencies, builds the shared browser UI,
runs gateway tests, publishes the same Worker and checks release `0.8.0`.
It preserves database identity, payment details and existing Worker secrets.
Use Python 3.11+ and Node 22.16+ (24 recommended) on the owner computer.

**The full agent also needs an owner-hosted engine.** Follow [HOSTED_ENGINE.md](HOSTED_ENGINE.md)
to run it on an existing Python/Docker host and connect its HTTPS origin.
Deploying the Worker alone does not enable command execution, cloud projects,
agent history or verification. The app shows this missing connection explicitly.
If initial setup stopped before secrets were uploaded, finish
`python scripts/setup_cloud.py` in the existing folder first.

## Available workflows

The full interface uses the original Python engine for projects, Build/Ask,
multi-file editing, plans, requirements, command/file approvals, recorded checks,
run controls, task history, follow-ups, report/log downloads and conflict-aware
undo. A manual editor adds create/save/delete actions with their own history.
Cloud project files persist on the owner host and are scoped to the account.
Use Import files/Import folder to bring local files into a cloud project and
Download ZIP to export it. The browser cannot open the owner's OS folders.

The old scratch editor remains at `/scratch.html`, with the same browser storage
and device account identity. Its direct local-folder editing (where supported),
imports, file downloads, code-block review and model request retry remain intact.
The brand link or Cloud projects link returns to the full workspace. Scratch
files are not automatically uploaded to the engine; download/import them when
needed. Clearing browser storage removes scratch files and the device credential;
cloud files can be recovered by signing back into the same account with its email
and password.

PWA installation remains available through the browser's install menu. Offline
support covers the public shell and browser scratch data. Account/admin/model
requests and cloud projects require a connection. The NVIDIA key and engine relay
secret are never sent to the browser.

## Admin flow

New signups now appear immediately under **Account requests** in `/admin`, including before a payment is submitted. The request ID matches the tester's receipt. The admin page checks for new requests every 30 seconds while visible and preserves unfinished review notes and verification checkboxes.

After registration, the tester submits the required purchase amount and UPI reference. The normal pack is ₹15 for 1,000,000 tokens; a coupon may reduce that price, add bonus tokens, or do both. The owner verifies the exact displayed amount in the bank/UPI app and approves it in `/admin`. A 100% discount coupon needs no UPI payment but still creates an admin-reviewed coupon claim. Approval activates the signup device and adds the base pack plus any coupon bonus exactly once; seeing a signup request by itself does not issue credits.

Returning approved users sign in with their email/password and receive an active browser connection immediately; normal sign-in does not create an admin approval request. New accounts still require the normal signup/purchase review. Existing accounts created before password login are required to create a password from an already approved browser before coding or buying more tokens; manual recovery remains available for exceptional legacy/lost-access cases.

Token purchases can optionally include a coupon code. Coupons can set a money discount from ₹0 through the full ₹15 price, add bonus tokens, or combine both. `/admin` includes controls for the money discount, bonus amount, expiry, maximum uses, one-use-per-account policy, active/disabled state and notes. Coupon benefits are granted only after admin approval, and rejected purchases release their coupon reservation.
