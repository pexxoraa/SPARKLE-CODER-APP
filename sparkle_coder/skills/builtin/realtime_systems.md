# Realtime Systems Mastery
For WebSocket/SSE/realtime products, define connection identity, subscription scope, ordering guarantees, backpressure, reconnect and missed-event recovery. Do not assume a live connection is permanent.

Use sequence/version identifiers where clients must reconcile state. Bound fan-out and per-client buffers. Keep authoritative state elsewhere unless the realtime layer is explicitly durable.

Master standard: reconnecting clients can recover correct state, slow clients cannot exhaust the service, and authorization applies to every subscription/channel.