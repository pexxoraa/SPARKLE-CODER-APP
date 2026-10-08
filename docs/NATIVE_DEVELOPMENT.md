# Native C/C++ Development in SPARKLE CODER

SPARKLE CODER supports native development through its existing workspace tools and
command runner. The check-discovery feature suggests a **reviewable** CMake workflow;
it does not automatically execute project scripts or install dependencies.

## Local versus hosted execution

**Use local execution for Vulkan, OpenGL, SDL3, GPU debugging and large C++ builds.**
Your workstation must have the compiler, CMake and target SDKs installed. The
browser-hosted command environment is intentionally limited to 2 CPUs, 4 GiB RAM,
no network, a fixed tools image and short command timeouts. The bundled hosted
image does not ship SDL3/Vulkan SDKs or GPU access. Do not claim a native
application has been run just because the agent generated its source code.

## Suggested checks for a CMake project

For a folder containing `CMakeLists.txt`, the agent can discover, in order:

```sh
cmake -S . -B build/sparkle-coder -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build/sparkle-coder --parallel 2
```

If a CMake file declares `include(CTest)`, `enable_testing()` or `add_test()`,
the agent also discovers:

```sh
ctest --test-dir build/sparkle-coder --output-on-failure --no-tests=error
```

`--no-tests=error` avoids a false-green run when CTest discovers no tests.
CMake build output lives under `build/`, which is ignored by the agent file
scanner. A source folder with a nested `CMakeLists.txt` isn't assumed to be an
independent project unless it declares `project(...)` or has no parent CMake
root. These commands are **candidates**: they still require the normal
command/verification authorization, available toolchains and genuine execution.

On Windows the default CMake generator may differ from Linux; project-defined
CMake presets, toolchains, cross-compilers and release configurations can
require an explicit user-provided command. Do not silently replace a project's
existing build convention. Configure before building; build before testing.
Successful compilation is not evidence of correct graphics or vehicle physics.

## Release-quality development checklist

1. Record the project requirements and concrete acceptance criteria.
2. Read existing build files before editing any source.
3. Make small, reversible changes; preserve manual edits and project history.
4. Run configure, build and applicable unit/integration tests.
5. Run native software on target hardware when behavior depends on GPUs,
   input devices, OS APIs or timing; report tests not executed.
6. Profile CPU and GPU frame budgets with real tools; don't invent FPS.
7. Confirm release packaging, dependencies, security and license compliance.
8. Inspect actual test output and never mark missing tests as passed.

For cross-platform games, use one portable C++ core with platform adapters.
Linux validation alone does **not** establish macOS, iOS, Windows or Android
compatibility. Apple builds require Apple toolchains and appropriate machines.
