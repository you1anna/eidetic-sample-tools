# Studio-aware sample foundation

The repository uses portable TOML profiles to describe capabilities that tools
can act on. The external **Eidetic Studio Knowledge Base v2.4** remains the
authority for physical wiring. Profiles deliberately omit patchbay detail,
purchases, and physical build tasks.

## Library zones

| Zone | Meaning |
|---|---|
| `PACKS/` | Intact source packs and native Octatrack Sets. |
| `CATALOGUE/` | Broad classified material, including legacy role folders. |
| `CURATED/` | Small, ear-approved working pool only. |

Nothing in the workflow deletes audio. Migration moves are dry-run by default
and undo-logged. Favourite promotion copies files; promotion undo moves copies
to `_QUARANTINE/promotion-undo/`.

## Local profile setup

Create `~/.config/eidetic-music-tools/config.toml`:

```toml
profile = "eidetic-studio"
```

Selection order is CLI `--profile`, `MUSIC_TOOLS_PROFILE`, local config, then
the legacy/default profile. Check the versioned snapshot against the Studio KB:

```bash
sample-profile show --profile eidetic-studio
sample-profile validate --profile eidetic-studio \
  --source-kb "/Users/macmini/Projects/Production/Studio/eidetic-studio-knowledge-base-v2_4.md"
```

Validation reads only the document version and update-date header. It never
walks the Studio `archive/` directory.

## Safe operating sequence

### 1. Fresh stable inventory

```bash
sample-analyze --pilot --profile eidetic-studio \
  --library-db library-tools/manifests/sample-library.sqlite
```

The new database is independent of `sample-intelligence.sqlite`. Audio content
is identified by SHA-256, so moves and exact copies do not lose review history.

### 2. Plan catalogue migration

```bash
sample-curate --library-db library-tools/manifests/sample-library.sqlite \
  migrate-catalogue \
  --ableton-root "/Volumes/Extreme SSD/Production/ABLETON_PROJECTS" \
  --manifest library-tools/manifests/catalogue-migration.tsv \
  --undo library-tools/manifests/catalogue-migration-undo.tsv
```

Review the manifest. Add `--apply` only after the Ableton reference preflight,
hash checks, and destination checks pass.

### 3. Audition and label

```bash
sample-curate --library-db library-tools/manifests/sample-library.sqlite \
  prepare --output-dir library-tools/manifests/foundation-v1-review
```

Listen through `audition.m3u8` and complete every `labels.tsv` row with
`reject`, `keep`, or `favourite`. A favourite also requires a canonical
`true_role` and short descriptor.

```bash
sample-curate validate \
  --labels library-tools/manifests/foundation-v1-review/labels.tsv
sample-curate --library-db library-tools/manifests/sample-library.sqlite \
  promote --run-id foundation-v1 \
  --labels library-tools/manifests/foundation-v1-review/labels.tsv
sample-curate --library-db library-tools/manifests/sample-library.sqlite \
  views --output-dir library-tools/manifests/foundation-v1 \
  --labels library-tools/manifests/foundation-v1-review/labels.tsv
```

### 4. Device-specific exports

```bash
# 96 one-shots, native 48 kHz mono
sample-export digitakt --profile eidetic-studio \
  --crate library-tools/manifests/foundation-v1/foundation-v1-one-shots.tsv

# ROLAND/TR-8S/SAMPLE/foundation-v1/, one folder level
sample-export tr8s --profile eidetic-studio \
  --crate library-tools/manifests/foundation-v1/foundation-v1-one-shots.tsv

# All 112 assets, 44.1 kHz, channel layout preserved
sample-export octatrack --profile eidetic-studio \
  --crate library-tools/manifests/foundation-v1/foundation-v1-all.tsv
```

Use `--list` or `--dry-run` before conversion. Digitakt/TR-8S reject long-form
roles; Octatrack accepts the full performance supplement. Add only
`SAMPLES/CURATED/` to Ableton Places and use `ableton-curated.tsv` as the tag
and saved-search reference.
