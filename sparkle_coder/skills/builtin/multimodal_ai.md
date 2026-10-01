# Multimodal AI Mastery
Handle text, image, audio or video as distinct evidence channels with explicit preprocessing and limits. Preserve ordering and provenance when multiple media items matter. Resize/compress intentionally without destroying details required for the task.

Do not assume a vision/audio model “saw” every detail; ask for structured outputs and validate them. For generated media, separate creative output from factual extraction and retain source metadata when relevant.

Master standard: media size/cost is bounded, modality-specific failure is handled, and downstream logic does not over-trust ambiguous model interpretation.