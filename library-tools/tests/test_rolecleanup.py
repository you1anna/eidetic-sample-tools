from __future__ import annotations

import csv
from pathlib import Path

import pytest

from librarytools import rolecleanup


FIELDS = [
    "path",
    "current_role",
    "authoritative",
    "top_class",
    "top_prob",
    "kick_prob",
    "suggested_role",
    "agree",
    "band",
    "note",
]


def _write_audit(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(FIELDS)
        writer.writerows(rows)


def _row(
    path: str,
    current: str,
    suggested: str,
    probability: str,
    *,
    authoritative: str = "yes",
    agree: str = "no",
    band: str = "trust",
) -> list[str]:
    return [
        path,
        current,
        authoritative,
        "snr",
        probability,
        "0.001",
        suggested,
        agree,
        band,
        "",
    ]


def test_read_trust_mismatches_filters_every_non_candidate(tmp_path: Path) -> None:
    audit = tmp_path / "audit.tsv"
    _write_audit(
        audit,
        [
            _row("CURATED/KICKS/a.wav", "KICKS", "CLAP-SNARE", "0.91"),
            _row(
                "CURATED/KICKS/b.wav",
                "KICKS",
                "CLAP-SNARE",
                "0.91",
                band="review",
            ),
            _row(
                "CURATED/KICKS/c.wav",
                "KICKS",
                "KICKS",
                "0.99",
                agree="yes",
            ),
            _row(
                "CURATED/BASS/d.wav",
                "BASS",
                "KICKS",
                "0.99",
                authoritative="",
                agree="",
                band="",
            ),
        ],
    )

    candidates = rolecleanup.read_trust_mismatches(audit)

    assert [(item.path.as_posix(), item.route) for item in candidates] == [
        ("CURATED/KICKS/a.wav", ("KICKS", "CLAP-SNARE")),
    ]
    assert len(candidates[0].candidate_id) == 12


def test_read_trust_mismatches_rejects_wrong_curated_prefix(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.tsv"
    _write_audit(audit, [_row("PACKS/a.wav", "KICKS", "PERC", "0.95")])

    with pytest.raises(ValueError, match="outside current CURATED role"):
        rolecleanup.read_trust_mismatches(audit)


def test_group_routes_uses_fixed_source_role_order(tmp_path: Path) -> None:
    audit = tmp_path / "audit.tsv"
    _write_audit(
        audit,
        [
            _row("CURATED/PERC/p.wav", "PERC", "KICKS", "0.94"),
            _row("CURATED/KICKS/k.wav", "KICKS", "PERC", "0.93"),
            _row("CURATED/HATS-CYM/h.wav", "HATS-CYM", "PERC", "0.92"),
        ],
    )

    routes = rolecleanup.group_routes(rolecleanup.read_trust_mismatches(audit))

    assert list(routes) == [
        ("KICKS", "PERC"),
        ("HATS-CYM", "PERC"),
        ("PERC", "KICKS"),
    ]


def test_select_calibration_is_stable_and_spreads_sources_and_confidence(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit.tsv"
    rows = [
        _row(
            f"CURATED/KICKS/pack-{index % 4}/item-{index:02}.wav",
            "KICKS",
            "PERC",
            f"0.{80 + index:02}",
        )
        for index in range(20)
    ]
    _write_audit(audit, rows)
    candidates = rolecleanup.read_trust_mismatches(audit)

    first = rolecleanup.select_calibration(candidates)
    second = rolecleanup.select_calibration(list(reversed(candidates)))

    assert [item.candidate_id for item in first] == [
        item.candidate_id for item in second
    ]
    assert len(first) == 10
    assert len({item.source_group for item in first}) == 4
    assert min(item.top_prob for item in first) == 0.80
    assert max(item.top_prob for item in first) >= 0.98


def test_select_calibration_returns_every_small_route(tmp_path: Path) -> None:
    audit = tmp_path / "audit.tsv"
    _write_audit(
        audit,
        [
            _row(
                "CURATED/CLAP-SNARE/a.wav",
                "CLAP-SNARE",
                "PERC",
                "0.81",
            ),
            _row(
                "CURATED/CLAP-SNARE/b.wav",
                "CLAP-SNARE",
                "PERC",
                "0.99",
            ),
        ],
    )
    candidates = rolecleanup.read_trust_mismatches(audit)

    assert rolecleanup.select_calibration(candidates) == sorted(
        candidates,
        key=lambda item: item.path.as_posix(),
    )
