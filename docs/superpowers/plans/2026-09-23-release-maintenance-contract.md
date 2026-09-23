# Release and maintenance implementation plan

**Goal:** Make releases identifiable and library maintenance predictable for CLI clients.

**Architecture:** Public release inspection and a library maintenance planner own
freshness. The studio consumes their versioned JSON; existing identity, locks,
scans, feature caches, backups and approval records remain authoritative.

**Tech stack:** Python 3.12, SQLite, setuptools, pytest; studio standard-library Python.

**Spec:** [Release/maintenance design](../specs/2026-09-23-release-maintenance-contract-design.md).

## Constraints

Work on main. Preserve unrelated work, source audio, approvals and profiles.
Read-only previews; explicit apply; no global installs. Keep private evidence out
of this repo. Packages have independent semantic versions; librarytools is 0.3.0.

## 1. Search and tagging predicates

Ownership: review.py, find.py, tagging.py, vocabulary.toml and its bundled copy,
their focused tests, and a small shared lexical module if required.

- [x] Add failing behavioural regressions for compound hi-hats, percussion, OHat,
      rap/Trap, rim/Grime, house/Warehouse, TR8/TR808 and processing suffixes.
- [x] Implement shared, explicit word/alias rules and keep supported custom rules clear.
- [x] Run focused review/find/tagging/curation tests; report changed semantics.

Representative expectation:

```python
assert matches_query(Match('id', Path('PACKS/HiHat_Closed_01.wav'), 'HATS-CYM', ''),
                     Query(terms=('hihat',)))
assert not matches_query(Match('id', Path('PACKS/Trap/bass.wav'), 'BASS', ''),
                         Query(terms=('rap',)))
```

## 2. Release provenance

Ownership: scripts/release.py, librarytools/release_runtime.py,
resources/release.json, package metadata, release tests and CI release checks.

- [x] Test installed bytes differing from a manifest, same-version source drift,
      optional package absence, checkout comparison and independent versions.
- [x] Implement manifest preparation/checking and runtime_report(checkout=None).
- [x] Runtime report exposes contract_version=1, status, packages, issues and actions;
      it reads actual package bytes and never imports heavyweight optional models.
- [x] Reject a changed runtime with an unchanged package version against a base ref.
- [x] Generate the final manifest only after all production edits are complete.

Representative expectation:

```python
report = runtime_report(checkout=checkout)
assert report['contract_version'] == 1
assert report['status'] == 'action_required'  # installed bytes differ
assert any(action['id'] == 'install_release' for action in report['actions'])
```

## 3. Library maintenance and CLI

Ownership: maintenance.py, inventory.py metadata publication, tag_cli.py stamps,
library_cli.py, maintenance tests and lifecycle documentation.

- [x] Test strict preview immutability and legacy tag staleness on a synthetic library.
- [x] Implement status(root, database_path=None, checkout=None, check_files=False)
      and refresh(root, database_path=None, apply=False, retry_failed=False,
      vocabulary=None, backup_dir=None). Both return contract_version=1 reports.
- [x] Stamp recipe/input fingerprints atomically with generated tags; preserve human tags.
- [x] Test no-op repeat refresh, newly added identity, feature cache reuse, changed/missing
      paths, full-root binding, schema block and existing failures.
- [x] Expose version/status/refresh JSON and text commands with stable exit codes.

Representative expectation:

```python
before = database_path.read_bytes()
report = refresh(root)
assert database_path.read_bytes() == before
assert report['apply'] is False
assert any(a['id'] == 'refresh_tags' for a in report['actions'])
```

## 4. Studio client

Ownership: private studio runtime/preflight/search scripts and their tests.

- [x] Add a public-contract consumer and sample-library discovery alongside finder discovery.
- [x] Test that an old/malformed/incompatible report cannot silently start a fresh search.
- [x] Show status/action guidance in session checks, including optional full file inspection.
- [x] Keep known failed measurements and optional model work visible without blocking search.
- [x] Fix the Python launcher compatibility issue without weakening transfer gates.
- [x] Update studio workflow, issue and current-session records with exact installed evidence.

## 5. Verify, release and install

- [x] Update public lifecycle, architecture, references, changelog and status.
- [x] Run focused tests during edits, then combined toolkit and studio suites.
- [x] Prepare/check the release manifest; build and verify fresh installed wheels.
- [x] Preserve the installed dependency snapshot; install only the reviewed package changes.
- [x] Verify pip dependencies, exact installed hashes and the live maintenance preview.
- [x] Preserve state backup; apply reviewed tag refresh with existing measurements.
- [x] Verify ready status, repeat no-op preview and TR/OT searches; preserve private evidence.
- Commit and push main in the toolkit; use the studio's privacy-checking sync helper.
  The resulting Git history records completion of this integration step.
