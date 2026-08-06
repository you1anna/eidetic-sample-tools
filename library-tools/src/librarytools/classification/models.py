"""Lazy local audio-language model adapters and embedding utilities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Protocol

import numpy as np

from .domain import ClassificationError, ModelVote


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    revision: str
    embedding_dimensions: int = 512

    def __post_init__(self) -> None:
        if not self.model_id or not self.revision or self.embedding_dimensions <= 0:
            raise ClassificationError("model specifications require an ID, revision and dimensions")


MODEL_SPECS = (
    ModelSpec(
        "laion/clap-htsat-unfused",
        "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a",
    ),
    ModelSpec(
        "laion/larger_clap_music_and_speech",
        "195c3a3e68faebb3e2088b9a79e79b43ddbda76b",
    ),
)
MODEL_ID = MODEL_SPECS[0].model_id
MODEL_REVISION = MODEL_SPECS[0].revision

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


def prompt_policy(prompts: Mapping[str, tuple[str, ...]]) -> str:
    payload = json.dumps(prompts, sort_keys=True, separators=(",", ":"))
    return "content-prompts-v1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


PROMPT_POLICY = prompt_policy(CONTENT_PROMPTS)


class SemanticScorer(Protocol):
    @property
    def revision(self) -> str: ...

    def score(self, path: Path) -> dict[str, float]: ...


class EmbeddingRuntime(Protocol):
    def embed(self, paths: list[Path]) -> list[np.ndarray]: ...

    def embed_prompts(self, prompts: Mapping[str, tuple[str, ...]]) -> dict[str, np.ndarray]: ...


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


def batches_of(values: list, size: int):
    if size <= 0:
        raise ClassificationError("batch size must be positive")
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def rank_prompt_embeddings(
    audio_embedding: np.ndarray,
    text_embeddings: Mapping[str, np.ndarray],
) -> dict[str, float]:
    audio = np.asarray(audio_embedding, dtype=np.float64).reshape(-1)
    audio_norm = float(np.linalg.norm(audio))
    if audio_norm == 0.0:
        raise ClassificationError("audio embedding has zero magnitude")
    scores: dict[str, float] = {}
    for name, raw in text_embeddings.items():
        text = np.asarray(raw, dtype=np.float64).reshape(-1)
        norm = audio_norm * float(np.linalg.norm(text))
        scores[name] = float(np.dot(audio, text) / norm) if norm else 0.0
    return scores


class ClapScorer:
    """Pure NumPy scorer for cached audio and prompt embeddings."""

    def __init__(self, spec: ModelSpec):
        self.spec = spec

    def score(
        self,
        embedding: np.ndarray,
        prompt_embeddings: Mapping[str, np.ndarray],
    ) -> ModelVote:
        similarities = rank_prompt_embeddings(embedding, prompt_embeddings)
        labels = sorted(similarities)
        logits = np.asarray([similarities[label] for label in labels], dtype=np.float64) * 10.0
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= np.sum(probabilities)
        scores = dict(zip(labels, (float(value) for value in probabilities), strict=True))
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ModelVote(
            model_id=self.spec.model_id,
            model_revision=self.spec.revision,
            scores=scores,
            top_label=ordered[0][0],
            top_score=ordered[0][1],
            margin=ordered[0][1] - ordered[1][1],
        )


class ClapEmbeddingRuntime:
    """One pinned CPU CLAP checkpoint, intended to live only inside a worker."""

    def __init__(self, spec: ModelSpec):
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ClassificationError(
                "audio classification requires the audio-classifier extra (torch, transformers)"
            ) from exc
        self.spec = spec
        self._torch = torch
        self._processor = ClapProcessor.from_pretrained(spec.model_id, revision=spec.revision)
        self._model = (
            ClapModel.from_pretrained(spec.model_id, revision=spec.revision).eval().to("cpu")
        )
        resolved = str(getattr(self._model.config, "_commit_hash", "") or spec.revision)
        if resolved != spec.revision:
            raise ClassificationError(
                f"resolved model revision {resolved} does not match pin {spec.revision}"
            )

    def embed(self, paths: list[Path]) -> list[np.ndarray]:
        import librosa

        excerpts: list[np.ndarray] = []
        owners: list[int] = []
        for owner, path in enumerate(paths):
            duration_s = float(librosa.get_duration(path=path))
            for offset in clap_excerpt_offsets(duration_s):
                excerpts.append(
                    librosa.load(path, sr=48_000, mono=True, offset=offset, duration=10.0)[0]
                )
                owners.append(owner)
        features: list[np.ndarray] = []
        for excerpt_batch in batches_of(excerpts, 8):
            inputs = clap_audio_inputs(self._processor, excerpt_batch)
            with self._torch.inference_mode():
                features.extend(feature_array(self._model.get_audio_features(**inputs)))

        results: list[np.ndarray] = []
        for owner in range(len(paths)):
            vector = np.mean(
                [feature for index, feature in enumerate(features) if owners[index] == owner],
                axis=0,
            ).astype(np.float32).reshape(-1)
            if vector.size != self.spec.embedding_dimensions:
                raise ClassificationError(
                    f"{self.spec.model_id} returned {vector.size} dimensions; "
                    f"expected {self.spec.embedding_dimensions}"
                )
            norm = float(np.linalg.norm(vector))
            if not norm:
                raise ClassificationError(f"{self.spec.model_id} returned a zero embedding")
            results.append(vector / norm)
        return results

    def embed_prompts(
        self,
        prompts: Mapping[str, tuple[str, ...]],
    ) -> dict[str, np.ndarray]:
        labels: list[str] = []
        texts: list[str] = []
        for label, label_prompts in sorted(prompts.items()):
            for prompt in label_prompts:
                labels.append(label)
                texts.append(prompt)
        inputs = self._processor(text=texts, return_tensors="pt", padding=True)
        with self._torch.inference_mode():
            raw = feature_array(self._model.get_text_features(**inputs))
        results: dict[str, np.ndarray] = {}
        for label in sorted(prompts):
            vector = np.mean(
                [raw[index] for index, current in enumerate(labels) if current == label],
                axis=0,
            ).astype(np.float32).reshape(-1)
            if vector.size != self.spec.embedding_dimensions:
                raise ClassificationError(
                    f"{self.spec.model_id} returned {vector.size} prompt dimensions; "
                    f"expected {self.spec.embedding_dimensions}"
                )
            norm = float(np.linalg.norm(vector))
            if not norm:
                raise ClassificationError(
                    f"{self.spec.model_id} returned a zero prompt embedding for {label}"
                )
            results[label] = vector / norm
        return results


class ClapSemanticScorer:
    """CPU-local CLAP prompt scorer with lazy model loading and cached text embeddings."""

    def __init__(self, model_id: str = MODEL_ID, revision: str = MODEL_REVISION):
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ClassificationError(
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
                prompt_scores[index]
                for index, current in enumerate(self._labels)
                if current == label
            ]))
            for label in CONTENT_PROMPTS
        }
        logits = np.array(list(by_label.values()), dtype=np.float64) * 10.0
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= np.sum(probabilities)
        return dict(zip(by_label, (float(value) for value in probabilities), strict=True))
