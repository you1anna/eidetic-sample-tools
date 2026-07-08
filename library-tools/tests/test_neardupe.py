from __future__ import annotations

import csv
from pathlib import Path

from librarytools import neardupe


HEADER = [
    "path",
    "source_kind",
    "source_name",
    "role",
    "sample_type",
    "bpm",
    "key",
    "tempo_fit",
    "duration",
    "duration_s",
    "peak",
    "rms",
    "crest",
    "attack_ms",
    "tail_ms",
    "head_silence_ms",
    "tail_silence_ms",
    "centroid_hz",
    "flatness",
    "sub_ratio",
    "low_ratio",
    "mid_ratio",
    "high_ratio",
    "onset_density",
    "zcr",
    "audio_error",
    "proposed_name",
    "review_reason",
    "processing_tag",
    "processing_reason",
    "character_tags",
    "tag_reasons",
]


def _row(path: str, proposed_name: str, *, role: str = "KICKS", sub: float = 0.82, centroid: float = 150.0) -> dict[str, str]:
    row = {key: "" for key in HEADER}
    row.update(
        {
            "path": path,
            "source_kind": "curated-sample" if path.startswith("CURATED/") else "vendor-pack-audio",
            "source_name": "Vendor",
            "role": role,
            "sample_type": "one-shot",
            "duration": "0.31",
            "duration_s": "0.31",
            "peak": "0.9",
            "rms": "0.3",
            "crest": "8.0",
            "attack_ms": "3.2",
            "tail_ms": "160.0",
            "head_silence_ms": "0.0",
            "tail_silence_ms": "10.0",
            "centroid_hz": str(centroid),
            "flatness": "0.02",
            "sub_ratio": str(sub),
            "low_ratio": "0.91",
            "mid_ratio": "0.07",
            "high_ratio": "0.02",
            "onset_density": "0.4",
            "zcr": "0.02",
            "proposed_name": proposed_name,
            "character_tags": "subby;short",
            "tag_reasons": "test",
        }
    )
    return row


def _write_features(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER, delimiter="	")
        writer.writeheader()
        writer.writerows(rows)


def test_find_groups_matches_same_family_with_close_acoustics(tmp_path: Path):
    features = tmp_path / "features.tsv"
    _write_features(
        features,
        [
            _row("CURATED/KICKS/Kick 909.wav", "kick-909.wav"),
            _row("PACKS/Vendor/Kicks/Kick 909.aif", "kick-909.wav", sub=0.83, centroid=152.0),
            _row("PACKS/Vendor/Kicks/Kick Other.wav", "kick-other.wav", sub=0.40, centroid=900.0),
        ],
    )

    rows = neardupe.load_feature_rows(features)
    groups = neardupe.find_groups(rows)

    assert len(groups) == 1
    group = groups[0]
    assert group.family == "kick-909"
    assert group.keep_path == Path("CURATED/KICKS/Kick 909.wav")
    assert [candidate.path for candidate in group.candidates] == [Path("PACKS/Vendor/Kicks/Kick 909.aif")]
    assert group.candidates[0].confidence == "high"
    assert "stem-family" in group.candidates[0].reason


def test_select_groups_and_write_audition_outputs_reviewable_pilot(tmp_path: Path):
    rows = [
        neardupe.FeatureRow(Path("CURATED/KICKS/Kick 909.wav"), "KICKS", "one-shot", "kick-909", 0.31, 160.0, 0.82, 0.91, 0.07, 0.02, 150.0, 0.02, 0.4, 0.02, "subby;short"),
        neardupe.FeatureRow(Path("PACKS/Vendor/Kicks/Kick 909.aif"), "KICKS", "one-shot", "kick-909", 0.31, 161.0, 0.83, 0.91, 0.07, 0.02, 152.0, 0.02, 0.4, 0.02, "subby;short"),
        neardupe.FeatureRow(Path("CURATED/KICKS/Kick 808.wav"), "KICKS", "one-shot", "kick-808", 0.30, 120.0, 0.90, 0.95, 0.04, 0.01, 120.0, 0.02, 0.5, 0.01, "subby;short"),
        neardupe.FeatureRow(Path("PACKS/Vendor/Kicks/Kick 808.wav"), "KICKS", "one-shot", "kick-808", 0.30, 121.0, 0.91, 0.95, 0.04, 0.01, 121.0, 0.02, 0.5, 0.01, "subby;short"),
    ]
    groups = neardupe.find_groups(rows)

    selected = neardupe.select_groups(groups, family="kick-909", limit_groups=10)
    out = tmp_path / "near-dupes.tsv"
    audition = tmp_path / "audition"
    neardupe.write_review(out, selected)
    neardupe.write_audition(audition, selected, Path("/Samples"))

    written = list(csv.DictReader(out.open(), delimiter="	"))
    assert len(written) == 1
    assert written[0]["decision"] == ""
    assert written[0]["keep_path"] == "CURATED/KICKS/Kick 909.wav"
    assert written[0]["candidate_path"] == "PACKS/Vendor/Kicks/Kick 909.aif"
    assert "PACKS/Vendor/Kicks/Kick 808.wav" not in (audition / "near-dupes.m3u").read_text()
    assert "/Samples/CURATED/KICKS/Kick 909.wav" in (audition / "near-dupes.m3u").read_text()
    assert "decision: keep/remove" in (audition / "near-dupes.md").read_text()


def test_build_apply_plan_uses_only_rows_marked_remove(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    keep = root / "CURATED" / "KICKS" / "Kick 909.wav"
    remove = root / "PACKS" / "Vendor" / "Kicks" / "Kick 909.aif"
    ignored = root / "PACKS" / "Vendor" / "Kicks" / "Kick 808.aif"
    for path in (keep, remove, ignored):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name)
    reviewed = tmp_path / "reviewed.tsv"
    with reviewed.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=neardupe.REVIEW_FIELDS, delimiter="	")
        writer.writeheader()
        writer.writerow({
            "decision": "remove",
            "group_id": "KICKS:one-shot:kick-909",
            "family": "kick-909",
            "role": "KICKS",
            "sample_type": "one-shot",
            "keep_path": "CURATED/KICKS/Kick 909.wav",
            "candidate_path": "PACKS/Vendor/Kicks/Kick 909.aif",
            "confidence": "high",
            "score": "0.98",
            "reason": "test",
        })
        writer.writerow({
            "decision": "",
            "group_id": "KICKS:one-shot:kick-808",
            "family": "kick-808",
            "role": "KICKS",
            "sample_type": "one-shot",
            "keep_path": "CURATED/KICKS/Kick 808.wav",
            "candidate_path": "PACKS/Vendor/Kicks/Kick 808.aif",
            "confidence": "high",
            "score": "0.98",
            "reason": "test",
        })

    plan = neardupe.build_apply_plan(root, reviewed)

    assert len(plan) == 1
    assert plan[0].src == remove
    assert plan[0].dest == root / "_TO-DELETE" / "near-dupes" / "PACKS" / "Vendor" / "Kicks" / "Kick 909.aif"
    assert plan[0].tag == "near-dupe"


def test_main_apply_stages_only_approved_rows(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    keep = root / "CURATED" / "KICKS" / "Kick 909.wav"
    remove = root / "PACKS" / "Vendor" / "Kicks" / "Kick 909.aif"
    for path in (keep, remove):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name)
    reviewed = tmp_path / "reviewed.tsv"
    with reviewed.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=neardupe.REVIEW_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow({
            "decision": "remove",
            "group_id": "KICKS:one-shot:kick-909",
            "family": "kick-909",
            "role": "KICKS",
            "sample_type": "one-shot",
            "keep_path": "CURATED/KICKS/Kick 909.wav",
            "candidate_path": "PACKS/Vendor/Kicks/Kick 909.aif",
            "confidence": "high",
            "score": "0.98",
            "reason": "test",
        })
    monkeypatch.setattr(neardupe.config, "MANIFEST_DIR", tmp_path / "manifests")

    code = neardupe.main(["--root", str(root), "--apply-manifest", str(reviewed), "--apply"])

    assert code == 0
    assert keep.exists()
    assert not remove.exists()
    assert (root / "_TO-DELETE" / "near-dupes" / "PACKS" / "Vendor" / "Kicks" / "Kick 909.aif").exists()
    undo_files = list((tmp_path / "manifests").glob("undo-near-dupes-*.tsv"))
    assert len(undo_files) == 1
    assert "_TO-DELETE/near-dupes/PACKS/Vendor/Kicks/Kick 909.aif" in undo_files[0].read_text()
