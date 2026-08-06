"""Lazy local audio-language model adapters and embedding utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol

import numpy as np

from .domain import ClassificationError


MODEL_ID = "laion/clap-htsat-unfused"
MODEL_REVISION = "main"

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


class SemanticScorer(Protocol):
    @property
    def revision(self) -> str: ...

    def score(self, path: Path) -> dict[str, float]: ...


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
