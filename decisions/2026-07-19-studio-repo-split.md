# 2026-07-19 — Studio wiring moved out to a private repo

Project: eidetic-sample-tools

## Decision

Studio-wiring documentation (the MIDI-sync and Method-A session guides added in
`e649ad7`) is **removed from this public repo**. All physical-studio knowledge —
knowledge base, diagrams, guides, issues log — now lives in the separate
**private** repo `eidetic-studio` (`~/Projects/eidetic-studio`), which is the single source of truth
for studio setup.

This repo stays public and product-only: the sample-library CLI packages. Added
`AGENTS.md`; fixed stale `eidetic-music-tools` repo/config references to
`eidetic-sample-tools` (the repo was renamed on GitHub; only the local remote URL
lagged); repointed the Knowledge Base reference at `~/Projects/eidetic-studio`.

## Rationale

This repo is public. Personal studio wiring (patchbay, channel map, MIDI routing)
should not be world-readable. Keeping the shareable product public and the private
wiring private — both git-tracked — is cleaner than blurring them.

## Consequences

- Studio work happens in `eidetic-studio`; this repo is CLI product only.
- **Open item:** the two guides remain in this repo's *history* (`e649ad7`, already
  on public GitHub). Removing from HEAD stops future exposure; a history scrub
  (git-filter-repo/BFG + force-push) is a separate decision if the exposure matters.
