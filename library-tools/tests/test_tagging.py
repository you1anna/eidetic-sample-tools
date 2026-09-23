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


@pytest.mark.parametrize(("path", "group", "tag"), [
    ("PACKS/Grime/perc_01.wav", "character", "wood"),
    ("PACKS/Warehouse/perc_01.wav", "style", "house"),
    ("PACKS/TR808/perc_01.wav", "gear", "tr8"),
    ("PACKS/Dubai/perc_01.wav", "style", "dub"),
    ("PACKS/Tapestry/perc_01.wav", "gear", "tape"),
])
def test_shipped_word_rules_exclude_nearby_words(path, group, tag):
    sample = build_sample("a", Path(path), origin=Path(path).parent.name)
    assert (group, tag) not in tags_for(sample, load_vocabulary())


@pytest.mark.parametrize(("path", "expected"), [
    ("SA909_BD_01.wav", {("gear", "909")}),
    ("TapeSH101_Bass_01.wav", {("gear", "sh101"), ("gear", "tape")}),
    ("tapesh101_bass_01.wav", {("gear", "sh101"), ("gear", "tape")}),
    ("TR-8_Kick_01.wav", {("gear", "tr8")}),
    ("TR8S_Kick_01.wav", {("gear", "tr8")}),
    ("TR808_Kick_01.wav", {("gear", "808")}),
    ("Perc_Wood_Block_01.wav", {("character", "wood")}),
    ("House_Dub_01.wav", {("style", "house"), ("style", "dub")}),
])
def test_shipped_rules_keep_explicit_gear_compounds_and_words(path, expected):
    assert expected <= set(tags_for(build_sample("a", Path(path)), load_vocabulary()))


@pytest.mark.parametrize(("path", "expected"), [
    ("hit_orig.wav", "original"),
    ("hit_original.wav", "original"),
    ("hit-Orig.aif", "original"),
    ("hit_aorig-r1.wav", "original"),
    ("hit_x.wav", "processed"),
    ("hit_X2.wav", "processed"),
    ("hit-x.wav", "processed"),
    ("hit_processed.wav", "processed"),
])
def test_shipped_processing_rules_preserve_named_suffixes(path, expected):
    assert ("character", expected) in tags_for(build_sample("a", Path(path)), load_vocabulary())


@pytest.mark.parametrize("path", [
    "hit_originality.wav", "hit_aoriginal.wav",
    "hit_x20.wav", "hit_x2extra.wav", "PACKS/pack_orig/hit.wav", "PACKS/pack_x.wav/hit.wav",
])
def test_processing_suffixes_exclude_longer_words_and_folder_names(path):
    tags = tags_for(build_sample("a", Path(path)), load_vocabulary())
    assert ("character", "original") not in tags
    assert ("character", "processed") not in tags


def test_schema_one_custom_vocabulary_preserves_legacy_substrings(tmp_path):
    path = _vocab(tmp_path, '[[tag]]\nname="custom"\ngroup="style"\nname_matches=["dub"]\norigin_matches=["house"]\n')
    rules = load_vocabulary(path)
    assert ("style", "custom") in tags_for(build_sample("a", Path("Dubai.wav")), rules)
    assert ("style", "custom") in tags_for(build_sample("b", Path("hit.wav"), origin="warehouse"), rules)


def test_schema_two_custom_vocabulary_uses_words_aliases_and_suffixes(tmp_path):
    path = tmp_path / "vocabulary.toml"
    path.write_text('''schema_version = 2
[[tag]]
name = "custom-hat"
group = "style"
name_matches = ["hi-hat"]
[[tag]]
name = "custom-house"
group = "style"
origin_matches = ["house"]
[[tag]]
name = "custom-processed"
group = "character"
name_suffixes = ["x2"]
''', encoding="utf-8")
    rules = load_vocabulary(path)
    tags = tags_for(build_sample("a", Path("HiHat_Closed_x2.wav"), origin="warehouse"), rules)
    assert ("style", "custom-hat") in tags
    assert ("character", "custom-processed") in tags
    assert ("style", "custom-house") not in tags
    assert ("style", "custom-house") in tags_for(build_sample("b", Path("hit.wav"), origin="deep-house"), rules)


def test_custom_suffix_selector_rejects_arbitrary_patterns():
    payload = b'schema_version=2\n[[tag]]\nname="x"\ngroup="style"\nname_suffixes=["*orig*"]\n'
    with pytest.raises(VocabularyError, match="name_suffixes"):
        load_vocabulary(payload=payload)


@pytest.mark.parametrize("suffixes", ['"orig"', '[false]', '["orig", 2]'])
def test_custom_suffix_selector_requires_an_array_of_strings(suffixes):
    payload = f'schema_version=2\n[[tag]]\nname="x"\ngroup="style"\nname_suffixes={suffixes}\n'.encode()
    with pytest.raises(VocabularyError, match="name_suffixes"):
        load_vocabulary(payload=payload)
