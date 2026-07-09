"""CLI for the human-labelled drum-role benchmark.

    sample-benchmark prepare --root <SAMPLES> --features <features.tsv> --output-dir <dir>
    sample-benchmark score   --output-dir <dir> [--model cnn-lstm]

`prepare` writes a read-only audition packet (empty true_role) for Robin to fill by ear. `score`
grades a model's predictions on the labelled set and writes a per-role precision/recall + confusion
scorecard. Nothing here moves or edits a sample.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import benchmark, config

_DEFAULT_FEATURES = (
    config.MANIFEST_DIR / "sample-intelligence-pilot" / "sample-features-latest.tsv"
)


def _cmd_prepare(args: argparse.Namespace) -> int:
    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2
    try:
        role_dirs = benchmark.write_prepare_artifacts(
            args.root, args.features, args.output_dir, per_role=args.per_role
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    total = 0
    print(f"[MANIFEST-ONLY] drum-role benchmark packet -> {args.output_dir}")
    for role in benchmark.ROLE_ORDER:
        labels = role_dirs[role] / "labels.tsv"
        count = max(0, sum(1 for _ in labels.open(encoding="utf-8")) - 1)
        total += count
        print(f"  {role}: {count} to audition ({role_dirs[role]})")
    print(f"  total: {total} — fill true_role in each labels.tsv by ear, then run: score")
    return 0


def _predict_cnn_lstm(paths: list[Path], root: Path) -> dict[str, str]:
    """Map absolute audio path -> predicted score-role using the current CNN-LSTM."""
    from .classifier import DrumRoleClassifier

    clf = DrumRoleClassifier()
    votes = clf.vote_batch([root / p for p in paths])
    predictions: dict[str, str] = {}
    for rel in paths:
        vote = votes.get(root / rel)
        role = vote.suggested_role if vote else "OTHER"
        # Collapse anything outside the four target roles (BASS, REVIEW, ...) to OTHER.
        predictions[rel.as_posix()] = role if role in benchmark.ROLE_ORDER else "OTHER"
    return predictions


def _cmd_score(args: argparse.Namespace) -> int:
    try:
        labelled = benchmark.read_labels(args.output_dir)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if not labelled:
        print("no labelled samples found", file=sys.stderr)
        return 3

    if args.model == "cnn-lstm":
        from .classifier import available

        if not available():
            print(
                "classifier unavailable: install the [classifier] extra and provide weights "
                f"({config.DRUM_MODEL_PATH})",
                file=sys.stderr,
            )
            return 4
        predictions = _predict_cnn_lstm([item.path for item in labelled], args.root)
    else:
        print(f"unknown model: {args.model}", file=sys.stderr)
        return 2

    pairs = [
        (item.true_role, predictions.get(item.path.as_posix(), "OTHER"))
        for item in labelled
    ]
    card = benchmark.score(pairs)
    report = benchmark.format_scorecard(card, model=args.model)

    md_path = args.output_dir / f"scorecard-{args.model}.md"
    md_path.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nwritten: {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="write a read-only benchmark audition packet")
    prepare.add_argument("--root", type=Path, default=config.SAMPLES_ROOT)
    prepare.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--per-role", type=int, default=25)

    scorer = subparsers.add_parser("score", help="grade a model against the ear labels")
    scorer.add_argument("--output-dir", type=Path, required=True)
    scorer.add_argument("--root", type=Path, default=config.SAMPLES_ROOT)
    scorer.add_argument("--model", default="cnn-lstm", choices=["cnn-lstm"])

    args = parser.parse_args(argv)
    if args.command == "prepare":
        return _cmd_prepare(args)
    if args.command == "score":
        return _cmd_score(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
