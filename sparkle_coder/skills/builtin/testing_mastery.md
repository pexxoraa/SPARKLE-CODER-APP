# Testing Mastery
Choose tests by risk. Prefer a small number of meaningful tests that prove user-visible behavior, boundaries, failure handling and regression cases over shallow line-by-line assertions. Reuse the project's existing framework and conventions.

For a bug fix, encode the original failure. For a feature, test the happy path plus the most important invalid/edge condition. Avoid tests that only mirror implementation details, sleep unnecessarily, depend on network randomness, or pass without exercising the real path.

Master standard: tests would fail for the important defect, pass for the correct behavior, and remain understandable to the next maintainer.