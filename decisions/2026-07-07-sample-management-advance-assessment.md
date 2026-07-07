# Sample Management Advance Assessment

Date: 2026-07-07
Project: eidetic-music-tools
State: Active

## Assessment

`sample-analyze` has enough proven value to keep advancing inside Active: the Tier-1 acoustic pass is fast on a warm cache, read-only, and produces an audition surface over the real SSD sample library. It should not be promoted to Operating yet because the audition queue still needs human ear-checks and the management surface is not stable enough to run as a routine.

Evidence from the 2026-07-07 focus pass:

- POC value is present: 23,251 feature rows, 23,201 clustered rows after the fix, 88 representative clusters, 6 crate manifests.
- Readiness is partial: the pipeline is read-only, cached, and test-covered, but the audition queue needed correctness fixes before Robin should spend ear-check time on it.
- Pull signal is present for personal/studio use: Robin explicitly asked to progress sample organisation and management.

## Recommendation

Do not advance the project state to Operationalising yet. Advance inside Active by removing known audition blockers, then run a real ear-check pass against the regenerated representatives.

## Action Taken

Implemented the first blocker fix:

- `CURATED/<role>` folders are now authoritative when building `sample-analyze` feature rows, so curated role folders are not reclassified by misleading filenames.
- Demo/preview/audition paths are excluded from acoustic clustering, preventing them from becoming representative audition picks.
- Regenerated the real pilot manifests against `/Volumes/Extreme SSD/Production/SAMPLES`.

Verification:

- New TDD tests failed before the production change, then passed after it.
- Full `library-tools` suite: 92 passed.
- Real pilot after fix: 23,251 feature rows, 23,201 clustered rows, 0 demo/preview representatives, 0 KICKS `No Kick` representatives, 0 KICKS `No Kick` feature rows.

## Next Move

Robin should audition the regenerated KICKS representatives first, then mark useful/poor labels. The next agent build step is a manifest-only near-duplicate report using the cached acoustic features; do not move or delete samples until that report is reviewed.
