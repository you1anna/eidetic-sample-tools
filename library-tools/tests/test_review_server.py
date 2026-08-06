from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from librarytools.classification.domain import AcousticEvidence, ModelVote
from librarytools.classification.ensemble import build_candidate
from librarytools.classification.review import ReviewSession
from librarytools.classification.packets import classification_digest, write_classification_audit
from librarytools.classification.review_server import (
    create_review_app,
    load_review_packet,
    validate_bind_host,
)
from librarytools.classification.domain import ClassificationError


def _candidate(root: Path):
    payload = b"0123456789"
    sample_id = hashlib.sha256(payload).hexdigest()
    path = root / "PACK" / "audio.wav"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    evidence = AcousticEvidence(
        duration_s=0.4,
        onset_density=1.0,
        crest=4.0,
        attack_ms=2.0,
        tail_ms=100.0,
        silence_ratio=0.0,
        tempo_bpm=0.0,
        beat_confidence=0.0,
        periodicity=0.0,
        onset_count=1,
        bar_fit_error=1.0,
    )
    votes = (
        ModelVote("one", "r1", {"RIM": 0.8, "TOM": 0.2}, "RIM", 0.8, 0.6),
        ModelVote("two", "r2", {"RIM": 0.7, "TOM": 0.3}, "RIM", 0.7, 0.4),
    )
    return build_candidate(sample_id, Path("PACK/audio.wav"), evidence, votes), path


def _client(tmp_path):
    root = tmp_path / "SAMPLES"
    candidate, source = _candidate(root)
    session = ReviewSession.open(tmp_path / "review-state.json", [candidate], "digest")
    app = create_review_app(
        root,
        session,
        [candidate],
        write_token="secret-token",
        on_complete=lambda queue: None,
    )
    return app.test_client(), candidate, source


def test_server_binding_is_loopback_only() -> None:
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    with pytest.raises(ClassificationError, match="loopback"):
        validate_bind_host("0.0.0.0")


def test_blind_sentinel_state_hides_predictions_and_path(tmp_path) -> None:
    client, candidate, _ = _client(tmp_path)
    response = client.get("/api/state")
    assert response.status_code == 200
    state = response.get_json()
    assert state["current"]["sample_id"] == candidate.sample_id
    assert state["current"]["kind"] == "check"
    assert "predicted_form" not in state["current"]
    assert "predicted_content" not in state["current"]
    assert "current_path" not in state["current"]
    assert "evidence" not in state["current"]


def test_audio_stream_uses_sample_id_and_supports_byte_ranges(tmp_path) -> None:
    client, candidate, source = _client(tmp_path)
    response = client.get(
        f"/audio/{candidate.sample_id}", headers={"Range": "bytes=2-5"},
    )
    assert response.status_code == 206
    assert response.data == source.read_bytes()[2:6]
    assert client.get("/audio/not-a-sample-id").status_code == 404
    assert client.get("/audio/../../etc/passwd").status_code == 404


def test_decisions_require_token_validate_taxonomy_persist_and_undo(tmp_path) -> None:
    client, candidate, _ = _client(tmp_path)
    body = {"sample_id": candidate.sample_id, "form": "ONE_SHOT", "content": "RIM"}
    assert client.post("/api/decision", json=body).status_code == 403
    assert client.post(
        "/api/decision",
        json={**body, "form": "WRONG"},
        headers={"X-Review-Token": "secret-token"},
    ).status_code == 400

    accepted = client.post(
        "/api/decision",
        json=body,
        headers={"X-Review-Token": "secret-token"},
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["complete"] is True
    state = json.loads((tmp_path / "review-state.json").read_text(encoding="utf-8"))
    assert state["decisions"][0]["sample_id"] == candidate.sample_id

    undone = client.post(
        "/api/undo", headers={"X-Review-Token": "secret-token"},
    )
    assert undone.status_code == 200
    assert undone.get_json()["complete"] is False


def test_audio_stream_refuses_bytes_changed_after_classification(tmp_path) -> None:
    client, candidate, source = _client(tmp_path)
    source.write_bytes(b"changed")
    assert client.get(f"/audio/{candidate.sample_id}").status_code == 409


def test_packet_loader_verifies_digest_and_label_membership(tmp_path) -> None:
    root = tmp_path / "SAMPLES"
    candidate, _ = _candidate(root)
    candidates = [
        replace(candidate, sample_id=f"{index:064x}", current_path=Path(f"PACK/{index}.wav"))
        for index in range(24)
    ]
    context = {"prompt_policy": "v1"}
    digest = classification_digest(candidates, context)
    packet = tmp_path / "packet"
    packet.mkdir()
    labels = packet / "labels.tsv"
    labels.write_text("sample_id\tcurrent_path\n" + "".join(
        f"{item.sample_id}\t{item.current_path.as_posix()}\n" for item in candidates
    ), encoding="utf-8")
    write_classification_audit(packet / "classification-audit.jsonl", candidates)
    strata = (
        "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
        "out-of-brief", "control",
    )
    (packet / "benchmark-labels.tsv").write_text(
        "sample_id\tcurrent_path\tstratum\tpredicted_form\tpredicted_content\t"
        "predicted_audition_group\ttrue_form\ttrue_content\ttrue_audition_group\tnotes\n"
        + "".join(
            f"{item.sample_id}\t{item.current_path}\t{strata[index // 4]}\tONE_SHOT\tRIM\t"
            "rim-one-shots\t\t\t\t\n"
            for index, item in enumerate(candidates)
        ),
        encoding="utf-8",
    )
    (packet / "packet-meta.json").write_text(json.dumps({
        "schema_version": 3,
        "root": str(root),
        "classification_digest": digest,
        "classification_context": context,
    }), encoding="utf-8")

    loaded_root, session, loaded = load_review_packet(labels)
    assert loaded_root == root.resolve()
    assert loaded == candidates
    assert session.queue.classification_digest == digest

    metadata = json.loads((packet / "packet-meta.json").read_text(encoding="utf-8"))
    metadata["classification_context"] = {"prompt_policy": "tampered"}
    (packet / "packet-meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ClassificationError, match="digest"):
        load_review_packet(labels)
