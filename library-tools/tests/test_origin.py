from collections import Counter
from pathlib import Path

from librarytools.origin import (
    UNKNOWN,
    Origin,
    build_token_vocabulary,
    canonical_origin,
    is_generated_name,
    resolve_from_path,
    resolve_library,
    resolve_origin,
    split_origin_token,
    strip_collision_suffix,
    structural_names,
)


def test_split_takes_everything_after_the_first_underscore():
    # `_description` joins with '-' only, so the first underscore is the origin boundary
    # and a multi-word source token stays intact.
    assert split_origin_token("perc-cr78-bongolo-t1s-r4_sa909_samples") == "sa909_samples"
    assert split_origin_token("kick-asr-x-kick-01_sean") == "sean"


def test_unrenamed_vendor_names_are_refused():
    # normalise_token lowercases everything it emits, so uppercase means the file was moved
    # but never renamed — its underscores are the vendor's, not ours.
    assert not is_generated_name("SineBass7_SP1200F")
    assert not is_generated_name("AME_115_C_Lux_Bass")
    assert split_origin_token("SineBass7_SP1200F") == ""
    assert resolve_origin(Path("CATALOGUE/BASS/AME_115_C_Lux_Bass.wav")).origin == UNKNOWN


def test_collision_suffix_collapses_to_one_origin():
    # sort.py appends -2/-3 to a *filename* when a destination name is taken; that is not a
    # new pack, so filename-derived tokens are stripped before canonicalising.
    assert strip_collision_suffix("sa909_samples-2") == "sa909_samples"
    assert canonical_origin("sa909_samples-2", strip_collision=True) == (
        canonical_origin("sa909_samples")
    )
    assert resolve_origin(Path("CATALOGUE/KICKS/kick-x_sa909_samples-2.wav")).origin == (
        "goldbaby-super-analog-909"
    )


def test_folder_names_keep_a_trailing_number():
    # A pack legitimately called "...tribal-techno-1" must not have its -1 stripped as if it
    # were a collision suffix. Only filename tokens get stripped.
    assert canonical_origin("riemann-tribal-techno-1") == "riemann-tribal-techno-1"
    assert resolve_from_path(
        Path("PACKS/riemann-kollektion-riemann-tribal-techno-1/Hits/x.wav")
    ).origin == "riemann-kollektion-riemann-tribal-techno-1"


def test_generic_container_names_resolve_to_unknown():
    assert canonical_origin("samples") == UNKNOWN
    assert canonical_origin("audio") == UNKNOWN
    assert canonical_origin("goldbaby-tape-101") != UNKNOWN


def test_structural_names_are_normalised():
    # `_LEGACY` normalises to `legacy`; before this the raw `_legacy` entry never matched
    # and 1,815 files claimed `legacy` as their pack.
    assert "legacy" in structural_names()
    assert resolve_from_path(Path("CATALOGUE/_LEGACY/SEAN/f.wav")).origin == "sean-archive"


def test_path_folder_beats_filename_and_skips_structure():
    rel = Path("PACKS/echospace-detroit-presents-modulation-space/Loops/x.wav")
    resolved = resolve_from_path(rel)
    assert resolved.origin == "echospace-detroit-presents-modulation-space"
    assert resolved.confidence == "exact"


def test_layout_change_does_not_break_resolution():
    # Zones may be renamed or nested differently later; the scan skips structural names at
    # any depth rather than assuming today's PACKS/CATALOGUE layout.
    assert resolve_from_path(Path("ARCHIVE/riemann-tribal-techno-1/Hits/x.wav")).origin == (
        "riemann-tribal-techno-1"
    )
    assert resolve_from_path(
        Path("SOUNDS/CATALOGUE/one-shots/riemann-tribal-techno-1/x.wav")
    ).origin == "riemann-tribal-techno-1"


def test_vocabulary_ignores_loop_style_names():
    # Loop names are {bpm}_{key}_{desc}_{source}, so the first-underscore rule is wrong for
    # them and they must not pollute the vocabulary.
    vocab = build_token_vocabulary(["kick-x_sa909_samples", "128_am_dark-thing_sa909_samples"])
    assert vocab == Counter({"sa909_samples": 1})


def test_loop_names_resolve_via_longest_known_token():
    vocab = Counter({"sa909_samples": 50, "samples": 90})
    resolved = resolve_origin(Path("CATALOGUE/DRUM-LOOPS/128_am_dark_sa909_samples.wav"), vocab)
    assert resolved.origin == "goldbaby-super-analog-909"


def test_unresolved_samples_are_still_reported():
    # A sample that resolves nowhere must stay in the result as unknown, not drop out of
    # the denominator and inflate the coverage figure.
    best = resolve_library([("aaa", Path("CATALOGUE/BASS/AME_115_C_Lux_Bass.wav"))])
    assert best["aaa"].origin == UNKNOWN


def test_identical_content_inherits_origin_from_its_twin():
    # Same sample_id means identical bytes, so a flattened copy takes the origin of the
    # copy still sitting in a pack folder. Order must not matter.
    flat = Path("CATALOGUE/BASS/AME_115_C_Lux_Bass.wav")
    intact = Path("PACKS/audentity-records-hardgroove/Bass/AME_115_C_Lux_Bass.wav")
    for locations in ([("x", flat), ("x", intact)], [("x", intact), ("x", flat)]):
        assert resolve_library(locations)["x"].origin == "audentity-records-hardgroove"


def test_confidence_never_downgrades():
    exact = Origin("pack", "exact", "path-folder")
    guessed = Origin("other", "guessed", "filename-token-fallback")
    assert guessed.beats(exact) is False
    assert exact.beats(guessed) is True
