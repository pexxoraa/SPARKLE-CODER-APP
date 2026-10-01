# Code Review Mastery
Review for correctness and risk before style. Trace inputs, state transitions, error paths, concurrency, boundaries and persistence. Look for behavior that tests do not actually prove, duplicated rules, stale state, silent failure and destructive edge cases.

When reporting findings, be specific: file or path, concrete behavior, why it matters, and the smallest credible fix. Separate blocking defects from maintainability improvements. Do not invent issues unsupported by the code.

Master standard: the review helps an engineer act immediately and prioritizes defects by user, reliability and data impact rather than cosmetic preference.