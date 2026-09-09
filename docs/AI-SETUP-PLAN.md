# Reproducible local classification

Keep both existing CLAP checkpoint revisions and existing human approval gates.
No whole-library inference or live-library mutation is part of installation.

1. Resolve a hashed Python 3.12 Apple Silicon dependency snapshot from package
   extras; validate it in a fresh local environment.
2. Expose conservative thread/batch controls and a worker timeout. Preserve
   completed embedding batches and checkpoint identities.
3. Add a small synthetic real-model check reporting cold/cached time and peak
   memory, with offline reuse. Keep large model tests opt-in in CI.
4. Document installation, prefetch/offline use and shortlist-first operation for
   large libraries. Run focused regressions, full tests and both real-model checks.

The user selected explicit `--root`/`SAMPLES_ROOT`. This is implemented, with
missing-selection checks across sample commands; Ableton uses `--root`/`ALS_ROOTS`.

Implementation and local verification are complete. Both original real-model
checks passed offline, as did the synthetic cold/cached resource check. See
[AI setup](AI-SETUP.md) for measured results and reproduction. Remote CI and
verification on the other Mac remain separate.
