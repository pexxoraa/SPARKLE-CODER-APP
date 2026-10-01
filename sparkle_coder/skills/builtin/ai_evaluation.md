# AI Evaluation Mastery
Evaluate AI behavior with a representative dataset, not a handful of happy prompts. Define dimensions such as correctness, instruction following, groundedness, safety, tool use, latency and cost. Use deterministic checks where possible and model/judge scoring only where human-like judgment is necessary.

Maintain regression cases from real failures. Compare prompt/model changes against the same set and track tradeoffs rather than optimizing one aggregate number blindly.

Master standard: an AI change cannot ship solely because examples “look better”; it has reproducible before/after evidence and protects known failure cases.