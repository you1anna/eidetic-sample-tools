# Near-Dupe Pilot Design

## Goal

Add safety-first tooling for likely duplicate sample material that Robin can test on one family or a small batch before any wider processing.

## Scope

- Manifest-first near-dupe detection from `sample-analyze` feature TSVs.
- Pilot outputs: a review TSV, Markdown checklist, and M3U playlist for audition.
- Apply only from a reviewed manifest: rows must be explicitly marked `remove`.
- Move-only, never delete, never overwrite, and write an undo TSV.
- Keep byte-identical `sample-dedupe` unchanged.

## Non-Goals

- No automatic deletion.
- No broad physical re-org from unreviewed scores.
- No audio embeddings or heavy model dependencies.
- No changes to original vendor packs beyond what an approved manifest explicitly asks to stage.

## Design

Create `librarytools.neardupe` and CLI `sample-near-dupes`.

Detection reads `sample-features-latest.tsv` and groups rows by role, sample type, and normalized stem family. After Robin's audition showed short one-shot candidates were not reliable, the default detector only emits long loop pairs (`duration_s >= 3.0`) with high acoustic certainty (`score >= 0.99`). Within each group, rows are paired when cached acoustic features are effectively identical enough to suggest the same long musical material in a different format/folder. Each candidate writes both a `keep_path` and a `candidate_path`; canonical selection prefers `CURATED/`, then shorter audio-friendly formats, then shorter paths.

Pilot selection supports both `--family TEXT` for one family and `--limit-groups N` for a small batch. Pilot artifacts live under `manifests/near-dupes-pilot/` by default and include:

- `near-dupes-latest.tsv` with blank `decision` column;
- `audition/near-dupes.md` checklist;
- `audition/near-dupes.m3u` with keep/candidate paths interleaved.

Apply mode reads a reviewed TSV and stages only rows where `decision=remove` to `_TO-DELETE/near-dupes/<candidate_path>`, using the existing `moves` module so moves are never overwritten and undo is recorded.

## Success Criteria

- Tests prove duplicate-family detection, family/batch pilot filtering, audition artifacts, and approved-only apply.
- Real pilot can run against current `sample-intelligence-pilot/sample-features-latest.tsv` without moving files.
- Documentation shows Robin how to run a one-family or small-batch audition before applying.
