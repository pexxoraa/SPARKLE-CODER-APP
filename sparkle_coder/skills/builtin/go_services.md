# Go Services Mastery
Write straightforward Go with small interfaces, explicit errors and context propagation for cancellation and deadlines. Prefer standard-library patterns before frameworks. Keep goroutine ownership clear and never start background work without a stop path.

Use channels for coordination, not as a replacement for clear state ownership. Bound concurrency and preserve wrapped error context. Avoid package globals for mutable runtime state.

Master standard: goroutines cannot leak silently, cancellation reaches outbound work, errors remain diagnosable, and package boundaries stay simple.