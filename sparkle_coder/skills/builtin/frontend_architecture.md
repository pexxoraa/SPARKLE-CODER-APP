# Frontend Architecture Mastery
Choose architecture proportional to the product. For a small static experience, semantic HTML and CSS with minimal JavaScript are often superior to a framework. For a stateful application, define clear component and state boundaries and keep server/client authority explicit.

Prevent stale async responses, duplicate submissions, accidental global state and UI states that cannot be reached or recovered from. Keep accessibility, loading, empty, error and reconnect states part of the design.

Master standard: the frontend has a small understandable state model, predictable data flow and no framework complexity that the feature set does not justify.