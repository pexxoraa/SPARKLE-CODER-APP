# Embedded & IoT Mastery
Design for constrained memory, CPU, power, unreliable networks and long-lived devices. Keep hardware abstraction, protocol handling and application logic separable. Bound buffers and avoid dynamic behavior that cannot be reasoned about under load.

Plan firmware versioning, safe update and rollback, device identity, provisioning and telemetry. Treat physical interfaces and network input as untrusted. Consider brownouts, watchdog resets and offline operation.

Master standard: firmware fails safely, can recover from interrupted updates, has deterministic resource bounds, and device fleet state is observable.