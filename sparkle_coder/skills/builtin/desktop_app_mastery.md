# Desktop App Mastery
Respect desktop expectations: windows, keyboard, files, drag/drop, long-running tasks, updates and local persistence. Keep UI responsiveness separate from blocking work. Treat local filesystem access as a capability with path and symlink boundaries.

Use native packaging/updating conventions for the target platform and preserve user data across upgrades. Avoid web-only interaction assumptions when keyboard/menu/window behavior matters.

Master standard: long operations do not freeze the UI, file operations are recoverable, settings/data survive updates, and platform-specific behavior is explicit.