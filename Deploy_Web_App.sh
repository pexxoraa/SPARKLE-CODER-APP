#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/gateway"
if [[ ! -f .owner/wrangler.json ]]; then
  echo "Missing gateway/.owner/wrangler.json. Run this from your existing configured SPARKLE-CODER repository."
  exit 1
fi
echo "Running gateway tests..."
npm test
echo "Deploying SPARKLE CODER web/PWA..."
npx --no-install wrangler deploy --config .owner/wrangler.json
echo
echo "Deployment finished. Open the Worker root URL printed above. The admin panel remains at /admin."
