SPARKLE CODER 0.8.0 — FULL WEB WORKSPACE

Keep your existing gateway/.owner, PROJECTS, APP_DATA and HOSTED_DATA.
Use APPLY_UPDATE.sh from the outer update package to check and apply a matching
patch. Do not blindly extract application files over a modified checkout.

After applying, run: bash Deploy_Web_App.sh
Then follow HOSTED_ENGINE.md to connect an owner Python/Docker host.
The Worker alone cannot execute the Python agent or project commands.
Testers use the Worker URL; they do not need installers or API keys.
Existing scratch files remain available at /scratch.html.
No production deployment or owner host provisioning is included in this archive.
