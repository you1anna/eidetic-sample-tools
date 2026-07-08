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


def _row(
    path: str,
    proposed_name: str,
    *,
    role: str = "DRONE-ATMOS",
    sample_type: str = "loop",
    duration: float = 32.126,
    tail: float = 21226.6,
    sub: float = 0.728996,
    centroid: float = 739.434,
) -> dict[str, str]:
    row = {key: "" for key in HEADER}
    row.update(
        {
            "path": path,
            "source_kind": "curated-sample" if path.startswith("CURATED/") else "vendor-pack-audio",
            "source_name": "Vendor",
            "role": role,
            "sample_type": sample_type,
            "duration": str(duration),
            "duration_s": str(duration),
            "peak": "0.9",
            "rms": "0.3",
            "crest": "8.0",
            "attack_ms": "3.2",
            "tail_ms": str(tail),
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


def test_find_groups_matches_long_high_certainty_loops_and_ignores_short_hits(tmp_path: Path):
    features = tmp_path / "features.tsv"
    _write_features(
        features,
        [
            _row(
                "CURATED/DRONE-ATMOS/Echospace/modulation-space-loop-1.wav",
                "127-echospace-detroit-presents-modulation-space-1-drone-atmos.wav",
            ),
            _row(
                "CURATED/DRONE-ATMOS/Echospace [FLAC]/modulation-space-loop-1.flac",
                "127-echospace-detroit-presents-modulation-space-1-drone-atmos.wav",
            ),
            _row(
                "CURATED/CLAP-SNARE/One Shot gr8 Claps/GR8_GREAT_CLAPS_100.wav",
                "clap-snare-gr8-great-claps-clap-snare.wav",
                role="CLAP-SNARE",
                sample_type="one-shot",
                duration=0.853923,
                tail=830.023,
                sub=0.011478,
                centroid=4001.08,
            ),
            _row(
                "CURATED/CLAP-SNARE/One Shot gr8 Claps/GR8_GREAT_CLAPS_136.wav",
                "clap-snare-gr8-great-claps-clap-snare.wav",
                role="CLAP-SNARE",
                sample_type="one-shot",
                duration=1.3,
                tail=866.848,
                sub=0.00683317,
                centroid=3239.38,
            ),
        ],
    )

    rows = neardupe.load_feature_rows(features)
    groups = neardupe.find_groups(rows)

    assert len(groups) == 1
    group = groups[0]
    assert group.family == "127-echospace-detroit-presents-modulation-space-1-drone-atmos"
    assert group.keep_path == Path("CURATED/DRONE-ATMOS/Echospace/modulation-space-loop-1.wav")
    assert [candidate.path for candidate in group.candidates] == [
        Path("CURATED/DRONE-ATMOS/Echospace [FLAC]/modulation-space-loop-1.flac")
    ]
    assert group.candidates[0].confidence == "high"
    assert "long-loop" in group.candidates[0].reason


def test_select_groups_and_write_audition_outputs_reviewable_pilot(tmp_path: Path):
    rows = [
        neardupe.FeatureRow(Path("CURATED/DRONE-ATMOS/Echospace/loop-1.wav"), "DRONE-ATMOS", "loop", "echospace-loop-1", 32.0, 21000.0, 0.72, 0.88, 0.10, 0.02, 740.0, 0.02, 1.0, 0.01, "subby;long"),
        neardupe.FeatureRow(Path("CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-1.flac"), "DRONE-ATMOS", "loop", "echospace-loop-1", 32.0, 21000.0, 0.72, 0.88, 0.10, 0.02, 740.0, 0.02, 1.0, 0.01, "subby;long"),
        neardupe.FeatureRow(Path("CURATED/DRONE-ATMOS/Echospace/loop-2.wav"), "DRONE-ATMOS", "loop", "echospace-loop-2", 31.0, 20500.0, 0.70, 0.87, 0.11, 0.02, 720.0, 0.02, 1.0, 0.01, "subby;long"),
        neardupe.FeatureRow(Path("CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-2.flac"), "DRONE-ATMOS", "loop", "echospace-loop-2", 31.0, 20500.0, 0.70, 0.87, 0.11, 0.02, 720.0, 0.02, 1.0, 0.01, "subby;long"),
    ]
    groups = neardupe.find_groups(rows)

    selected = neardupe.select_groups(groups, family="echospace-1", limit_groups=10)
    out = tmp_path / "near-dupes.tsv"
    audition = tmp_path / "audition"
    neardupe.write_review(out, selected)
    neardupe.write_audition(audition, selected, Path("/Samples"))

    written = list(csv.DictReader(out.open(), delimiter="	"))
    assert len(written) == 1
    assert written[0]["decision"] == ""
    assert written[0]["keep_path"] == "CURATED/DRONE-ATMOS/Echospace/loop-1.wav"
    assert written[0]["candidate_path"] == "CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-1.flac"
    assert "CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-2.flac" not in (audition / "near-dupes.m3u").read_text()
    assert "/Samples/CURATED/DRONE-ATMOS/Echospace/loop-1.wav" in (audition / "near-dupes.m3u").read_text()
    assert "decision: keep/remove" in (audition / "near-dupes.md").read_text()


def test_build_apply_plan_uses_only_rows_marked_remove(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    keep = root / "CURATED" / "DRONE-ATMOS" / "Echospace" / "loop-1.wav"
    remove = root / "CURATED" / "DRONE-ATMOS" / "Echospace [FLAC]" / "loop-1.flac"
    ignored = root / "CURATED" / "DRONE-ATMOS" / "Echospace [FLAC]" / "loop-2.flac"
    for file_path in (keep, remove, ignored):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_path.name)
    reviewed = tmp_path / "reviewed.tsv"
    with reviewed.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=neardupe.REVIEW_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow({
            "decision": "remove",
            "group_id": "DRONE-ATMOS:loop:echospace-1",
            "family": "echospace-1",
            "role": "DRONE-ATMOS",
            "sample_type": "loop",
            "keep_path": "CURATED/DRONE-ATMOS/Echospace/loop-1.wav",
            "candidate_path": "CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-1.flac",
            "confidence": "high",
            "score": "1.000",
            "reason": "long-loop;acoustic-score=1.000",
        })
        writer.writerow({
            "decision": "",
            "group_id": "DRONE-ATMOS:loop:echospace-2",
            "family": "echospace-2",
            "role": "DRONE-ATMOS",
            "sample_type": "loop",
            "keep_path": "CURATED/DRONE-ATMOS/Echospace/loop-2.wav",
            "candidate_path": "CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-2.flac",
            "confidence": "high",
            "score": "1.000",
            "reason": "long-loop;acoustic-score=1.000",
        })

    plan = neardupe.build_apply_plan(root, reviewed)

    assert len(plan) == 1
    assert plan[0].src == remove
    assert plan[0].dest == root / "_TO-DELETE" / "near-dupes" / "CURATED" / "DRONE-ATMOS" / "Echospace [FLAC]" / "loop-1.flac"
    assert plan[0].tag == "near-dupe"


def test_main_apply_stages_only_approved_rows(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    keep = root / "CURATED" / "DRONE-ATMOS" / "Echospace" / "loop-1.wav"
    remove = root / "CURATED" / "DRONE-ATMOS" / "Echospace [FLAC]" / "loop-1.flac"
    for file_path in (keep, remove):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_path.name)
    reviewed = tmp_path / "reviewed.tsv"
    with reviewed.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=neardupe.REVIEW_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow({
            "decision": "remove",
            "group_id": "DRONE-ATMOS:loop:echospace-1",
            "family": "echospace-1",
            "role": "DRONE-ATMOS",
            "sample_type": "loop",
            "keep_path": "CURATED/DRONE-ATMOS/Echospace/loop-1.wav",
            "candidate_path": "CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-1.flac",
            "confidence": "high",
            "score": "1.000",
            "reason": "long-loop;acoustic-score=1.000",
        })
    monkeypatch.setattr(neardupe.config, "MANIFEST_DIR", tmp_path / "manifests")

    code = neardupe.main(["--root", str(root), "--apply-manifest", str(reviewed), "--apply"])

    assert code == 0
    assert keep.exists()
    assert not remove.exists()
    assert (root / "_TO-DELETE" / "near-dupes" / "CURATED" / "DRONE-ATMOS" / "Echospace [FLAC]" / "loop-1.flac").exists()
    undo_files = list((tmp_path / "manifests").glob("undo-near-dupes-*.tsv"))
    assert len(undo_files) == 1
    assert "_TO-DELETE/near-dupes/CURATED/DRONE-ATMOS/Echospace [FLAC]/loop-1.flac" in undo_files[0].read_text()
