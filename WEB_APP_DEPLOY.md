# SPARKLE CODER Web/PWA deployment

This build makes the Cloudflare Worker root URL the tester application. Testers do not need the GitHub ZIP, Python, Node.js, Wrangler, or a desktop installer.

## Tester URL

Use the Worker origin printed by setup, for example:

```text
https://sparkle-pilot-xxxx.sparklecoder.workers.dev
```

The private owner panel remains at `/admin`.

## What testers can do in the browser

- Register or reconnect a tester account.
- See UPI payment details and submit a UTR for admin verification.
- See the available token balance.
- Open a local source folder directly in Chromium browsers that support the File System Access API.
- Use a browser-persistent scratch workspace when direct folder access is unavailable.
- Import a folder into browser storage.
- Edit and save text/code files.
- Ask the shared NVIDIA Nemotron model for coding help using the active file as context.
- Review the returned code and explicitly apply the first fenced code block to the editor.
- Install the site as a PWA when the browser offers installation.

The browser never receives the NVIDIA key, `ADMIN_SECRET`, or `CACHE_SECRET`.

## Deploy over an existing pilot

Keep your current `gateway/.owner` directory. It contains the Worker/D1 configuration for your live deployment and must not be copied into a public ZIP or Git repository.

From the existing repository on the owner computer, the easiest path is:

```sh
cd ~/SPARKLE-CODER
./Deploy_Web_App.sh
```

Or run the same steps manually:

```sh
cd ~/SPARKLE-CODER/gateway
npm test
npx --no-install wrangler deploy --config .owner/wrangler.json
```

A successful deploy prints the same `workers.dev` URL. Open that root URL in a fresh browser tab. It should show the three-column SPARKLE CODER workspace instead of the old installer landing page.

## Browser behavior

Chrome and Edge provide the best direct local-folder editing experience. Opening a folder requires explicit user permission. The browser does not receive unrestricted filesystem access.

Other browsers can still use the scratch workspace and imported files. Scratch/imported files are stored in browser storage; use Download to export the active file when direct disk writing is unavailable.

## Admin flow

The existing `/admin` flow is unchanged. A new tester registers, submits a ₹15 UPI reference, and waits. The owner verifies the payment in the bank/UPI app and approves it in `/admin`. Approval activates the signup device and adds 1,000,000 tokens.

A reconnect request for an existing email is handled through the existing device-approval section in `/admin`.

## Security notes

- Never publish `gateway/.owner`.
- Never put the NVIDIA API key in browser JavaScript or static files.
- Rotate secrets if they are pasted into chat, logs, screenshots, or a public repository.
- The web client sends only prompts and the active file when the user keeps **Include active file as context** enabled.
- AI-generated code is not written automatically. The user must choose Apply and then Save.
