# Full cloud workspace — release 0.8.0

The Worker now serves the same full interface as the Python app. The smaller
browser editor is kept at `/scratch.html`; its existing browser files remain
there. Cloud project files and histories are stored on the owner's engine host.
They are separate from scratch files and existing desktop project folders.

## What changed after comparing both repositories

`SPARKLE-CODER` contains the Python agent, file tools, verification and session
engine. `SPARKLE-CODER-APP` added a separate browser editor and chat client, so
deploying that client did not deploy the Python engine's features. This release
builds the web interface from `sparkle_coder/ui` and adds an authenticated route
from the existing Worker to the same Python engine.

| Feature | Full cloud interface |
| --- | --- |
| Signup, payment reference, admin approval, credits | Existing Worker + D1; request receipt is visible in admin before payment |
| Projects, files and folders | Account-specific persistent projects; browser import and ZIP download |
| Manual code editing | Create/edit/delete text files up to 200 KB, with conflict detection and undo history |
| Build and read-only Ask | Same agent and file tools as the Python app; model requests use each member's gateway credit balance |
| Multi-file agent changes | Written to the selected cloud project; optional review before each file change |
| Project brief and requirements | Saved per project and attached to new tasks |
| Plans, changes and check output | Shared interface with diffs, recorded evidence and explanations |
| Approvals, pause, resume, stop | Real background runs and browser control APIs |
| Saved tasks, follow-ups and restart recovery | Persistent sessions; interrupted actions are not silently replayed |
| Reports, logs and undo | Downloads and conflict-aware rollback of tracked file changes |
| Commands and verification | Docker on the owner host; no host-shell fallback |
| Desktop folder picker / open OS folder | Browser import and download instead |
| Local model/API-key settings, storage relocation, Quit | Owner-managed in cloud mode; personal desktop mode remains available |
| Scratch editor and direct browser folder access | Retained at `/scratch.html` |

Cloud accounts start in the full controls view. They can switch to simple view.
Future roadmap items such as app previews, browser automation, a GitHub panel,
parallel agents, document tools and scheduling were not implemented in either
repository. This release does not pretend to implement them.

## Where it runs

The browser sends account and project requests to the Worker. The Worker authenticates
project requests before forwarding them to the owner engine. The engine runs the
agent and Docker commands, and sends model requests back through the Worker so
they use that account's token balance. Only the Worker calls the AI provider with the
owner's provider key.

The existing Workers + D1 deployment continues to handle accounts, UPI references,
credit accounting and the protected provider key. A separate, continuously running
Linux host with Python 3.11+, Docker and persistent disk runs the Python engine.
Workers alone cannot run this app's Python subprocess/Docker execution engine.
No server is provisioned or purchased by these scripts. You may use an existing
dedicated host; its availability, capacity and hosting costs are your choice.
Testers need only the Worker URL and an approved account.

## Owner setup

Keep your existing `gateway/.owner` and database. First apply this update, then
deploy the new interface from the existing configured checkout:

```sh
bash Deploy_Web_App.sh
```

Until an engine is connected, the interface clearly says that cloud projects
are unavailable. Signup/admin/payment and the scratch editor remain available.

On the owner engine host, use the updated source and build the supplied tools
image (Docker must already be installed and usable by the service user):

```sh
docker build -t sparkle-coder-tools:local -f containers/Dockerfile .
python3 scripts/setup_hosted_engine.py init \
  --gateway https://sparkle-pilot-7f7948.sparklecoder.workers.dev
python3 scripts/setup_hosted_engine.py serve
```

Use your actual Worker URL if different. `init` creates a private
`gateway/.owner/engine.json` and preserves it on reruns. It does not display the
relay secret. `serve` binds to `127.0.0.1:8788`, verifies Docker/image availability,
and persists account data in `HOSTED_DATA`. Keep it running under your host's
service manager for continuous availability. Stop and restart it to load future
source updates; saved projects and sessions remain on disk.

If the owner uses Docker Desktop on Linux, start its existing user service and
set `DOCKER_CONTEXT=desktop-linux` for both the image build and engine service.
The command runner preserves the selected context for the Docker CLI and cleanup;
it does not send Docker connection settings or owner secrets into command containers.
Do not disable AppArmor to make an unrelated rootless Docker installation work.

The web **Project files** screen opens cloud projects. Its **Open files from this
computer** link opens the browser editor for local folders and earlier scratch
files. A task's **Open project folder** action opens the cloud file browser.
Offline/account-required states explain the blocker and provide the appropriate
account or workspace refresh action. Failed file reads clear stale file previews.

Publish that loopback service through an HTTPS reverse proxy or tunnel at an
origin you control, such as `https://engine.your-domain.example`. Pass request
headers/body through unchanged and allow imports up to 30 MiB. Do not add a
browser login page in front of this API: it authenticates the Worker's relay
header itself. Keep its underlying port private. The origin must not redirect.

On the owner computer with the existing Wrangler login, use the **same private
engine.json** as the engine host (transfer it privately if these are separate
computers), plus the existing Worker configuration. Then run:

```sh
python3 scripts/setup_hosted_engine.py connect \
  --origin https://engine.your-domain.example
```

This checks the authenticated engine health endpoint first, builds/tests the
interface, uploads only `ENGINE_SECRET` through stdin, and updates `ENGINE_ORIGIN`
on the existing Worker. It preserves D1 identity, payment settings and existing
secrets. It checks the deployed release/configuration before reporting success.
Do not put `.owner`, `HOSTED_DATA`, account credentials or model keys in Git/ZIPs.
The provider key stays on the Worker; the engine receives each user's own device
credential to make metered calls on that account.

## Capacity and command behavior

The default is one simultaneous coding run for the entire host, one per account,
up to 50 accounts and 30 projects per account. Use `init --max-running 2` or `3`
only on first initialization if the host has enough capacity; an existing private
configuration is preserved. Busy requests fail before a model request is made.

Each command container has a 4 GiB memory ceiling, 2 CPUs, 256 processes, a read-only
root, temporary storage and only that project's bind mount. Networking is disabled.
Package downloads therefore do not work during a task. Add needed runtimes and
dependencies to an owner-built tools image, or import a project with usable
dependencies according to its tooling. The default image has Python, Node/npm,
Git and build tools; it is not a universal environment for every language or
framework. Setup discovery reports this uncertainty; only actual checks are proof.

Hosted run caps are 24 model steps, 15 minutes, 200,000 total tokens, 8,192 output
tokens per request and 120 seconds per command. Project configuration cannot
disable Docker, enable network access, replace the tools image, relax these caps
or change the managed model connection. These caps and the gateway's rate/balance
limits also bound usage; a cap is not a guarantee that the task will finish.

Run this pilot on a dedicated host. Container isolation is not a guarantee against
host/kernel vulnerabilities. Put `HOSTED_DATA` on a size-limited persistent volume,
monitor free disk, and back it up; a hard per-account disk quota is not implemented.
Losing that volume loses cloud files/history; D1 contains account records, not
project backups. Offline PWA support covers the public shell and scratch files,
not the cloud engine. This release neither hosts generated applications nor
provides a live preview of them.

## Verification and final live check

Automated tests exercise the browser transport through the real Worker and SQLite
adapter into the real Python HTTP service, filesystem, agent and session engine.
They cover signup visibility, payment approval, isolation, multi-file edit approval,
history, downloads, pause/resume/stop, restart persistence, conflict detection and
undo. Test model replies are scripted; no live provider request or real payment is
part of these tests. Docker command construction and fail-closed behavior are
tested; actual container execution must be checked on the owner host.

After connecting the host, open your existing approved account on the Worker URL:

1. Check that the cloud workspace opens without a desktop pairing screen.
2. Create a project, import a text file, edit it, and download its ZIP.
3. Ask Build to add two small files, with **Review edits** selected. Approve them.
4. Ask for a simple Python check. Approve the command and inspect its actual output.
5. Open History, download the report, then preview and confirm Undo.
6. Restart the engine and reload: the project and saved task must still appear.

Use actual model usage and check output to verify the deployment before inviting
testers. If the engine is offline, projects are shown as unavailable; no simulated
success is presented. Returning members sign in with their account email/password
without a new admin approval. Existing pre-password accounts must create a login password
before coding or buying more tokens. A still-connected approved browser can set it directly.
If that browser was logged out, the owner verifies the user in the admin panel and issues a
single-use setup code that expires after 30 minutes; the user can then create the first
password from any browser. Only the setup-code hash is stored, and successful use deletes it.
Manual admin recovery remains a lost-access fallback after a password exists. Purchase coupons may reduce the ₹15 price,
add bonus tokens, or combine both; a full discount still requires an admin-reviewed claim.

## Prompt and tunnel recovery update

Prompt submission now locks while starting, preserves the prompt on transport failure,
and reads the current run before allowing a retry. An accepted task with a lost response
is reattached without automatically sending another model request. Errors remain visible
under the prompt. Hosted model labels use SPARKLE branding.

An uncertain model response keeps its reservation for manual usage reconciliation. It
no longer freezes every later prompt: one in-flight request and at most three unresolved
requests are allowed per account. Confirmed usage still determines every member charge;
this update does not erase historical holds or invent usage.

The admin dashboard's **Test AI connection** sends a small, fixed diagnostic prompt and
checks the real response and exact usage. It requires the existing admin session, is
rate limited, and does not change member credits. Provider usage still occurs.

For an owner-managed temporary tunnel using `sparkle-engine-tunnel.service`, run
`python3 scripts/recover_engine_tunnel.py` once per minute with a user timer. It checks
loopback before checking the public tunnel, restarts only that app's tunnel after three
failed checks, and reconnects the existing Worker to the new authenticated origin.
Deployments are serialized and retries are bounded. Private deployment receipts
separate successful publishing from an unavailable public health check. This helper
requires the existing owner Wrangler login and configuration; it creates no new database.

Temporary tunnel recovery cannot keep a sleeping or disconnected owner computer online.
For continuous availability, use a persistent host and a stable HTTPS origin. Projects
remain in `HOSTED_DATA` across tunnel and engine restarts.

The production prompt failure was reproduced in workerd: `redirect: 'error'` is
rejected by the Workers runtime before an outbound request is sent. Both the
engine proxy and model transport now use `manual` and refuse redirects without
forwarding secrets. The gateway suite includes a real workerd/D1 test for model
usage settlement, cached retries, engine proxying and redirect rejection.
