# JVM & Kotlin Mastery
Design JVM services and applications with explicit domain boundaries, immutable data where practical, structured concurrency and clear transaction ownership. In Kotlin, use nullability and sealed/domain types instead of pervasive nullable checks; in Java, favor simple explicit types over reflection-heavy frameworks.

Keep blocking and async work separated. Avoid hidden lazy-loading or transaction behavior crossing layers.

Master standard: thread and transaction boundaries are clear, domain errors are explicit, null/state handling is deliberate, and framework annotations do not hide core business rules.