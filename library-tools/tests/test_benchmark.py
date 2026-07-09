from __future__ import annotations

import csv
from pathlib import Path

import pytest

from librarytools import benchmark


FEATURE_FIELDS = ["path", "role", "centroid_hz", "sub_ratio"]


def _write_features(path: Path, rows: list[list[str]]) -> None:
    # Mirror the real sample-features tsv shape (only the columns we read matter);
    # pad to the real column layout so the header-index lookup is exercised.
    header = [
        "path", "source_kind", "source_name", "role", "sample_type", "bpm",
        "key", "tempo_fit", "duration", "duration_s", "peak", "rms", "crest",
        "attack_ms", "tail_ms", "head_silence_ms", "tail_silence_ms",
        "centroid_hz", "flatness", "sub_ratio", "low_ratio", "mid_ratio",
        "high_ratio", "onset_density", "zcr", "audio_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(header)
        for rel, role, centroid, sub in rows:
            row = [""] * len(header)
            row[0], row[3], row[17], row[19] = rel, role, centroid, sub
            writer.writerow(row)


def _make_files(root: Path, rels: list[str]) -> None:
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"RIFFxxxxWAVE")


# ---- feature loading -------------------------------------------------------------------------


def test_load_features_reads_centroid_and_sub_ratio(tmp_path: Path) -> None:
    features = tmp_path / "features.tsv"
    _write_features(
        features,
        [
            ["CURATED/KICKS/a.wav", "KICKS", "210.5", "0.99"],
            ["CURATED/KICKS/b.wav", "KICKS", "3800.0", "0.05"],
        ],
    )

    table = benchmark.load_features(features)

    assert table["CURATED/KICKS/a.wav"] == (210.5, 0.99)
    assert table["CURATED/KICKS/b.wav"] == (3800.0, 0.05)


def test_load_features_tolerates_blank_numeric_cells(tmp_path: Path) -> None:
    features = tmp_path / "features.tsv"
    _write_features(features, [["CURATED/KICKS/a.wav", "KICKS", "", ""]])

    table = benchmark.load_features(features)

    assert table["CURATED/KICKS/a.wav"] == (None, None)


# ---- item building ---------------------------------------------------------------------------


def test_build_items_walks_curated_role_and_joins_features(tmp_path: Path) -> None:
    root = tmp_path / "SAMPLES"
    _make_files(root, ["CURATED/KICKS/pack/a.wav", "CURATED/KICKS/b.wav"])
    features = {"CURATED/KICKS/pack/a.wav": (200.0, 0.98)}

    items = benchmark.build_items(root, "KICKS", features)

    by_path = {item.path.as_posix(): item for item in items}
    assert set(by_path) == {"CURATED/KICKS/pack/a.wav", "CURATED/KICKS/b.wav"}
    assert by_path["CURATED/KICKS/pack/a.wav"].centroid_hz == 200.0
    assert by_path["CURATED/KICKS/b.wav"].centroid_hz is None
    assert by_path["CURATED/KICKS/pack/a.wav"].folder_role == "KICKS"
    assert len(by_path["CURATED/KICKS/pack/a.wav"].sample_id) == 12


def test_build_items_skips_appledouble_and_non_audio(tmp_path: Path) -> None:
    root = tmp_path / "SAMPLES"
    _make_files(
        root,
        [
            "CURATED/KICKS/a.wav",
            "CURATED/KICKS/._a.wav",
            "CURATED/KICKS/notes.txt",
        ],
    )

    items = benchmark.build_items(root, "KICKS", {})

    assert [item.path.as_posix() for item in items] == ["CURATED/KICKS/a.wav"]


# ---- stratified selection --------------------------------------------------------------------


def _item(rel: str, centroid: float | None) -> benchmark.BenchmarkItem:
    return benchmark.BenchmarkItem(
        sample_id=benchmark.sample_id(rel),
        path=Path(rel),
        folder_role="KICKS",
        centroid_hz=centroid,
        sub_ratio=None,
    )


def test_select_benchmark_is_deterministic_and_spans_the_bright_tail() -> None:
    # 40 dark kicks + 10 bright (SP-1200-like) kicks across 5 packs.
    items = [
        _item(f"CURATED/KICKS/pack-{i % 5}/dark-{i:02}.wav", 100.0 + i)
        for i in range(40)
    ] + [
        _item(f"CURATED/KICKS/pack-{i % 5}/bright-{i:02}.wav", 3000.0 + i * 50)
        for i in range(10)
    ]

    first = benchmark.select_benchmark(items, size=25)
    second = benchmark.select_benchmark(list(reversed(items)), size=25)

    assert [i.sample_id for i in first] == [i.sample_id for i in second]
    assert len(first) == 25
    # The whole point: bright/tonal kicks must be represented, not just dark thumps.
    assert any(i.centroid_hz is not None and i.centroid_hz >= 3000.0 for i in first)
    # And it should spread across source packs.
    assert len({i.source_group for i in first}) >= 4


def test_select_benchmark_returns_all_when_fewer_than_size() -> None:
    items = [_item("CURATED/KICKS/a.wav", 100.0), _item("CURATED/KICKS/b.wav", 200.0)]

    assert benchmark.select_benchmark(items, size=25) == sorted(
        items, key=lambda i: i.path.as_posix()
    )


def test_select_benchmark_includes_feature_less_items_as_a_stratum() -> None:
    items = [_item(f"CURATED/KICKS/dark-{i:02}.wav", 100.0 + i) for i in range(30)] + [
        _item(f"CURATED/KICKS/unknown-{i:02}.wav", None) for i in range(10)
    ]

    picked = benchmark.select_benchmark(items, size=25)

    assert any(i.centroid_hz is None for i in picked)


# ---- prepare artifacts -----------------------------------------------------------------------


def test_write_prepare_artifacts_emits_packet_with_empty_true_role(tmp_path: Path) -> None:
    root = tmp_path / "SAMPLES"
    _make_files(
        root,
        [f"CURATED/KICKS/k{i:02}.wav" for i in range(30)]
        + [f"CURATED/CLAP-SNARE/s{i:02}.wav" for i in range(30)]
        + [f"CURATED/HATS-CYM/h{i:02}.wav" for i in range(30)]
        + [f"CURATED/PERC/p{i:02}.wav" for i in range(30)],
    )
    features = tmp_path / "features.tsv"
    _write_features(features, [])
    output = tmp_path / "run"

    roles = benchmark.write_prepare_artifacts(root, features, output, per_role=5)

    assert set(roles) == {"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC"}
    labels = (roles["KICKS"] / "labels.tsv").read_text(encoding="utf-8").splitlines()
    header = labels[0].split("\t")
    assert header == [
        "sample_id", "path", "folder_role", "centroid_hz", "sub_ratio",
        "true_role", "notes",
    ]
    # true_role + notes empty for the human to fill.
    assert labels[1].split("\t")[-2:] == ["", ""]
    assert len(labels) == 1 + 5
    m3u8 = (roles["KICKS"] / "audition.m3u8").read_text(encoding="utf-8").splitlines()
    assert m3u8[0] == "#EXTM3U"
    assert all(line.startswith(str(root)) for line in m3u8[1:])
    # Frozen manifest + checksum for reproducible scoring.
    assert (output / "benchmark-manifest.tsv").is_file()
    assert (output / "benchmark-manifest.sha256").read_text(encoding="utf-8").strip()


# ---- label reading ---------------------------------------------------------------------------


def _write_labels(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(
            ["sample_id", "path", "folder_role", "centroid_hz", "sub_ratio", "true_role", "notes"]
        )
        for sid, rel, folder, true_role in rows:
            writer.writerow([sid, rel, folder, "", "", true_role, ""])


def test_read_labels_requires_every_true_role_filled(tmp_path: Path) -> None:
    labels = tmp_path / "run" / "audition" / "kicks" / "labels.tsv"
    _write_labels(
        labels,
        [("id1", "CURATED/KICKS/a.wav", "KICKS", "KICKS"), ("id2", "CURATED/KICKS/b.wav", "KICKS", "")],
    )

    with pytest.raises(ValueError, match="unlabelled"):
        benchmark.read_labels(tmp_path / "run")


def test_read_labels_rejects_unknown_true_role(tmp_path: Path) -> None:
    labels = tmp_path / "run" / "audition" / "kicks" / "labels.tsv"
    _write_labels(labels, [("id1", "CURATED/KICKS/a.wav", "KICKS", "BONGO")])

    with pytest.raises(ValueError, match="invalid true_role"):
        benchmark.read_labels(tmp_path / "run")


def test_read_labels_collects_across_roles(tmp_path: Path) -> None:
    _write_labels(
        tmp_path / "run" / "audition" / "kicks" / "labels.tsv",
        [("id1", "CURATED/KICKS/a.wav", "KICKS", "KICKS")],
    )
    _write_labels(
        tmp_path / "run" / "audition" / "perc" / "labels.tsv",
        [("id2", "CURATED/PERC/b.wav", "PERC", "OTHER")],
    )

    labelled = benchmark.read_labels(tmp_path / "run")

    assert {(item.path.as_posix(), item.true_role) for item in labelled} == {
        ("CURATED/KICKS/a.wav", "KICKS"),
        ("CURATED/PERC/b.wav", "OTHER"),
    }


# ---- scoring ---------------------------------------------------------------------------------


def test_score_computes_per_role_precision_recall_and_confusion() -> None:
    pairs = [
        ("KICKS", "KICKS"),
        ("KICKS", "CLAP-SNARE"),   # the failure mode: kick called snare
        ("KICKS", "CLAP-SNARE"),
        ("CLAP-SNARE", "CLAP-SNARE"),
        ("HATS-CYM", "HATS-CYM"),
        ("PERC", "OTHER"),
    ]

    card = benchmark.score(pairs)

    assert card.overall_accuracy == pytest.approx(3 / 6)
    kicks = card.per_role["KICKS"]
    assert kicks.recall == pytest.approx(1 / 3)   # 1 of 3 true kicks recovered
    assert kicks.precision == pytest.approx(1.0)  # the one KICKS prediction was right
    # Dominant confusion cell: true KICKS predicted CLAP-SNARE, twice.
    assert card.confusion[("KICKS", "CLAP-SNARE")] == 2


def test_score_handles_role_with_no_predictions_or_truths() -> None:
    card = benchmark.score([("KICKS", "KICKS")])

    # A role never seen as truth or prediction has zero-division guarded to 0.0.
    assert card.per_role["PERC"].precision == 0.0
    assert card.per_role["PERC"].recall == 0.0
    assert card.per_role["PERC"].f1 == 0.0


def test_format_scorecard_renders_markdown_table() -> None:
    card = benchmark.score([("KICKS", "CLAP-SNARE"), ("KICKS", "KICKS")])

    text = benchmark.format_scorecard(card, model="cnn-lstm")

    assert "cnn-lstm" in text
    assert "KICKS" in text
    assert "Confusion" in text


# ---- CLI -------------------------------------------------------------------------------------


def test_prepare_cli_writes_packets_and_reports_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from librarytools import benchmark_cli

    root = tmp_path / "SAMPLES"
    _make_files(
        root,
        [f"CURATED/KICKS/k{i:02}.wav" for i in range(30)]
        + [f"CURATED/CLAP-SNARE/s{i:02}.wav" for i in range(30)]
        + [f"CURATED/HATS-CYM/h{i:02}.wav" for i in range(30)]
        + [f"CURATED/PERC/p{i:02}.wav" for i in range(30)],
    )
    output = tmp_path / "run"

    result = benchmark_cli.main(
        [
            "prepare",
            "--root", str(root),
            "--features", str(tmp_path / "missing.tsv"),  # tolerated: no features
            "--output-dir", str(output),
            "--per-role", "5",
        ]
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "total: 20" in out
    assert (output / "benchmark-manifest.sha256").is_file()


def test_score_cli_errors_when_labels_incomplete(tmp_path: Path) -> None:
    from librarytools import benchmark_cli

    _write_labels(
        tmp_path / "run" / "audition" / "kicks" / "labels.tsv",
        [("id1", "CURATED/KICKS/a.wav", "KICKS", "")],
    )

    result = benchmark_cli.main(["score", "--output-dir", str(tmp_path / "run")])

    assert result == 3
