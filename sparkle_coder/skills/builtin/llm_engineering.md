# LLM Engineering Mastery
Design LLM features as probabilistic systems with explicit contracts. Separate model instructions, retrieved/user context, tool results, and untrusted content. Keep prompts versioned and bounded. Choose model, temperature, context size, structured output, retries, and fallbacks based on the product requirement rather than habit.

Treat model output as untrusted data: validate schemas, bound length, handle refusal/empty/truncated responses, and preserve provenance when facts matter. Control cost and latency by reducing unnecessary context/model calls before shrinking capability.

Master standard: behavior is testable across representative prompts, failures degrade safely, costs are bounded, and model-specific quirks are isolated behind a clear interface.