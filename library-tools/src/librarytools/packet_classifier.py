"""Local audio-derived classification for audition packets.

The classifier deliberately separates form (one-shot/loop/phrase/long-form) from
content (rim/tom/percussion/full drums/vocal/out-of-brief).  Path text is tokenised
and contributes only a small tie-breaking bonus; acoustic and CLAP evidence remain
the primary signals.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping, Protocol, Sequence

import numpy as np

from . import audiofeatures
from .featurecache import FEATURE_COLUMNS
from .inventory import sha256_file


CLASSIFIER_VERSION = "hybrid-v1"
MODEL_ID = "laion/clap-htsat-unfused"
MODEL_REVISION = "main"
FORMS = frozenset({"ONE_SHOT", "LOOP", "PHRASE", "LONG_FORM"})
CONTENTS = frozenset({"RIM", "TOM", "PERCUSSION", "FULL_DRUMS", "VOCAL", "OUT_OF_BRIEF"})
AUDITION_GROUPS = (
    "rim-one-shots",
    "tom-one-shots",
    "percussion-one-shots",
    "percussion-loops",
    "full-drum-loops",
    "vocal-stabs",
    "vocal-phrases",
    "long-vocal-sources",
    "out-of-brief",
)
CLASSIFICATION_FIELDS = (
    "sample_id", "current_path", "form", "content", "audition_group",
    "form_confidence", "content_confidence", "evidence", "classifier_version",
)
BENCHMARK_FIELDS = (
    "sample_id", "current_path", "stratum", "predicted_form", "predicted_content",
    "predicted_audition_group", "true_form", "true_content",
    "true_audition_group", "notes",
)
BENCHMARK_STRATA = (
    "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
    "out-of-brief", "control",
)

CONTENT_PROMPTS: dict[str, tuple[str, ...]] = {
    "RIM": (
        "an isolated rimshot drum hit",
        "a short single rim click percussion sample",
    ),
    "TOM": (
        "an isolated tom drum hit",
        "a short single pitched tom sample",
    ),
    "PERCUSSION": (
        "isolated hand percussion, conga, bongo, shaker or metallic percussion",
        "a percussion-only rhythmic loop without a full kick and snare drum kit",
    ),
    "FULL_DRUMS": (
        "a full drum kit loop with kick, snare and hi hats",
        "a complete electronic drum beat loop",
    ),
    "VOCAL": (
        "a human vocal word, rap phrase, shout or acapella recording",
        "a voice-only music sample",
    ),
    "OUT_OF_BRIEF": (
        "an acid bass or synthesizer line, melody or chord loop",
        "a waterfall, nature ambience, field recording or unrelated sound effect",
    ),
}

_TOKEN_CONTENT: dict[str, frozenset[str]] = {
    "RIM": frozenset({"rim", "rimshot"}),
    "TOM": frozenset({"tom", "toms"}),
    "PERCUSSION": frozenset({
        "perc", "percussion", "conga", "congas", "bongo", "bongos", "shaker",
        "clave", "cowbell", "djembe", "tribal",
    }),
    "FULL_DRUMS": frozenset({"drum", "drums", "beat", "beats", "groove"}),
    "VOCAL": frozenset({"vocal", "vocals", "vox", "voice", "acapella", "rap"}),
    "OUT_OF_BRIEF": frozenset({
        "acid", "synth", "bassline", "waterfall", "nature", "field", "atmosphere",
        "ambient", "melody", "chord",
    }),
}


class PacketClassifierError(ValueError):
    pass


@dataclass(frozen=True)
class AcousticEvidence:
    duration_s: float
    onset_density: float
    crest: float
    attack_ms: float
    tail_ms: float
    silence_ratio: float
    tempo_bpm: float
    beat_confidence: float
    periodicity: float


@dataclass(frozen=True)
class Classification:
    sample_id: str
    current_path: Path
    form: str
    content: str
    audition_group: str
    form_confidence: float
    content_confidence: float
    evidence: str
    classifier_version: str = CLASSIFIER_VERSION


@dataclass(frozen=True)
class ClassifierConfig:
    lexical_weight: float
    periodicity_threshold: float
    beat_threshold: float


@dataclass(frozen=True)
class RawCandidate:
    sample_id: str
    current_path: Path
    evidence: AcousticEvidence
    semantic_scores: Mapping[str, float]


DEFAULT_CONFIG = ClassifierConfig(
    lexical_weight=0.08,
    periodicity_threshold=0.32,
    beat_threshold=0.20,
)
CALIBRATION_CONFIGS = tuple(
    ClassifierConfig(lexical_weight, periodicity, beat)
    for lexical_weight in (0.00, 0.02, 0.04, 0.08)
    for periodicity in (0.25, 0.32, 0.40)
    for beat in (0.10, 0.20, 0.30)
)


@dataclass(frozen=True)
class BenchmarkScore:
    form_correct: int
    content_correct: int
    group_correct: int
    content_group_correct: int
    total: int
    ready: bool
    passed: bool


def calibrate_config(
    items: Sequence[RawCandidate],
    truth: Mapping[str, Mapping[str, str]],
    configs: Sequence[ClassifierConfig] = CALIBRATION_CONFIGS,
) -> ClassifierConfig:
    if not configs:
        raise PacketClassifierError("calibration requires at least one candidate configuration")
    ranked: list[tuple[tuple[float, ...], ClassifierConfig]] = []
    for config in configs:
        form_correct = content_correct = group_correct = content_group_correct = 0
        margins: list[float] = []
        for item in items:
            expected = truth.get(item.sample_id)
            if not expected:
                continue
            predicted = classify_evidence(
                item.current_path, item.evidence, item.semantic_scores, config=config,
            )
            form_correct += predicted.form == expected.get("true_form")
            content_correct += predicted.content == expected.get("true_content")
            group_correct += predicted.audition_group == expected.get("true_audition_group")
            content_group_correct += (
                predicted.content == expected.get("true_content")
                and predicted.audition_group == expected.get("true_audition_group")
            )
            margins.append(min(predicted.form_confidence, predicted.content_confidence))
        mean_margin = sum(margins) / len(margins) if margins else 0.0
        objective = (
            float(form_correct), float(content_group_correct), float(content_correct), mean_margin,
            -config.lexical_weight,
        )
        ranked.append((objective, config))
    return max(ranked, key=lambda item: item[0])[1]


class SemanticScorer(Protocol):
    @property
    def revision(self) -> str: ...

    def score(self, path: Path) -> dict[str, float]: ...


def verify_packet_source(root: Path, database, sample_id: str, path: Path) -> Path:
    root = root.resolve()
    source = (root / path).resolve()
    if not source.is_relative_to(root):
        raise PacketClassifierError(f"sample path escapes root: {path}")
    try:
        location = database.location(path)
    except KeyError as exc:
        raise PacketClassifierError(f"sample is absent from inventory: {path}") from exc
    if not location.exists or location.sample_id != sample_id:
        raise PacketClassifierError(f"stale sample identity for: {path}")
    if not source.is_file():
        raise PacketClassifierError(f"sample is missing: {path}")
    if sha256_file(source) != sample_id:
        raise PacketClassifierError(f"hash changed since inventory scan: {path}")
    return source


def feature_array(output):
    """Normalise Transformers 4 tensor and Transformers 5 pooled outputs."""
    value = getattr(output, "pooler_output", output)
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def clap_audio_inputs(processor, excerpts):
    return processor(
        audio=excerpts,
        sampling_rate=48_000,
        return_tensors="pt",
        padding=True,
    )


def clap_excerpt_offsets(duration_s: float, window_s: float = 10.0) -> list[float]:
    """Return bounded start offsets without decoding an entire long source."""
    if duration_s <= window_s:
        return [0.0]
    remainder = duration_s - window_s
    return [0.0, remainder / 2.0, remainder]


def rhythm_periodicity(onset, sample_rate: int) -> float:
    if len(onset) < 4:
        return 0.0
    import librosa

    autocorrelation = librosa.autocorrelate(onset, max_size=len(onset))
    if len(autocorrelation) <= 1 or autocorrelation[0] <= 0:
        return 0.0
    min_lag = max(1, int(round(60.0 * sample_rate / (240.0 * 512))))
    max_lag = min(
        len(autocorrelation),
        int(round(60.0 * sample_rate / (50.0 * 512))) + 1,
    )
    if max_lag <= min_lag:
        return 0.0
    return float(np.max(autocorrelation[min_lag:max_lag]) / autocorrelation[0])


def tokenise_path(path: Path) -> frozenset[str]:
    """Return whole lowercase tokens; substrings such as bottom/tom never match."""
    return frozenset(re.findall(r"[a-z]+|[0-9]+", path.as_posix().lower()))


def _normalise_scores(scores: Mapping[str, float]) -> dict[str, float]:
    values = {name: max(0.0, float(scores.get(name, 0.0))) for name in CONTENTS}
    total = sum(values.values())
    if total <= 0.0:
        return {name: 1.0 / len(CONTENTS) for name in CONTENTS}
    return {name: value / total for name, value in values.items()}


def _content(
    path: Path,
    semantic_scores: Mapping[str, float],
    config: ClassifierConfig,
) -> tuple[str, float, dict[str, float]]:
    scores = _normalise_scores(semantic_scores)
    tokens = tokenise_path(path)
    # Text is deliberately capped at an eight-point bonus and cannot rescue a weak
    # semantic class by itself.
    adjusted = {
        name: score + (config.lexical_weight if tokens & _TOKEN_CONTENT[name] else 0.0)
        for name, score in scores.items()
    }
    ordered = sorted(adjusted.items(), key=lambda item: (-item[1], item[0]))
    content = ordered[0][0]
    margin = max(0.0, ordered[0][1] - ordered[1][1])
    confidence = min(1.0, max(scores[content], 0.5 + margin / 2.0))
    return content, confidence, adjusted


def _form(
    path: Path,
    evidence: AcousticEvidence,
    config: ClassifierConfig,
) -> tuple[str, float]:
    duration = evidence.duration_s
    filename_tokens = tokenise_path(Path(path.name))
    loop_hint = "loop" in filename_tokens or "loops" in filename_tokens
    rhythmic = (
        evidence.periodicity >= config.periodicity_threshold
        and evidence.beat_confidence >= config.beat_threshold
    )

    if duration >= 90.0:
        return "LONG_FORM", min(1.0, 0.90 + min(duration - 90.0, 100.0) / 1000.0)
    if duration <= 2.0:
        return "ONE_SHOT", min(1.0, 0.76 + (2.0 - duration) * 0.10)
    if rhythmic or (loop_hint and evidence.onset_density >= 1.0):
        strength = max(evidence.periodicity, evidence.beat_confidence)
        return "LOOP", min(0.98, 0.62 + strength * 0.35)
    return "PHRASE", min(0.85, 0.55 + min(duration, 30.0) / 150.0)


def _audition_group(form: str, content: str) -> str:
    if content == "OUT_OF_BRIEF":
        return "out-of-brief"
    if content == "VOCAL":
        if form == "LONG_FORM":
            return "long-vocal-sources"
        return "vocal-stabs" if form == "ONE_SHOT" else "vocal-phrases"
    if form in {"LOOP", "PHRASE", "LONG_FORM"}:
        return "full-drum-loops" if content == "FULL_DRUMS" else "percussion-loops"
    if content == "RIM":
        return "rim-one-shots"
    if content == "TOM":
        return "tom-one-shots"
    return "percussion-one-shots"


def classify_evidence(
    path: Path,
    evidence: AcousticEvidence,
    semantic_scores: Mapping[str, float],
    *,
    config: ClassifierConfig = DEFAULT_CONFIG,
) -> Classification:
    content, content_confidence, adjusted = _content(path, semantic_scores, config)
    form, form_confidence = _form(path, evidence, config)
    group = _audition_group(form, content)
    top_scores = sorted(adjusted.items(), key=lambda item: (-item[1], item[0]))[:2]
    detail = (
        f"duration_s={evidence.duration_s:.3f};onset_density={evidence.onset_density:.3f};"
        f"tempo_bpm={evidence.tempo_bpm:.2f};beat_confidence={evidence.beat_confidence:.3f};"
        f"periodicity={evidence.periodicity:.3f};semantic="
        + ",".join(f"{name}:{score:.3f}" for name, score in top_scores)
    )
    return Classification(
        sample_id="",
        current_path=path,
        form=form,
        content=content,
        audition_group=group,
        form_confidence=form_confidence,
        content_confidence=content_confidence,
        evidence=detail,
    )


def rank_prompt_embeddings(
    audio_embedding: np.ndarray,
    text_embeddings: Mapping[str, np.ndarray],
) -> dict[str, float]:
    audio = np.asarray(audio_embedding, dtype=np.float64).reshape(-1)
    audio_norm = float(np.linalg.norm(audio))
    if audio_norm == 0.0:
        raise PacketClassifierError("audio embedding has zero magnitude")
    scores: dict[str, float] = {}
    for name, raw in text_embeddings.items():
        text = np.asarray(raw, dtype=np.float64).reshape(-1)
        norm = audio_norm * float(np.linalg.norm(text))
        scores[name] = float(np.dot(audio, text) / norm) if norm else 0.0
    return scores


def measure_acoustic(path: Path, payload: Mapping[str, float | None]) -> AcousticEvidence:
    """Combine the identity-keyed cache with librosa rhythm measurements."""
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise PacketClassifierError(
            "audio classification requires the audio-classifier extra (librosa)"
        ) from exc

    audio, sample_rate = librosa.load(path, sr=22_050, mono=True, duration=120.0)
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    if len(onset) >= 4 and float(np.max(onset)) > 0.0:
        tempo_raw, beats = librosa.beat.beat_track(
            onset_envelope=onset, sr=sample_rate, units="frames",
        )
        tempo = float(np.asarray(tempo_raw).reshape(-1)[0])
        periodicity = rhythm_periodicity(onset, sample_rate)
        beat_confidence = min(1.0, max(0.0, periodicity) * min(1.0, len(beats) / 8.0))
    else:
        tempo = periodicity = beat_confidence = 0.0

    duration = float(payload.get("duration_s") or (len(audio) / sample_rate if sample_rate else 0.0))
    head = float(payload.get("head_silence_ms") or 0.0)
    tail_silence = float(payload.get("tail_silence_ms") or 0.0)
    silence_ratio = min(1.0, (head + tail_silence) / max(duration * 1000.0, 1.0))
    return AcousticEvidence(
        duration_s=duration,
        onset_density=float(payload.get("onset_density") or 0.0),
        crest=float(payload.get("crest") or 0.0),
        attack_ms=float(payload.get("attack_ms") or 0.0),
        tail_ms=float(payload.get("tail_ms") or 0.0),
        silence_ratio=silence_ratio,
        tempo_bpm=tempo,
        beat_confidence=beat_confidence,
        periodicity=max(0.0, min(1.0, periodicity)),
    )


class ClapSemanticScorer:
    """CPU-local CLAP prompt scorer with lazy model loading and cached text embeddings."""

    def __init__(self, model_id: str = MODEL_ID, revision: str = MODEL_REVISION):
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise PacketClassifierError(
                "audio classification requires the audio-classifier extra (torch, transformers)"
            ) from exc
        self._torch = torch
        self._processor = ClapProcessor.from_pretrained(model_id, revision=revision)
        self._model = ClapModel.from_pretrained(model_id, revision=revision).eval().to("cpu")
        resolved = getattr(self._model.config, "_commit_hash", None)
        self._revision = str(resolved or revision)
        self._labels: list[str] = []
        prompts: list[str] = []
        for label, texts in CONTENT_PROMPTS.items():
            for prompt in texts:
                self._labels.append(label)
                prompts.append(prompt)
        text_inputs = self._processor(text=prompts, return_tensors="pt", padding=True)
        with torch.inference_mode():
            self._text_embeddings = feature_array(self._model.get_text_features(**text_inputs))

    @property
    def revision(self) -> str:
        return self._revision

    def score(self, path: Path) -> dict[str, float]:
        import librosa

        duration_s = float(librosa.get_duration(path=path))
        excerpts = [
            librosa.load(
                path,
                sr=48_000,
                mono=True,
                offset=offset,
                duration=10.0,
            )[0]
            for offset in clap_excerpt_offsets(duration_s)
        ]
        inputs = clap_audio_inputs(self._processor, excerpts)
        with self._torch.inference_mode():
            embeddings = feature_array(self._model.get_audio_features(**inputs))
        prompt_scores = np.mean([
            np.array(list(rank_prompt_embeddings(embedding, {
                str(index): text for index, text in enumerate(self._text_embeddings)
            }).values()))
            for embedding in embeddings
        ], axis=0)
        by_label = {
            label: float(np.mean([
                prompt_scores[index] for index, current in enumerate(self._labels) if current == label
            ]))
            for label in CONTENT_PROMPTS
        }
        logits = np.array(list(by_label.values()), dtype=np.float64) * 10.0
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= np.sum(probabilities)
        return dict(zip(by_label, (float(value) for value in probabilities), strict=True))


def score_benchmark(rows: Sequence[Mapping[str, str]]) -> BenchmarkScore:
    ready_rows = [
        row for row in rows
        if row.get("true_form") and row.get("true_content") and row.get("true_audition_group")
    ]
    expected_strata = Counter({stratum: 4 for stratum in BENCHMARK_STRATA})
    structurally_valid = (
        len(rows) == 24
        and len({row.get("sample_id", "") for row in rows}) == 24
        and all(row.get("sample_id") and row.get("current_path") for row in rows)
        and Counter(row.get("stratum", "") for row in rows) == expected_strata
    )
    truths_valid = all(
        row.get("true_form") in FORMS
        and row.get("true_content") in CONTENTS
        and row.get("true_audition_group") in AUDITION_GROUPS
        for row in ready_rows
    )
    ready = structurally_valid and len(ready_rows) == 24 and truths_valid
    form_correct = sum(row.get("form") == row.get("true_form") for row in ready_rows)
    content_correct = sum(row.get("content") == row.get("true_content") for row in ready_rows)
    group_correct = sum(
        row.get("audition_group") == row.get("true_audition_group") for row in ready_rows
    )
    content_group_correct = sum(
        row.get("content") == row.get("true_content")
        and row.get("audition_group") == row.get("true_audition_group")
        for row in ready_rows
    )
    return BenchmarkScore(
        form_correct=form_correct,
        content_correct=content_correct,
        group_correct=group_correct,
        content_group_correct=content_group_correct,
        total=len(ready_rows),
        ready=ready,
        passed=ready and form_correct >= 22 and content_group_correct >= 20,
    )


def select_benchmark_rows(rows: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    selected: list[Mapping[str, str]] = []
    used: set[str] = set()
    for stratum in BENCHMARK_STRATA:
        candidates = sorted(
            (row for row in rows if row.get("stratum") == stratum),
            key=lambda row: str(row.get("sample_id", "")),
        )
        for row in candidates:
            sample_id = str(row.get("sample_id", ""))
            if sample_id not in used:
                selected.append(row)
                used.add(sample_id)
            if sum(item.get("stratum") == stratum for item in selected) == 4:
                break
    if len(selected) != 24:
        raise PacketClassifierError("benchmark requires four unique candidates in each of six strata")
    return selected


def benchmark_strata(rows: Sequence[Classification]) -> dict[str, str]:
    """Assign four unique candidates to each benchmark stratum deterministically."""
    remaining = {row.sample_id: row for row in rows}
    assigned: dict[str, str] = {}

    def take(stratum: str, key) -> None:
        candidates = sorted(remaining.values(), key=key)
        for row in candidates[:4]:
            assigned[row.sample_id] = stratum
            remaining.pop(row.sample_id)

    take("out-of-brief", lambda row: (row.content != "OUT_OF_BRIEF", -row.content_confidence, row.sample_id))
    take("vocal-form", lambda row: (row.content != "VOCAL", row.form_confidence, row.sample_id))
    take("loop-content", lambda row: (row.form != "LOOP", row.content not in {"PERCUSSION", "FULL_DRUMS"}, row.content_confidence, row.sample_id))
    take("drum-one-shot", lambda row: (row.form != "ONE_SHOT", row.content not in {"RIM", "TOM", "PERCUSSION"}, row.content_confidence, row.sample_id))
    take("form-boundary", lambda row: (row.form_confidence, row.content_confidence, row.sample_id))
    take("control", lambda row: (-min(row.form_confidence, row.content_confidence), row.sample_id))
    if len(assigned) != 24:
        raise PacketClassifierError("benchmark requires at least 24 classified samples")
    return assigned


def write_classifications(path: Path, rows: Sequence[Classification]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CLASSIFICATION_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            data = asdict(row)
            data["current_path"] = row.current_path.as_posix()
            data["form_confidence"] = f"{row.form_confidence:.6f}"
            data["content_confidence"] = f"{row.content_confidence:.6f}"
            writer.writerow(data)


def read_classifications(path: Path) -> list[Classification]:
    if not path.is_file():
        raise PacketClassifierError(f"classification.tsv is missing beside {path.parent / 'labels.tsv'}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != CLASSIFICATION_FIELDS:
            raise PacketClassifierError("classification.tsv has an unexpected schema")
        rows = []
        seen: set[str] = set()
        for index, raw in enumerate(reader, start=2):
            sample_id = raw["sample_id"]
            if sample_id in seen:
                raise PacketClassifierError(f"classification.tsv row {index}: duplicate sample_id")
            if raw["form"] not in FORMS or raw["content"] not in CONTENTS:
                raise PacketClassifierError(f"classification.tsv row {index}: invalid form/content")
            if raw["audition_group"] not in AUDITION_GROUPS:
                raise PacketClassifierError(f"classification.tsv row {index}: invalid audition_group")
            seen.add(sample_id)
            rows.append(Classification(
                sample_id=sample_id,
                current_path=Path(raw["current_path"]),
                form=raw["form"],
                content=raw["content"],
                audition_group=raw["audition_group"],
                form_confidence=float(raw["form_confidence"]),
                content_confidence=float(raw["content_confidence"]),
                evidence=raw["evidence"],
                classifier_version=raw["classifier_version"],
            ))
    return rows


def write_benchmark_sheet(
    path: Path,
    rows: Sequence[Classification],
    strata: Mapping[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            if row.sample_id not in strata:
                continue
            writer.writerow({
                "sample_id": row.sample_id,
                "current_path": row.current_path.as_posix(),
                "stratum": strata[row.sample_id],
                "predicted_form": row.form,
                "predicted_content": row.content,
                "predicted_audition_group": row.audition_group,
                "true_form": "",
                "true_content": "",
                "true_audition_group": "",
                "notes": "",
            })


def refresh_benchmark_predictions(
    path: Path,
    classifications: Mapping[str, Classification],
) -> list[dict[str, str]]:
    """Refresh machine columns while preserving all human-entered benchmark fields."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise PacketClassifierError("benchmark-labels.tsv has an unexpected schema")
        raw_rows = list(reader)

    saved_rows: list[dict[str, str]] = []
    merged: list[dict[str, str]] = []
    for raw in raw_rows:
        predicted = classifications.get(raw["sample_id"])
        if predicted is None:
            raise PacketClassifierError(f"benchmark sample is not classified: {raw['sample_id']}")
        if Path(raw["current_path"]) != predicted.current_path:
            raise PacketClassifierError(f"benchmark sample path is stale: {raw['sample_id']}")
        refreshed = {
            **raw,
            "predicted_form": predicted.form,
            "predicted_content": predicted.content,
            "predicted_audition_group": predicted.audition_group,
        }
        saved_rows.append(refreshed)
        merged.append({
            **refreshed,
            "form": predicted.form,
            "content": predicted.content,
            "audition_group": predicted.audition_group,
        })

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(saved_rows)
    temporary.replace(path)
    return merged


def read_benchmark_with_predictions(
    path: Path,
    classifications: Mapping[str, Classification],
) -> list[dict[str, str]]:
    """Read benchmark truth and merge current predictions without changing the sheet."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise PacketClassifierError("benchmark-labels.tsv has an unexpected schema")
        merged: list[dict[str, str]] = []
        for raw in reader:
            predicted = classifications.get(raw["sample_id"])
            if predicted is None:
                raise PacketClassifierError(f"benchmark sample is not classified: {raw['sample_id']}")
            merged.append({
                **raw,
                "form": predicted.form,
                "content": predicted.content,
                "audition_group": predicted.audition_group,
            })
    return merged


def _read_benchmark_truth(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise PacketClassifierError("benchmark-labels.tsv has an unexpected schema")
        return {
            row["sample_id"]: {
                "true_form": row["true_form"],
                "true_content": row["true_content"],
                "true_audition_group": row["true_audition_group"],
            }
            for row in reader
            if row["true_form"] and row["true_content"] and row["true_audition_group"]
        }


def _write_benchmark_audition(root: Path, benchmark_path: Path) -> None:
    with benchmark_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    playlist_path = benchmark_path.parent / "benchmark.m3u8"
    lines = ["#EXTM3U", *(str((root / row["current_path"]).resolve()) for row in rows)]
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    playlists_dir = benchmark_path.parent / "benchmark-playlists"
    if playlists_dir.exists():
        shutil.rmtree(playlists_dir)
    playlists_dir.mkdir()
    index_lines = [
        "# Classifier benchmark playlists",
        "",
        "Each playlist contains four samples. Enter the heard truth in `../benchmark-labels.tsv`.",
        "",
        "| Stratum | Files | Playlist |",
        "|---|---:|---|",
    ]
    for stratum in BENCHMARK_STRATA:
        stratum_rows = [row for row in rows if row["stratum"] == stratum]
        stratum_lines = [
            "#EXTM3U",
            *(str((root / row["current_path"]).resolve()) for row in stratum_rows),
        ]
        filename = f"{stratum}.m3u8"
        (playlists_dir / filename).write_text(
            "\n".join(stratum_lines) + "\n", encoding="utf-8",
        )
        index_lines.append(
            f"| `{stratum}` | {len(stratum_rows)} | [{filename}]({filename}) |"
        )
    (playlists_dir / "README.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8",
    )
    readme = benchmark_path.parent / "benchmark-README.md"
    readme.write_text(
        "# Classifier ear benchmark\n\n"
        "Listen to `benchmark.m3u8`, then fill `true_form`, `true_content`, "
        "`true_audition_group` and optional `notes` in `benchmark-labels.tsv`.\n\n"
        "Allowed form values: `ONE_SHOT`, `LOOP`, `PHRASE`, `LONG_FORM`.\n\n"
        "Allowed content values: `RIM`, `TOM`, `PERCUSSION`, `FULL_DRUMS`, `VOCAL`, "
        "`OUT_OF_BRIEF`.\n",
        encoding="utf-8",
    )


def classify_packet(
    root: Path,
    database,
    labels_path: Path,
    benchmark_path: Path,
    scorer: SemanticScorer | None = None,
) -> tuple[list[Classification], BenchmarkScore]:
    """Classify a packet and create/score its 24-row ear benchmark."""
    scorer = scorer or ClapSemanticScorer()
    with labels_path.open(encoding="utf-8", newline="") as fh:
        label_reader = csv.DictReader(fh, delimiter="\t")
        label_rows = list(label_reader)
    cached = database.features()
    raw_candidates: list[RawCandidate] = []
    for raw in label_rows:
        rel = Path(raw["current_path"])
        source = verify_packet_source(root, database, raw["sample_id"], rel)
        payload = json.loads(cached.get(raw["sample_id"], "{}"))
        if not payload:
            record = audiofeatures.extract(source, cache_path=rel)
            if record.error:
                raise PacketClassifierError(f"cannot analyse {rel}: {record.error}")
            payload = {column: getattr(record, column) for column in FEATURE_COLUMNS}
        evidence = measure_acoustic(source, payload)
        raw_candidates.append(RawCandidate(
            sample_id=raw["sample_id"],
            current_path=rel,
            evidence=evidence,
            semantic_scores=scorer.score(source),
        ))

    truth = _read_benchmark_truth(benchmark_path)
    config = (
        calibrate_config(raw_candidates, truth)
        if len(truth) == 24
        else DEFAULT_CONFIG
    )
    classifications = []
    for item in raw_candidates:
        predicted = classify_evidence(
            item.current_path, item.evidence, item.semantic_scores, config=config,
        )
        classifications.append(replace(
            predicted,
            sample_id=item.sample_id,
            current_path=item.current_path,
        ))

    classification_path = labels_path.parent / "classification.tsv"
    write_classifications(classification_path, classifications)
    by_id = {row.sample_id: row for row in classifications}
    if benchmark_path.is_file():
        benchmark_rows = refresh_benchmark_predictions(benchmark_path, by_id)
    else:
        strata = benchmark_strata(classifications)
        write_benchmark_sheet(benchmark_path, classifications, strata)
        benchmark_rows = read_benchmark_with_predictions(benchmark_path, by_id)
    _write_benchmark_audition(root, benchmark_path)
    score = score_benchmark(benchmark_rows)

    meta_path = labels_path.parent / "packet-meta.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    metadata.update({
        "schema_version": 2,
        "classifier": {
            "version": CLASSIFIER_VERSION,
            "model_id": MODEL_ID,
            "model_revision": scorer.revision,
            "config": asdict(config),
        },
        "benchmark": {
            "path": benchmark_path.name,
            "ready": score.ready,
            "passed": score.passed,
            "form_correct": score.form_correct,
            "content_correct": score.content_correct,
            "group_correct": score.group_correct,
            "content_group_correct": score.content_group_correct,
            "total": score.total,
        },
    })
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return classifications, score
