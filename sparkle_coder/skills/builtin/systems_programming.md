# Systems Programming Mastery
For C, C++ and Rust, make ownership, lifetime, memory layout, concurrency and error boundaries explicit. Prefer simple data structures and deterministic resource management. In C or C++, use RAII where available, avoid unchecked pointer arithmetic and make ownership clear. In Rust, model invariants with types rather than fighting the borrow checker with unnecessary indirection.

Respect ABI, alignment, endian, platform and FFI boundaries. Benchmark hot paths before low-level optimization.

Master standard: resource ownership is obvious, undefined behavior and data races are actively avoided, error paths release resources correctly, and tests cover boundary conditions.