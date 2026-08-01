from pathlib import Path

import pytest

from librarytools.tagging import (
    Rule,
    Sample,
    VocabularyError,
    build_sample,
    count_rules,
    load_vocabulary,
    tags_for,
)


def _vocab(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "vocabulary.toml"
    path.write_text("schema_version = 1\n\n" + body, encoding="utf-8")
    return path


def test_shipped_vocabulary_loads():
    rules = load_vocabulary()
    assert rules
    assert {rule.group for rule in rules} >= {"gear", "style", "character"}


def test_selectors_are_or_and_constraints_are_and():
    rule = Rule(
        name="tribal", group="style",
        origins=("riemann",), name_matches=("conga",), roles=("PERC",),
    )
    perc = Path("CATALOGUE/PERC/perc-conga-1.wav")
    assert rule.matches(Sample("a", perc, origin="somewhere", role="PERC"))
    assert rule.matches(Sample("a", perc, origin="riemann", role="PERC"))
    # role constraint must hold even when a selector fires
    assert not rule.matches(Sample("a", perc, origin="riemann", role="KICKS"))
    # no selector fires
    assert not rule.matches(Sample("a", Path("CATALOGUE/PERC/perc-shaker.wav"), role="PERC"))


def test_feature_only_rule_fires_on_measurements_alone():
    rule = Rule(name="subby", group="character", roles=("KICKS",),
                features=(("sub_ratio", ">=", 0.6),))
    kick = Path("CATALOGUE/KICKS/kick-x.wav")
    assert rule.matches(Sample("a", kick, role="KICKS", features={"sub_ratio": 0.7}))
    assert not rule.matches(Sample("a", kick, role="KICKS", features={"sub_ratio": 0.5}))


def test_missing_measurement_never_fires_a_feature_rule():
    # An unmeasured sample must not be tagged as if it had been measured.
    rule = Rule(name="subby", group="character", features=(("sub_ratio", ">=", 0.6),))
    assert not rule.matches(Sample("a", Path("k.wav"), features={}))
    assert not rule.matches(Sample("a", Path("k.wav"), features={"sub_ratio": None}))


def test_unreadable_feature_test_is_rejected_loudly(tmp_path):
    path = _vocab(tmp_path, '[[tag]]\nname="x"\ngroup="character"\nfeatures={sub_ratio="loud"}\n')
    with pytest.raises(VocabularyError, match="cannot read feature test"):
        load_vocabulary(path)


def test_duplicate_and_incomplete_rules_are_rejected(tmp_path):
    dupe = _vocab(tmp_path, '[[tag]]\nname="a"\ngroup="style"\n\n[[tag]]\nname="a"\ngroup="style"\n')
    with pytest.raises(VocabularyError, match="duplicate tag"):
        load_vocabulary(dupe)
    nameless = _vocab(tmp_path, '[[tag]]\ngroup="style"\n')
    with pytest.raises(VocabularyError, match="name and a group"):
        load_vocabulary(nameless)


def test_role_comes_from_the_name_not_the_folder():
    # Roles must survive a restructure, so they are classified from the path text rather
    # than read off whichever folder the file currently sits in.
    moved = build_sample("a", Path("SOMEWHERE-NEW/anything/kick-909-hard.wav"))
    assert moved.role == "KICKS"


def test_tags_include_origin_and_role_for_querying():
    sample = build_sample("a", Path("CATALOGUE/KICKS/kick-x.wav"), origin="goldbaby-909")
    tags = tags_for(sample, [])
    assert ("origin", "goldbaby-909") in tags
    assert ("role", "KICKS") in tags


def test_unknown_origin_is_not_tagged():
    sample = build_sample("a", Path("CATALOGUE/KICKS/kick-x.wav"), origin="unknown")
    assert not any(group == "origin" for group, _ in tags_for(sample, []))


def test_regenerating_tags_is_idempotent():
    rules = load_vocabulary()
    sample = build_sample(
        "a", Path("CATALOGUE/KICKS/kick-909-x.wav"), origin="goldbaby-super-analog-909",
        features={"sub_ratio": 0.8},
    )
    assert tags_for(sample, rules) == tags_for(sample, rules)


def test_count_rules_reports_every_rule_even_at_zero():
    rules = [Rule(name="nothing", group="style", name_matches=("zzzz",))]
    counts = count_rules([build_sample("a", Path("k.wav"))], rules)
    assert counts[("style", "nothing")][0] == 0
