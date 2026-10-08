# Systems Programming Mastery
For C, C++ and Rust, make ownership, lifetime, memory layout, concurrency and error boundaries explicit. Prefer simple data structures and deterministic resource management. In C or C++, use RAII where available, avoid unchecked pointer arithmetic and make ownership clear. In Rust, model invariants with types rather than fighting the borrow checker with unnecessary indirection.

Respect ABI, alignment, endian, platform and FFI boundaries. Benchmark hot paths before low-level optimization.

For CMake projects, discover and honor existing toolchain/preset conventions. Verify in order: configure, build, then CTest if tests are declared. Prefer an out-of-source build under build/; never treat a successful configure as a successful compile. Use --no-tests=error so an empty CTest suite cannot be reported as passing. On platforms requiring a native SDK, explicitly identify unverified targets rather than implying portability.

Master standard: resource ownership is obvious, undefined behavior and data races are actively avoided, error paths release resources correctly, and tests cover boundary conditions.
