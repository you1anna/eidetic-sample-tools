"""Feature-row construction and character tags for sample analysis."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from . import audiofeatures, config, probe, review
from .analyze_types import FeatureRow, SourceRow
from .featurecache import FEATURE_COLUMNS, FeatureCache, FeatureRecord

def _is_sample_source(row: SourceRow) -> bool:
    return row.source_kind in {"curated-sample", "vendor-pack-audio", "octatrack-set-audio"}


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _fmt_num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _reason(name: str, value: float) -> str:
    return f"{name}={_fmt_num(value)}"


def _empty_acoustic_values() -> dict[str, float | None]:
    return {column: None for column in FEATURE_COLUMNS}


def _acoustic_values(record: FeatureRecord | None) -> dict[str, float | None]:
    if record is None or record.error:
        return _empty_acoustic_values()
    return {column: getattr(record, column) for column in FEATURE_COLUMNS}


def _read_acoustic_features(
    root: Path,
    source: SourceRow,
    cache: FeatureCache | None,
) -> FeatureRecord:
    full_path = root / source.path
    try:
        stat = full_path.stat()
    except OSError as exc:
        return FeatureRecord(path=source.path, size=0, mtime=0.0, error=str(exc))
    if cache is not None:
        cached = cache.get_or_none(source.path, stat.st_size, stat.st_mtime)
        if cached is not None:
            return cached
    record = audiofeatures.extract(full_path, cache_path=source.path)
    if cache is not None:
        cache.upsert(record)
    return record


def derive_character_tags(row: FeatureRow) -> tuple[str, str]:
    tags: list[str] = []
    reasons: list[str] = []
    text = row.path.as_posix().lower().replace("_", " ").replace("-", " ")

    def add(tag: str, reason: str) -> None:
        if tag not in tags:
            tags.append(tag)
            reasons.append(reason)

    if row.role == "KICKS":
        if row.sub_ratio is not None and row.sub_ratio >= 0.60:
            add("subby", _reason("sub_ratio", row.sub_ratio))
        if row.tail_ms is not None and row.tail_ms <= 250:
            add("short", _reason("tail_ms", row.tail_ms))
        if (
            row.tail_ms is not None
            and row.tail_ms >= 700
            and row.low_ratio is not None
            and row.low_ratio >= 0.55
        ):
            add("rumble-long", f"{_reason('tail_ms', row.tail_ms)};{_reason('low_ratio', row.low_ratio)}")
        if row.attack_ms is not None and row.attack_ms <= 5:
            add("clicky", _reason("attack_ms", row.attack_ms))
        if _has(text, "sub"):
            add("subby", "path:sub")
        if row.duration is not None and row.duration <= 0.75:
            add("short", f"duration={row.duration:.2f}s")
        if _has(text, "rumble"):
            add("rumble-long", "path:rumble")
    if row.role == "HATS-CYM":
        if (
            row.flatness is not None
            and row.centroid_hz is not None
            and row.flatness >= 0.35
            and row.centroid_hz >= 3500
        ):
            add("metallic", f"{_reason('flatness', row.flatness)};{_reason('centroid_hz', row.centroid_hz)}")
        if row.tail_ms is not None and row.tail_ms <= 250:
            add("tight", _reason("tail_ms", row.tail_ms))
        if _has(text, "metallic", "metal"):
            add("metallic", "path:metallic")
        if _has(text, "tight", "closed") or (row.duration is not None and row.duration <= 0.35):
            add("tight", f"duration={row.duration:.2f}s" if row.duration is not None else "path:tight")
    if row.role == "PERC":
        if _has(text, "wood", "clave", "block"):
            add("wood", "path:wood-family")
        if _has(text, "tribal", "conga", "tom", "cowbell"):
            add("tribal", "path:tribal-family")
    if row.role == "DRUM-LOOPS":
        if row.duration is not None and row.duration >= 1.0 and row.onset_density is not None:
            if row.onset_density <= 2.0:
                add("sparse", _reason("onset_density", row.onset_density))
            if row.onset_density >= 8.0:
                add("busy", _reason("onset_density", row.onset_density))
        if _has(text, "sparse"):
            add("sparse", "path:sparse")
        if _has(text, "busy"):
            add("busy", "path:busy")
        if _has(text, "top") and row.bpm:
            add(f"top-{row.bpm}", f"path:top;bpm={row.bpm}")
    if row.role == "DRONE-ATMOS":
        if (
            row.duration is not None
            and row.duration >= 5.0
            and row.onset_density is not None
            and row.onset_density <= 1.5
            and row.centroid_hz is not None
            and row.centroid_hz <= 1200
        ):
            add(
                "dub-wash",
                f"duration={_fmt_num(row.duration)}s;{_reason('onset_density', row.onset_density)};{_reason('centroid_hz', row.centroid_hz)}",
            )
        if _has(text, "dub", "wash"):
            add("dub-wash", "path:dub/wash")
    if row.processing_tag:
        add(row.processing_tag, row.processing_reason)

    return ";".join(tags), ";".join(reasons)


def _curated_folder_role(rel: Path) -> str | None:
    if (
        len(rel.parts) >= 2
        and rel.parts[0] == "CURATED"
        and rel.parts[1] in review.ROLE_FOLDERS
    ):
        return rel.parts[1]
    return None


def build_feature_rows(
    root: Path,
    sources: list[SourceRow],
    probe_durations: bool = False,
    audio_features: bool = False,
    cache_path: Path | None = None,
) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    cache = FeatureCache(cache_path or (config.MANIFEST_DIR / "sample-intelligence.sqlite")) if audio_features else None
    for source in sources:
        if not _is_sample_source(source):
            continue
        full_path = root / source.path
        acoustic = _read_acoustic_features(root, source, cache) if audio_features else None
        values = _acoustic_values(acoustic)
        duration = values["duration_s"] if values["duration_s"] is not None else (
            probe.duration(full_path) if probe_durations else None
        )
        item = review.build_item(full_path, root, probe_durations=False)
        role = _curated_folder_role(source.path) or item.role
        sample_type = review.sample_type(source.path, role, duration)
        proposed_name = review.proposed_name(source.path, role)
        review_reason = f"curated-role:{role}" if role != item.role else item.reason
        row = FeatureRow(
            path=source.path,
            source_kind=source.source_kind,
            source_name=source.source_name,
            role=role,
            sample_type=sample_type,
            bpm=item.bpm,
            key=item.key,
            tempo_fit=item.tempo_fit,
            duration=duration,
            duration_s=values["duration_s"],
            peak=values["peak"],
            rms=values["rms"],
            crest=values["crest"],
            attack_ms=values["attack_ms"],
            tail_ms=values["tail_ms"],
            head_silence_ms=values["head_silence_ms"],
            tail_silence_ms=values["tail_silence_ms"],
            centroid_hz=values["centroid_hz"],
            flatness=values["flatness"],
            sub_ratio=values["sub_ratio"],
            low_ratio=values["low_ratio"],
            mid_ratio=values["mid_ratio"],
            high_ratio=values["high_ratio"],
            onset_density=values["onset_density"],
            zcr=values["zcr"],
            audio_error=acoustic.error if acoustic and acoustic.error else "",
            proposed_name=proposed_name,
            review_reason=review_reason,
            processing_tag=source.processing_tag,
            processing_reason=source.processing_reason,
            character_tags="",
            tag_reasons="",
        )
        tags, reasons = derive_character_tags(row)
        rows.append(replace(row, character_tags=tags, tag_reasons=reasons))
    return rows
