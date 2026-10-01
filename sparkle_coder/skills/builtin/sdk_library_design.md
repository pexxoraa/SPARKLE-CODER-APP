# SDK & Library Design Mastery
Design the public API for stability and misuse resistance. Keep the surface small, names consistent, defaults safe and errors typed and actionable. Hide transport or storage implementation details behind clear domain interfaces.

Plan backward compatibility, semantic versioning, deprecation and test fixtures. Avoid global mutable state and surprising side effects on import or construction.

Master standard: a new consumer can discover the common path from types and docs, upgrades do not break silently, and invalid states are difficult to represent.