from __future__ import annotations

import csv
from pathlib import Path

from librarytools import review


def test_vendor_drum_folders_map_to_role_folders():
    assert review.classify_role(
        Path("_PACKS/Vendor Library/Samples/Drums/Kick/Kick 909.wav")
    ).role == "KICKS"
    assert review.classify_role(
        Path("_PACKS/Vendor Library/Samples/Drums/Clap/Clap 808.wav")
    ).role == "CLAP-SNARE"
    assert review.classify_role(
        Path("_PACKS/Vendor Library/Samples/Drums/Hihat/ClosedHH 70sDnB.wav")
    ).role == "HATS-CYM"


def test_goldbaby_and_vengeance_patterns_map_to_roles():
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.Super.Analog.909/SA909_Samples/SA909_BD/SA909_BD_01.wav")
    ).role == "KICKS"
    assert review.classify_role(
        Path("DRUM-KITS/Vengeance Essential Tech House/VETH1 Bassdrums/VETH1 Bassdrum 001.wav")
    ).role == "KICKS"
    assert review.classify_role(
        Path("DRUM-KITS/Vengeance Essential Tech House/VETH1 FX Sounds/VETH1 Uplifter/Up 001.wav")
    ).role == "FX-RISE-IMPACT"


def test_sean_pack_loop_and_bass_patterns_map_to_roles():
    assert review.classify_role(
        Path("_PACKS/Sean/Analogue Underground 2/Wav/modular drum loops/au2_132.wav")
    ).role == "DRUM-LOOPS"
    assert review.classify_role(
        Path("_PACKS/Sean/abitdeeper.Real.Chicago.House.WAV/JU BASS LOOPS 120 BPM/JU_01.wav")
    ).role == "BASS"


def test_drum_machine_abbreviations_map_to_roles():
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.Super.Analog.909/SA909_HH/HH_909D2_AC_R6.wav")
    ).role == "HATS-CYM"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.Super.Analog.909/SA909_HH/HHo_909D2_AC_R2.wav")
    ).role == "HATS-CYM"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SA909/TDMVol2_Samples/CR-78/CR78_Clave_T1S_R1.wav")
    ).role == "PERC"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SA909/Vol2/RX-5/RX5_CowHigh_C2A.wav")
    ).role == "PERC"
    assert review.classify_role(
        Path("DRUM-KITS/Goldbaby.SP-1200.Vol.2/707_727_vs_SP1200/Cabasa_727TR1_SP1200R.wav")
    ).role == "PERC"


def test_abbreviations_do_not_false_match_full_words():
    # 'chord' must not hit hat-code 'ch'; 'ohio' must not hit 'oh'
    assert review.classify_role(
        Path("_PACKS/Keys/Chord stack warm.wav")
    ).role == "SYNTH-STAB-CHORD"
    assert review.classify_role(
        Path("_PACKS/Field/Ohio rainstorm.wav")
    ).role != "HATS-CYM"


def test_cryptic_sean_names_stay_in_review():
    assert review.classify_role(Path("_PACKS/Sean/Sean 80s/o.wav")).role == "_REVIEW"
    assert review.classify_role(Path("_PACKS/Sean/cloud 909/dms2.wav")).role == "_REVIEW"


def test_loop_context_can_extract_bare_bpm_without_treating_drum_machines_as_bpm():
    loop = review.build_item(
        Path("/samples/_PACKS/Sean/Analogue Underground 2/Wav/modular drum loops/au2_132.wav"),
        Path("/samples"),
    )
    kick = review.build_item(
        Path("/samples/DRUM-KITS/Goldbaby/SA909_BD/SA909_BD_01.wav"),
        Path("/samples"),
    )

    assert loop.bpm == "132"
    assert loop.tempo_fit == "techno-core"
    assert loop.proposed_name.startswith("132_au2_sean")
    assert kick.bpm == ""


def test_hardware_name_preserves_extension_and_flags_digitakt_length():
    item = review.build_item(
        Path("/samples/_PACKS/Sean/Pack/JU BASS LOOPS 120 BPM/JU Deep Rolling Bass Loop In A Minor.wav"),
        Path("/samples"),
    )

    assert item.main_category == "BASS"
    assert item.sample_type == "loop"
    assert item.bpm == "120"
    assert item.key == "am"
    assert item.tempo_fit == "house-lower"
    assert item.proposed_name.endswith(".wav")
    assert item.proposed_name.startswith("120_am_")
    assert " " not in item.proposed_name
    assert "digitakt-name>24" in item.warnings


def test_bracketed_bpm_is_indexed_as_techno_core_loop():
    item = review.build_item(
        Path("/samples/_PACKS/Vendor Library/Samples/Loops/Guitar/GuitarFunk01 [130].wav"),
        Path("/samples"),
    )

    assert item.main_category == "SYNTH-STAB-CHORD"
    assert item.sample_type == "loop"
    assert item.bpm == "130"
    assert item.tempo_fit == "techno-core"
    assert item.proposed_name.startswith("130_guitarfunk01_vendor-library")


def test_kick_one_shot_keeps_tempo_unknown():
    item = review.build_item(
        Path("/samples/DRUM-KITS/Pack/Kicks/Kick Big 909.wav"),
        Path("/samples"),
    )

    assert item.main_category == "KICKS"
    assert item.sample_type == "one-shot"
    assert item.bpm == ""
    assert item.key == ""
    assert item.tempo_fit == "unknown"


def test_write_manifest_outputs_review_rows_without_moving_files(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    src = root / "DRUM-KITS" / "Pack" / "Kicks" / "Kick Big 909.wav"
    src.parent.mkdir(parents=True)
    src.write_text("audio")
    out = tmp_path / "review.tsv"

    items = review.build_review(root=root, probe_durations=False)
    review.write_manifest(out, items)

    assert src.exists()
    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["source"] == "DRUM-KITS/Pack/Kicks/Kick Big 909.wav"
    assert rows[0]["main_category"] == "KICKS"
    assert rows[0]["role"] == "KICKS"
    assert rows[0]["sample_type"] == "one-shot"
    assert rows[0]["bpm"] == ""
    assert rows[0]["key"] == ""
    assert rows[0]["tempo_fit"] == "unknown"
    assert rows[0]["proposed_name"] == "kick-big-909_pack.wav"
    assert rows[0]["warnings"] == ""


def test_main_writes_explicit_manifest_without_apply(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    src = root / "_PACKS" / "Sean" / "Pack" / "Drum Loops" / "Loop 132 BPM.wav"
    src.parent.mkdir(parents=True)
    src.write_text("audio")
    out = tmp_path / "review.tsv"

    code = review.main(["--root", str(root), "--no-probe", "--output", str(out)])

    assert code == 0
    assert src.exists()
    assert out.exists()


def test_write_split_indexes_groups_high_confidence_and_tempo(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    kick = root / "DRUM-KITS" / "Pack" / "Kicks" / "Kick Big 909.wav"
    bass = root / "_PACKS" / "Sean" / "Pack" / "BASS LOOPS 120 BPM" / "Deep Bass Loop A Minor.wav"
    for src in (kick, bass):
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("audio")
    out_dir = tmp_path / "index"

    items = review.build_review(root=root, probe_durations=False)
    review.write_split_indexes(out_dir, items)

    assert (out_dir / "high-confidence" / "KICKS.tsv").exists()
    assert (out_dir / "high-confidence" / "BASS.tsv").exists()
    assert (out_dir / "tempo" / "house-lower.tsv").exists()
    assert (out_dir / "review-needed.tsv").exists()
