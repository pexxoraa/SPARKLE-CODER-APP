# Event-Driven Systems Mastery
Define events as immutable facts with stable schemas and identifiers. Separate commands (“do this”) from events (“this happened”). Consumers must handle duplicates, out-of-order delivery and replay according to their business semantics.

Version schemas compatibly and make dead-letter/retry behavior observable. Avoid using an event bus merely to hide direct dependencies.

Master standard: replay does not corrupt state, duplicate delivery is safe, schema evolution is planned, and event ownership/purpose is clear.