import csv
from pathlib import Path

import pytest

from librarytools.find import (
    CRATE_FIELDS,
    Match,
    Query,
    descriptor_for,
    distance,
    export_role,
    family,
    matches_query,
    search,
    spread,
    write_crate,
    write_m3u8,
)


def _match(name, role="PERC", origin="pack", tags=(), zone="CATALOGUE"):
    return Match(
        "id-" + name, Path(f"{zone}/{role}/{name}.wav"), role, origin, zone, tuple(tags),
    )


def test_terms_are_and_by_default_and_or_with_any():
    match = _match("x", tags=("tribal", "analog"))
    assert matches_query(match, Query(terms=("tribal", "analog")))
    assert not matches_query(match, Query(terms=("tribal", "metallic")))
    assert matches_query(match, Query(terms=("tribal", "metallic"), any_=True))


def test_group_filters_are_restrictions():
    match = _match("x", role="KICKS", origin="goldbaby-909", tags=("subby",))
    assert matches_query(match, Query(groups={"role": ("kicks",)}))
    assert not matches_query(match, Query(groups={"role": ("perc",)}))
    assert matches_query(match, Query(groups={"origin": ("goldbaby",)}))
    assert matches_query(match, Query(groups={"character": ("subby",)}))
    assert not matches_query(match, Query(groups={"character": ("metallic",)}))


def test_curated_only_excludes_uncurated_zones():
    curated = _match("a", zone="CURATED")
    catalogue = _match("b", zone="CATALOGUE")
    assert search([curated, catalogue], Query(curated_only=True)) == [curated]


def test_empty_query_returns_everything():
    everything = [_match("a"), _match("b")]
    assert search(everything, Query()) == everything


def test_round_robin_takes_share_a_family():
    a = _match("perc-cr78-bongohi-aorig-r1_sa909_samples")
    b = _match("perc-cr78-bongohi-aorig-r3_sa909_samples")
    c = _match("perc-cr78-bongolo-aorig-r1_sa909_samples")
    assert family(a) == family(b)
    assert family(a) != family(c)


def test_spread_shows_variety_before_more_takes():
    # Eight takes of one bongo is a bad answer to "find me a bongo"; one of each first.
    takes = [_match(f"perc-cr78-bongohi-aorig-r{n}_sa909_samples") for n in range(1, 5)]
    others = [_match("perc-ed10-conga1-fat1-r1_sa909_samples")]
    ordered = spread(takes + others)
    assert len(ordered) == 5
    assert family(ordered[0]) != family(ordered[1])


def test_spread_keeps_every_result():
    everything = [_match(f"perc-{n}") for n in range(7)]
    assert sorted(m.sample_id for m in spread(everything)) == sorted(
        m.sample_id for m in everything
    )


def test_export_role_refines_broad_folders():
    assert export_role("KICKS", "kick-909.wav") == "KICK"
    assert export_role("CLAP-SNARE", "clap-gr8-01.wav") == "CLAP"
    assert export_role("CLAP-SNARE", "snare-909.wav") == "SNARE"
    assert export_role("HATS-CYM", "hat-cym-open-909.wav") == "HAT-OPEN"
    assert export_role("HATS-CYM", "hat-cym-closed-909.wav") == "HAT-CLOSED"
    assert export_role("HATS-CYM", "ride-01.wav") == "RIDE"


def test_export_roles_are_all_known_to_the_exporter():
    # sampletools lives in its own venv; this contract check runs when both are installed.
    pytest.importorskip("sampletools")
    from sampletools.export import ROLE_CODES

    for role in ("KICKS", "CLAP-SNARE", "HATS-CYM", "PERC", "BASS", "SYNTH-STAB-CHORD",
                 "DRONE-ATMOS", "FX-RISE-IMPACT", "VOCALS", "DRUM-LOOPS"):
        assert export_role(role, "x.wav") in ROLE_CODES


def test_descriptor_skips_the_redundant_role_prefix():
    # The crate already has a role column, so "kick" tells the reader nothing.
    assert descriptor_for(Path("kick-bd-909bigmuff1_sa909_samples.wav")) == "909bigmu"
    assert descriptor_for(Path("perc-cr78-bongohi_sa909_samples.wav")) == "bongohi"


def test_descriptor_keeps_the_whole_stem_of_an_unrenamed_vendor_name():
    # The _<origin> split only applies to names the sorter generated. A vendor's own name
    # has no origin suffix, so splitting on its first underscore leaves a useless prefix.
    assert descriptor_for(Path("AU_HHT_kick_one_shot_balancer.wav")) == "balancer"
    assert descriptor_for(Path("Kick001.wav")) == "kick001"


def test_crate_schema_matches_what_the_exporter_reads(tmp_path):
    pytest.importorskip("sampletools")
    from sampletools.export import read_crate_tsv

    crate = tmp_path / "kit.tsv"
    write_crate([_match("perc-conga-1", role="PERC")], crate, "perc tribal")
    with crate.open() as fh:
        assert tuple(next(csv.reader(fh, delimiter="\t"))) == CRATE_FIELDS
    rows = read_crate_tsv(crate)
    assert len(rows) == 1 and rows[0].role == "PERC"


def test_distance_is_zero_for_identical_and_ignores_missing_dimensions():
    ranges = [(0.0, 1.0), (0.0, 10.0)]
    assert distance([0.5, 5.0], [0.5, 5.0], ranges) == 0.0
    assert distance([0.5, None], [0.5, 9.0], ranges) == 0.0
    assert distance([0.0, None], [1.0, None], ranges) == 1.0
    assert distance([None, None], [None, None], ranges) is None


def test_playlist_lists_absolute_paths(tmp_path):
    playlist = tmp_path / "audition.m3u8"
    write_m3u8(Path("/library"), [_match("a")], playlist)
    assert playlist.read_text().strip() == "/library/CATALOGUE/PERC/a.wav"
