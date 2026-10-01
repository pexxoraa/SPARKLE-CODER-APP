# JavaScript & TypeScript Mastery
Keep state and side effects explicit. Use platform/browser APIs directly for small work; introduce libraries only when they materially simplify the problem. Prefer event delegation and small functions over tangled global handlers. In TypeScript, use types to model real states rather than blanket casts or any.

Handle async work deliberately: cancellation, stale responses, error states and double-submit/race behavior matter. Avoid unnecessary build complexity, giant components and mutation hidden across modules.

Master standard: behavior is deterministic under rapid user interaction, errors are surfaced appropriately, and the code remains easy to trace from event to state change to rendered result.