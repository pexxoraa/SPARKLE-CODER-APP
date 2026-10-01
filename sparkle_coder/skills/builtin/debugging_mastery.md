# Debugging Mastery
Debug from evidence, not guesses. Reproduce the failure with the smallest reliable case, inspect the relevant code/data/state, identify the first incorrect assumption or transition, and fix the root cause rather than adding broad fallbacks.

Preserve a clear chain: observed symptom → reproduction → narrowed cause → minimal fix → regression test. Do not rewrite unrelated code while debugging. Distinguish product bugs, environment/setup failures, flaky external services, and invalid tests.

Master standard: the original failure is reproduced before the fix when practical, the fix is narrowly scoped, and a focused regression demonstrates that the same failure cannot return silently.