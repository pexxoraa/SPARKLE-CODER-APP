# SPARKLE CODER tester pilot — 0.7.0

The hosted web/PWA client, shared gateway and admin panel are implemented. A live
server address, the owner's NVIDIA credential and UPI details are required before
distribution. Testers can use the Worker URL directly; they do not need the source ZIP,
Python, Node.js, Wrangler or a desktop installer. The legacy desktop client remains in
the repository for advanced local execution features. See `WEB_APP_DEPLOY.md`.

## Owner: deploy once

Use your own Cloudflare account on the Workers **Free** plan. No paid plan, card,
domain purchase or payment processor is requested by this setup. Free quotas can
stop service; NVIDIA availability and model cost are separate from hosting.

On the owner's computer, install Python 3.11+ and Node.js 22+ if they are missing.
Download this repository, extract it, open a terminal in its folder and run:

```sh
python scripts/setup_cloud.py
```

The script opens Cloudflare's normal secure login. It asks for your UPI ID,
the exact recipient name shown by the payment app, your support email and your
NVIDIA API key. Enter the key only in the hidden terminal prompt. Testers never
receive it. The script creates one Worker and one D1 database, applies the schema,
uploads secrets and prints your server URL and `/admin` address.

The generated admin password is `ADMIN_SECRET` in
`gateway/.owner/admin-credentials.json`. Keep a secure backup. This directory is
excluded from Git. The NVIDIA key is uploaded to Cloudflare secrets and is not
written into that file, the repository or the installer. Never share this folder.

If setup stops, fix the stated problem and rerun in the same folder. It reuses
the saved deployment configuration. If database creation succeeded but parsing
its identifier failed, copy that database ID into `.owner/wrangler.json` first.
Do not create a new database for an app update: balances live in the original DB.

### Recover from `incomplete input: SQLITE_ERROR [code: 7500]`

This error can occur when D1's remote SQL parser splits a trigger body. It does
not mean your Cloudflare login or UPI ID is wrong. The initial migration now uses
single-line, uppercase trigger bodies without nested `CASE ... END`, and setup
normalizes SQL files to LF before applying them.

Update the source in the **same SPARKLE-CODER folder**, retaining
`gateway/.owner`, `PROJECTS` and `APP_DATA`, then run:

```sh
python scripts/setup_cloud.py
```

For a Git checkout, use `git pull --ff-only` first. If you downloaded a ZIP,
replace `scripts/setup_cloud.py` and `gateway/migrations/0001_pilot.sql` with
the updated versions. Do not replace or share the private `.owner` directory.
Press Enter to keep the saved payment details. Enter the NVIDIA key only when
the hidden terminal prompt asks for it.

Setup reuses the saved database name and ID. If D1 still reports this specific
SQL error, setup first verifies that the database has no application tables or
applied migrations, then retries through Wrangler's SQL-file import path. The
schema and migration-history entry are imported together. Setup refuses this
recovery on populated databases and verifies the schema and history before
deploying the Worker. It never drops or recreates the database.

To check the migration files without logging in or changing Cloudflare:

```sh
python scripts/setup_cloud.py --check
```

This is a local SQL check, not proof of a successful remote deployment. Wait
for setup to print both **Server:** and **Admin:** before building the tester
installer. If it stops again, retain the configuration and share the error text
without keys or the admin password.

## Owner: publish the tester web app

The Worker deployed by `scripts/setup_cloud.py` serves the tester client at its root URL.
No separate frontend host is required. After an update, keep `gateway/.owner` and deploy:

```sh
cd gateway
npm test
npx --no-install wrangler deploy --config .owner/wrangler.json
```

Give testers only the root HTTPS URL. Keep `/admin` and the admin password private.
Chrome and Edge provide the best direct local-folder editing experience. Other browsers
can use the persistent scratch workspace and import files into browser storage.

## Tester: open, pay and start

1. Open the Worker root URL in a browser. Optionally install it as a PWA when the browser offers **Install app**.
2. Open **Account**, enter name/email, optionally phone, consent to model processing, and select **Request access**.
3. Pay **₹15** to the displayed UPI ID after confirming the recipient.
4. Submit the UPI transaction reference / UTR.
5. After admin approval, the balance shows **1,000,000 tokens** and model requests are enabled.
6. Choose **Open local folder** in Chrome/Edge for direct editing, or use the browser scratch workspace.

The browser creates and remembers a private device credential for this origin. Testers never
receive the NVIDIA key. On a new browser/device, choose **Reconnect an existing account**;
the admin must approve that reconnection.

## Admin: accept a payment

Open the printed `/admin` address and sign in with your generated admin password.
Under **Payments**, compare the ₹15 amount, UTR and payer with the actual credit
in your bank/UPI app. Check the verification box, then select **Accept + 1M tokens**.
The server updates the account and ledger in one database transaction.
Repeated clicks cannot credit twice. A UTR cannot fund two accounts. Reject
requests with a reason when the payment cannot be verified.

Users cannot choose the amount, credit quantity or model. Credit means the
provider's reported **input + output tokens**, including reasoning if the
provider includes it in output usage. There is no promise of one million words
or one million output-only tokens.

Before an inference request, the server holds a conservative maximum. It then
charges confirmed usage and releases the unused hold. Retrying the same request
returns the saved response without another model call or charge. Response data
is encrypted and expires after 15 minutes; cleanup runs every 15 minutes. Usage
metadata and the immutable credit ledger remain. Unknown provider outcomes stay
held for **Usage holds** review. Settle only confirmed provider usage; never guess.

## Performance changes

- Fast mode is the default and disables Nemotron 3 reasoning. Thorough mode is
  available when the task needs it.
- Default output ceiling: 4,096 tokens per request; context target: 24,000
  characters. Old default settings migrate. Explicit run caps remain optional.
- Completed write/edit bodies and long command outputs are compacted in the
  model request. The exact originals remain in local task history.
- Simple pages are prompted to use compact HTML/CSS and only necessary JS.
  These are scope guidelines, not file-line cutoffs or promises of exact sizes.
- Built-in HTML/CSS structural checks avoid installing a framework or issuing
  shell commands just to verify local links and markup structure. They do not
  claim to test appearance, JavaScript behavior or full accessibility.
- File review is optional and initially off; shell-command approvals remain on.
- Busy managed requests wait and retry for up to the default five-minute
  recovery window instead of stopping after a few seconds. Account refresh uses
  one server request to reduce free-host quota usage.
- Gateway request IDs prevent duplicate inference on transport retries. Direct
  providers are not blindly retried after ambiguous paid POST failures.

In a synthetic 1,448-line repeated-CSS history fixture, the completed exchange
shrinks from **72,707 to 2,466 serialized characters (96.6%)**. This measures
request-history compaction only. It is not a live token, price or speed result,
and does not verify the reported 600,000-token flower-shop run.

## Open the pilot with one tester first

Verify one real ₹15 payment and approval, restart the tester app, build the same
flower-shop prompt, inspect the rendered desktop/mobile page and record:
provider input/output tokens, elapsed model time, number of calls, interruptions,
file sizes/lines and remaining balance. Compare the full result with the prior
run before inviting all 30–50 members. Do not promise a token multiplier or a
latency improvement until those measurements exist.

The pilot permits 50 registrations, one outstanding model request per account,
and three upstream requests concurrently. This is admission control, not a
guarantee that all 50 can code simultaneously. Monitor provider rate limits and
Cloudflare quotas. ₹15 per pack is your selected price; validate model costs and
provider usage terms before expanding.

For updates, preserve `.owner` and deploy the existing config:

```sh
cd gateway
npx wrangler d1 migrations apply sparkle-pilot-YOUR_SUFFIX --remote --config .owner/wrangler.json
npx wrangler deploy --config .owner/wrangler.json
```

Use the database name in your config. Rebuild the desktop installer for app
changes. Secrets stay in Cloudflare unless explicitly changed.

Official references: [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/),
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[D1 transactions](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/).
