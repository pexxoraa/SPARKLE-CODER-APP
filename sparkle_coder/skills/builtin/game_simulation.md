# Game & Simulation Engineering Mastery
Separate simulation state from rendering, input, AI decision logic and game rules. Define update frequency, deterministic or nondeterministic behavior, entity ownership and asset lifecycle explicitly. Use fixed-step logic with an accumulator for physics when appropriate; bound catch-up steps to avoid runaway spiral-of-death behavior. Interpolate render state where necessary without changing simulation timestep.

Validate gameplay using reproducible test cases (acceleration, braking, stability at varying frame rates, lap timing, collision handling and AI decisions). Distinguish physical units and coordinate conversions. Do not invent benchmark, telemetry or regulatory numbers. GPU-dependent rendering, input devices and OS packaging need tests on actual hardware, not just code generation.

Profile frame time, allocations and loading before optimizing. Treat save/load, scene transitions and multiplayer synchronization as state-machine problems, not ad-hoc callbacks. For cross-platform games, keep a portable simulation core and small platform-specific integrations.

Master standard: simulation remains stable across frame-rate variation, resources are loaded and released predictably, and performance budgets are measurable.
