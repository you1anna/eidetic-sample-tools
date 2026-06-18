# Token-Aware Abbreviation Classification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve ~1,749 of the 3,898 unmatched `_REVIEW` samples by matching drum-machine instrument abbreviations at token boundaries.

**Architecture:** Add a token-set matcher to `classify_role` that runs *after* the existing full-word role rules and *before* the generic loop/duration fallback. Short codes (`hh`, `hho`, `rs`, `cow`…) match only as whole tokens, so previously-unmatched files get categorized without regressing existing high-confidence matches.

**Tech Stack:** Python 3.12, pytest, existing `librarytools.review` module.

## Global Constraints

- `sample-review` is manifest-only — no file moves/renames/deletes. Analysis only.
- Short codes (≤3 chars) match ONLY as whole tokens (avoid `chord`→`ch`, `ohio`→`oh`).
- Drum-machine *model* tokens (`cr78`, `xd5`, `tr55`, `sp1200`) are NOT keywords.
- Precedence unchanged: drum-loop → full-word role rules → **new abbrev tokens** → loop/duration fallback.
- venv interpreter: `~/.venvs/library-tools/bin/python` / `pytest`.

---

### Task 1: Token-boundary abbreviation matching in `classify_role`

**Files:**
- Modify: `src/librarytools/review.py` (add `_tokens`, `ROLE_ABBREV`; extend `classify_role`)
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `_parts_text(rel)`, `_TOKEN_SPLIT_RE`, `RoleResult` (existing).
- Produces: `_tokens(rel: Path) -> set[str]`; module constant `ROLE_ABBREV`; `classify_role` now returns role `HATS-CYM`/`PERC`/`CLAP-SNARE` for abbreviation tokens with `reason="token:<code>"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_drum_machine_abbreviations_map_to_roles():
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.Super.Analog.909/SA909_HH/HH_909D2_AC_R6.wav")
    ).role == "HATS-CYM"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.Super.Analog.909/SA909_HH/HHo_909D2_AC_R2.wav")
    ).role == "HATS-CYM"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SA909/TDMVol2_Samples/CR-78/CR78_Clave_T1S_R1.wav")
    ).role == "PERC"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SA909/Vol2/RX-5/RX5_CowHigh_C2A.wav")
    ).role == "PERC"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SP-1200.Vol.2/707_727_vs_SP1200/Cabasa_727TR1_SP1200R.wav")
    ).role == "PERC"


def test_abbreviations_do_not_false_match_full_words():
    # 'chord' must not hit hat-code 'ch'; 'ohio' must not hit 'oh'
    assert review.classify_role(
        Path("_PACKS/Keys/Chord stack warm.wav")
    ).role == "SYNTH-STAB-CHORD"
    assert review.classify_role(
        Path("_PACKS/Field/Ohio rainstorm.wav")
    ).role != "HATS-CYM"


def test_cryptic_sean_names_stay_in_review():
    assert review.classify_role(Path("_PACKS/Sean/Sean 80s/o.wav")).role == "_REVIEW"
    assert review.classify_role(Path("_PACKS/Sean/cloud 909/dms2.wav")).role == "_REVIEW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/library-tools/bin/pytest tests/test_review.py -k "abbreviation or cryptic_sean" -v`
Expected: FAIL — abbreviation cases return `_REVIEW` instead of the instrument role.

- [ ] **Step 3: Implement token matcher**

In `src/librarytools/review.py`, after `_parts_text`:

```python
def _tokens(rel: Path) -> set[str]:
    """Whole-token set of the normalised path (folders + filename)."""
    return {t for t in _TOKEN_SPLIT_RE.split(_parts_text(rel)) if t}


# Short instrument codes matched ONLY as whole tokens, so 'chord' never hits
# 'ch' and 'ohio' never hits 'oh'. Drum-machine model names are excluded.
ROLE_ABBREV: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("HATS-CYM", ("hh", "hho", "hhc", "ohh", "chh")),
    ("CLAP-SNARE", ("rs",)),
    ("PERC", (
        "cow", "clave", "claves", "cabasa", "conga", "congas", "block",
        "tamb", "agogo", "quijada", "timb", "timbale", "tabla", "tri",
        "triangle", "guiro", "maraca", "maracas", "whistle",
    )),
)
```

In `classify_role`, after the `for role, needles in role_rules:` loop and before the `loop = _contains(...)` line:

```python
    tokens = _tokens(rel)
    for role, codes in ROLE_ABBREV:
        hit = tokens.intersection(codes)
        if hit:
            return RoleResult(role, "high", f"token:{sorted(hit)[0]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/library-tools/bin/pytest tests/test_review.py -v`
Expected: PASS (all, including pre-existing tests).

- [ ] **Step 5: Measure real impact (manifest-only, no moves)**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools/library-tools" && ~/.venvs/library-tools/bin/sample-review --no-probe --summary | sed -n '/_REVIEW/p;/confidence/,/sample type/p'`
Expected: `_REVIEW` count drops from 3,898 toward ≈2,000; HATS-CYM and PERC counts rise.

- [ ] **Step 6: Commit**

```bash
git add src/librarytools/review.py tests/test_review.py
git commit -m "feat(review): classify drum-machine abbreviations by whole token"
```

---

### Task 2: Regenerate indexes and verify no false positives

**Files:**
- Regenerate: `manifests/index-latest/` (gitignored — not committed)

- [ ] **Step 1: Regenerate the split indexes**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools/library-tools" && ~/.venvs/library-tools/bin/sample-review --no-probe --output manifests/review-latest.tsv --index-dir manifests/index-latest`

- [ ] **Step 2: Spot-check new HATS/PERC rows for false positives**

Run: `tail -n +2 manifests/index-latest/high-confidence/HATS-CYM.tsv | grep -i "token:" | awk 'NR%50==1' | cut -f1,11`
Expected: every sampled row is genuinely a hat/cymbal; no chords/keys/loops mislabelled.

- [ ] **Step 3: Confirm remaining `_REVIEW` is the expected cryptic remainder**

Run: `wc -l manifests/index-latest/review-needed.tsv`
Expected: ≈2,000 rows, dominated by `_PACKS/Sean/*` cryptic names (acceptable per spec Tier 3).

---

## Self-Review

- **Spec coverage:** Tier 1 abbreviations → Task 1. Token-boundary safety → Task 1 Step 1 regression test. Tier 3 stays `_REVIEW` → Task 1 cryptic-name test. Success criteria (count drop, no false positives) → Task 1 Step 5 + Task 2. ✓
- **Placeholders:** none. ✓
- **Type consistency:** `_tokens` returns `set[str]`; `ROLE_ABBREV` is `tuple[tuple[str, tuple[str,...]],...]`; `classify_role` returns `RoleResult`. ✓
