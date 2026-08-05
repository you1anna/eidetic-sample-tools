# Category-scoped audition playlists

**Date:** 2026-08-05
**Status:** Approved design; implementation pending

## Problem

`sample-curate prepare` currently writes every selected candidate to one `audition.m3u8`. The
category remains visible in `labels.tsv`, but a media player receives no category boundary. That
makes an audition session ambiguous and forces the listener to cross-reference a spreadsheet while
audio is playing.

The active `tribal-140-01` packet exposes the problem: its 63 candidates span `RIM`, `TOM`, `PERC`,
`VOCAL`, `VOCAL-LOOP` and `DRUM-LOOP`, but all six roles are flattened into one playlist.

## Outcome

Every curation packet will contain:

- `labels.tsv`, which remains the authoritative candidate and feedback record;
- `audition.m3u8`, retained as the complete packet for backwards compatibility;
- `playlists/<role-slug>.m3u8`, one playlist for every represented `suggested_role`; and
- `playlists/README.md`, an index linking each category playlist and stating its item count.

For `tribal-140-01`, the role files will be:

```text
playlists/
  README.md
  drum-loop.m3u8
  perc.m3u8
  rim.m3u8
  tom.m3u8
  vocal-loop.m3u8
  vocal.m3u8
```

## Generation rules

1. `labels.tsv` is the source of truth after packet creation. Playlist regeneration reads its
   current rows, so a recorded manual trim is preserved.
2. The combined playlist contains every label row once, in label-sheet order.
3. Each category playlist contains exactly the rows whose `suggested_role` matches that category,
   in label-sheet order.
4. Every playlist begins with `#EXTM3U` and contains absolute source paths resolved below the sample
   root. Playlist generation never copies, moves, converts or edits audio.
5. Role filenames use a lowercase, hyphenated slug derived from a trusted role, for example
   `VOCAL-LOOP` becomes `vocal-loop.m3u8`.
6. Regeneration replaces the generated `playlists/` directory so categories removed by a later trim
   cannot survive as stale playlists. It also rewrites the combined playlist.
7. An empty label sheet produces an empty combined playlist and an index stating that no categories
   are present.

## Command and integration

`sample-curate prepare` will call the playlist writer automatically after writing `labels.tsv`.

A new derived-file command will support existing or manually trimmed packets:

```bash
sample-curate playlists \
  --labels library-tools/manifests/tribal-140-01-audition/labels.tsv
```

The command will infer the packet directory from the labels path and resolve the sample root from
that packet's `packet-meta.json`. It will fail clearly if the metadata is missing, malformed or has
no usable root. This prevents a silently guessed root from generating broken playlist paths.

## Current packet repair

After the implementation passes its tests, run the new command against the existing trimmed
`tribal-140-01` label sheet. Do not rerun `prepare`: that would regenerate the original broad
selection and discard the recorded 216 to 63 trim. Verify these exact category counts:

| Category | Expected files |
|---|---:|
| `PERC` | 20 |
| `TOM` | 16 |
| `RIM` | 8 |
| `VOCAL-LOOP` | 8 |
| `DRUM-LOOP` | 7 |
| `VOCAL` | 4 |
| **Combined** | **63** |

Update the packet README with direct links to the six playlists and make category playlists the
primary audition instruction. Keep the combined playlist described as an optional full-packet pass.

## Documentation changes

- Update `docs/WORKFLOWS.md` and `library-tools/README.md` so the normal curation process starts with
  `playlists/README.md`, not the combined playlist.
- Update `eidetic-studio/guides/sample-device-masterplan.md` Phase 2 to require category-scoped
  auditioning and playlist regeneration after a trim.
- Update the active packet README with its generated playlist links and counts.

## Tests and verification

Add tests proving:

1. `prepare_packet` writes the combined playlist, category playlists and index.
2. Every selected label row appears exactly once across the category playlists.
3. Category playlists preserve label-sheet order and contain no rows from another role.
4. Regeneration after editing `labels.tsv` removes stale category files and updates counts.
5. The CLI rejects missing or malformed packet metadata rather than guessing a sample root.
6. The live `tribal-140-01` packet has category counts `20/16/8/8/7/4` and combined count 63.

Run the complete `library-tools` test suite after the focused tests. Playlist generation is correct
only when the tests pass and an independent count of the rebuilt live packet agrees with the label
sheet.

## Out of scope

- Splitting `labels.tsv` into separate category sheets.
- Changing candidate selection, quotas, promotion or export behaviour.
- Writing to `CURATED/`, `_EXPORT/` or removable media.
- Reclassifying any candidate or making listening decisions for Robin.
