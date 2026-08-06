from pathlib import Path

from librarytools.classification.domain import Classification
from librarytools.classification.packets import read_classifications, write_classifications


def test_classification_snapshot_round_trips_through_the_public_schema(tmp_path):
    snapshot = tmp_path / "classification.tsv"
    expected = Classification(
        sample_id="a" * 64,
        current_path=Path("PACKS/pack/rim.wav"),
        form="ONE_SHOT",
        content="RIM",
        audition_group="rim-one-shots",
        form_confidence=0.91,
        content_confidence=0.82,
        evidence="duration_s=0.2",
        classifier_version="hybrid-v1",
    )

    write_classifications(snapshot, [expected])

    assert read_classifications(snapshot) == [expected]
