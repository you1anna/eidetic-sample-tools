# Live tools architecture

The package is independent of library-tools and uses the Python standard library.
Optional library audition calls this transport, while core Live control has no
library database path or dependency.

| Module | Responsibility |
|---|---|
| `client.py` | Loopback-only UDP, per-ACK-port cross-process flock plus thread lock, bounded deadlines/packets, unique request IDs, upstream ACK validation. |
| `reports.py` | Versioned sequential snapshots, differences, expectation checks and runtime doctor. Incomplete/manual results never pass. |
| `edits.py` | Allowlist, path/ID and expected-state guards, saved-byte checkpoint, source hashes, journal-before-send, readback and read-only reconciliation. |
| `staging.py` | Explicit isolated source build, deterministic source identity and staged file manifest. |
| `resources/eidetic_extension.js` | Reserved runtime pseudo-property, new JS-load instance ID and actual Song identity. |
| `_vendor/bridge.py` | Unmodified upstream OSC codec, protocol layouts and strict ACK validators; its standalone CLI is not exposed. |

A reviewed plan records runtime identity, saved Set bytes and per-target state.
Apply holds a cooperating-client lock, checks all prerequisites, writes a fresh
receipt, journals each operation before sending it once and validates readback.
Uncertain writes stop the plan. Reconciliation observes the intended result or
before-state without executing anything. Human actions remain outside that lock.

Core inspection uses bounded upstream property/child RPCs instead of fragmented
project responses. A child resolution failure, interrupted traversal or changed
track roster leaves `complete: false`. The snapshot is explicitly non-atomic;
inspection does not claim a point-in-time full Live state or plugin internals.

Vendored source: [codex-live-bridge](https://github.com/sunflower-of-parchman/codex-live-bridge),
commit `6b9ed94dd471d2b33c3218792e644a4f85fb32e3`. The MIT licence is bundled.
Upstream files remain byte-identical; the staging build appends the isolated
identity extension and updates file references and chosen loopback ports.

Boundary tests cover ACK correlation/content rejection, mutation non-retry,
process-lock exclusion, stale identity/state/file/plan rejection, durable uncertain
receipts, read-only reconciliation, invalid operations, isolated staging and
unverified check results. They are software tests; Max/Live validation is pending.
