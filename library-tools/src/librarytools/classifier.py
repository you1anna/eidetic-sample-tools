"""Optional drum-role classifier vote for sample-analyze.

Clean-room reimplementation of a small CNN-BiLSTM mel classifier. The pretrained WEIGHTS are
user-supplied (see ``config.DRUM_MODEL_PATH``) and never redistributed — the upstream weights
carry no license, so this package ships only the integration and loads the file if present.

If torch/librosa are not installed, or the weights file is absent, ``available()`` returns False
and callers skip classification: ``sample-analyze`` then behaves exactly as before.

The model outputs one of 30 percussion classes. We map the drum-relevant ones onto CURATED
sound-role folders and treat the vote as authoritative only for the drum roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config

# ---- taxonomy -------------------------------------------------------------------------------

# Index -> class order the checkpoint was trained with (do not reorder).
INT2CLASS: tuple[str, ...] = (
    "whis", "met", "cow", "taik", "clav", "hhc", "cah", "tim", "tab", "kick",
    "rid", "bass", "thd", "hho", "rim", "shk", "stick", "tom", "clp", "wood",
    "cong", "snr", "tri", "vib", "cym", "gui", "fx", "tomf", "ped", "cui",
)
KICK_INDEX = INT2CLASS.index("kick")

# Predicted class -> CURATED role it would belong in. Classes with no clean role home
# (whis/met/gui/fx/thd/ped/cui/vib/tri) are omitted and surface as suggested_role="REVIEW".
CLASS_TO_ROLE: dict[str, str] = {
    "kick": "KICKS",
    "snr": "CLAP-SNARE", "clp": "CLAP-SNARE", "rim": "CLAP-SNARE",
    "hhc": "HATS-CYM", "hho": "HATS-CYM", "cym": "HATS-CYM", "rid": "HATS-CYM",
    "cong": "PERC", "clav": "PERC", "tom": "PERC", "tomf": "PERC", "tab": "PERC",
    "taik": "PERC", "cah": "PERC", "wood": "PERC", "cow": "PERC", "shk": "PERC",
    "tim": "PERC", "stick": "PERC",
    "bass": "BASS",
}

# CURATED roles the drum classifier is authoritative for (one-shot drum/perc content).
DRUM_ROLES: frozenset[str] = frozenset({"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC", "DRUM-KITS"})

# librosa mel/transform params — must match the values the weights were trained with.
# The checkpoint was trained on librosa's default-rate load (22050 Hz), so we must resample
# to the same rate; using native sr shifts every mel frame and wrecks the predictions.
_SR = 22050
_HOP_LENGTH = 256
_N_MELS = 128
_CLIP_FRAMES = 600
_MIN_SEQ = 17
_MAX_SEQ = 300


AUDIO_EXTS: frozenset[str] = frozenset({".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"})


@dataclass(frozen=True)
class RoleVote:
    top_class: str
    top_prob: float
    kick_prob: float
    suggested_role: str  # CURATED role for top_class, or "REVIEW"


@dataclass(frozen=True)
class RoleAuditRow:
    path: str            # relative to the library root
    current_role: str    # CURATED folder the file currently sits in
    authoritative: bool  # True only for drum roles the classifier is trained to judge
    top_class: str
    top_prob: float
    kick_prob: float
    suggested_role: str
    agree: str           # yes/no for authoritative rows, blank otherwise
    band: str            # trust/review/low for authoritative rows, blank otherwise
    note: str            # e.g. possible-drum-oneshot flag for non-drum roles


def _band(prob: float) -> str:
    return "trust" if prob >= 0.80 else "review" if prob >= 0.50 else "low"


def available() -> bool:
    """True when torch, librosa, and the weights file are all present."""
    try:
        import librosa  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return config.DRUM_MODEL_PATH.is_file()


def _build_module(params: dict):
    import torch.nn as nn

    class MelCnnBiLstm(nn.Module):
        """Layer names/order mirror the checkpoint so state_dict loads strict=True."""

        def __init__(self, p: dict) -> None:
            super().__init__()
            self.convl11 = nn.Sequential(
                nn.Dropout(p["dropout_11"]),
                nn.Conv2d(p["n_channels"], p["num_filters_11"], kernel_size=p["kernel_size_11"], stride=p["stride_11"]),
                nn.BatchNorm2d(p["num_filters_11"]),
                nn.ReLU(),
                nn.MaxPool2d(kernel_size=p["maxpool_size11"], stride=p["maxpool_stride11"]),
            )
            self.convl12 = nn.Sequential(
                nn.Dropout(p["dropout_12"]),
                nn.Conv2d(p["num_filters_11"], p["num_filters_12"], kernel_size=p["kernel_size_12"], stride=p["stride_12"]),
                nn.BatchNorm2d(p["num_filters_12"]),
                nn.ReLU(),
                nn.MaxPool2d(kernel_size=p["maxpool_size12"], stride=p["maxpool_stride12"]),
            )
            self.convl13 = nn.Sequential(
                nn.Dropout(p["dropout_13"]),
                nn.Conv2d(p["num_filters_12"], p["num_filters_13"], kernel_size=p["kernel_size_13"], stride=p["stride_13"]),
                nn.BatchNorm2d(p["num_filters_13"]),
                nn.ReLU(),
            )
            self.lstm = nn.LSTM(input_size=p["num_filters_13"], hidden_size=p["lstm_dim"], batch_first=True, bidirectional=True)
            self.fc1_dropout = nn.Dropout(p["fc1_dropout"])
            self.fc1 = nn.Linear(p["lstm_dim"] * 2, p["fc1_dim"])
            self.relu = nn.ReLU()
            self.fc2 = nn.Linear(p["fc1_dim"], p["outdim"])

        def forward(self, bx):  # bx: (batch, seqlen, band_dim)
            import torch

            bs, seqlen, band_dim = bx.shape
            bx = bx.unsqueeze(1)
            pos = _positional_encoding(bs, seqlen, band_dim, bx.dtype, bx.device)
            x = torch.cat((pos, bx), dim=1)  # channels: [xpos, ypos, mel]
            o = self.convl13(self.convl12(self.convl11(x)))
            o = o.squeeze(-1).transpose(-2, -1)  # (batch, time', filters)
            _, (hs, _) = self.lstm(o)
            s = torch.cat((hs[0], hs[1]), dim=1)
            return self.fc2(self.relu(self.fc1(s)))

    return MelCnnBiLstm(params)


def _positional_encoding(bs: int, seqlen: int, band_dim: int, dtype, device):
    """Reproduce the checkpoint's fixed x/y positional-encoding formula."""
    import numpy as np
    import torch

    ypos = (np.arange(band_dim) - 63.5) / 36.94928957368463
    xpos = np.log(np.arange(seqlen) + 1) / 4.38202663 - 0.33
    ypos_ext = np.tile(ypos, (bs, len(xpos), 1)).reshape(bs, 1, seqlen, band_dim)
    xpos_ext = np.tile(xpos, (bs, len(ypos), 1)).transpose(0, -1, -2).reshape(bs, 1, seqlen, band_dim)
    posenc = np.concatenate((xpos_ext, ypos_ext), axis=1)  # (bs, 2, seqlen, band_dim)
    return torch.from_numpy(posenc).to(dtype=dtype, device=device)


class DrumRoleClassifier:
    """Loads local weights once and votes on batches of audio files."""

    def __init__(self, model_path: Path | None = None) -> None:
        import torch

        path = model_path or config.DRUM_MODEL_PATH
        # Safe load: the checkpoint pickle references only OrderedDict / storages /
        # _rebuild_tensor_v2, all in torch's default weights_only allowlist.
        state = torch.load(path, map_location="cpu", weights_only=True)
        self._torch = torch
        self.net = _build_module(state["params"])
        self.net.load_state_dict(state["model_state_dict"], strict=True)
        self.net.eval()

    def _mel(self, path: Path):
        import librosa
        import numpy as np

        y, sr = librosa.load(str(path), sr=_SR)
        mel = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=_HOP_LENGTH, n_mels=_N_MELS)
        log_mel = librosa.amplitude_to_db(mel, ref=np.max)
        std = (log_mel + 80.0) / 80.0
        if std.shape[-1] > _CLIP_FRAMES:
            std = std[:, :_CLIP_FRAMES]
        return std.T  # (time, band)

    def vote_batch(self, paths: list[Path]) -> dict[Path, RoleVote]:
        import numpy as np
        import torch

        specs: list[tuple[Path, np.ndarray]] = []
        for p in paths:
            try:
                specs.append((p, self._mel(p)))
            except Exception:  # unreadable/corrupt file — skip, caller records no vote
                continue
        if not specs:
            return {}
        maxlen = max(_MIN_SEQ, min(_MAX_SEQ, max(m.shape[0] for _, m in specs)))
        batch = np.zeros((len(specs), maxlen, _N_MELS), dtype=np.float64)
        for i, (_, m) in enumerate(specs):
            n = min(m.shape[0], maxlen)
            batch[i, :n] = m[:n]
        with torch.no_grad():
            logits = self.net(torch.from_numpy(batch).float())
            probs = torch.softmax(logits, dim=1).numpy()
        out: dict[Path, RoleVote] = {}
        for (p, _), row in zip(specs, probs):
            idx = int(row.argmax())
            top = INT2CLASS[idx]
            out[p] = RoleVote(
                top_class=top,
                top_prob=float(row[idx]),
                kick_prob=float(row[KICK_INDEX]),
                suggested_role=CLASS_TO_ROLE.get(top, "REVIEW"),
            )
        return out


def build_role_audit(root: Path | None = None, chunk: int = 64) -> list[RoleAuditRow]:
    """Vote on every audio file under CURATED/<role>/. Read-only: moves nothing.

    Drum roles get an authoritative agree/disagree + confidence band. Non-drum roles
    (BASS, SYNTH, DRONE, VOCALS, FX, LOOPS) get only a soft 'possible-drum-oneshot'
    outlier note when the model is very confident — never a role verdict.
    """
    import csv  # noqa: F401  (kept local; writer lives in write_role_audit)

    root = config.require_root(root or config.SAMPLES_ROOT)
    curated = root / "CURATED"
    clf = DrumRoleClassifier()
    rows: list[RoleAuditRow] = []
    for role_dir in sorted(p for p in curated.iterdir() if p.is_dir()):
        role = role_dir.name
        authoritative = role in DRUM_ROLES
        files = sorted(
            f for f in role_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS and not f.name.startswith("._")
        )
        for i in range(0, len(files), chunk):
            votes = clf.vote_batch(files[i:i + chunk])
            for f in files[i:i + chunk]:
                v = votes.get(f)
                if v is None:
                    continue
                if authoritative:
                    agree, band, note = ("yes" if v.suggested_role == role else "no"), _band(v.top_prob), ""
                else:
                    agree, band = "", ""
                    note = "possible-drum-oneshot" if v.top_prob >= 0.80 and v.suggested_role in DRUM_ROLES else ""
                rows.append(RoleAuditRow(
                    path=f.relative_to(root).as_posix(),
                    current_role=role,
                    authoritative=authoritative,
                    top_class=v.top_class,
                    top_prob=v.top_prob,
                    kick_prob=v.kick_prob,
                    suggested_role=v.suggested_role,
                    agree=agree,
                    band=band,
                    note=note,
                ))
    return rows


def write_role_audit(path: Path, rows: list[RoleAuditRow]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow([
            "path", "current_role", "authoritative", "top_class", "top_prob",
            "kick_prob", "suggested_role", "agree", "band", "note",
        ])
        for r in rows:
            w.writerow([
                r.path, r.current_role, "yes" if r.authoritative else "",
                r.top_class, f"{r.top_prob:.3f}", f"{r.kick_prob:.3f}",
                r.suggested_role, r.agree, r.band, r.note,
            ])


def summarise_role_audit(rows: list[RoleAuditRow]) -> list[str]:
    """Per-role agreement summary for the CLI + report."""
    lines: list[str] = []
    by_role: dict[str, list[RoleAuditRow]] = {}
    for r in rows:
        by_role.setdefault(r.current_role, []).append(r)
    for role in sorted(by_role):
        items = by_role[role]
        if items[0].authoritative:
            disagree = [r for r in items if r.agree == "no"]
            trust_disagree = [r for r in disagree if r.band == "trust"]
            lines.append(
                f"- {role}: {len(items)} files | mismatched role: {len(disagree)} "
                f"({len(trust_disagree)} high-confidence) "
                f"| agree: {len(items) - len(disagree)}"
            )
        else:
            flagged = [r for r in items if r.note]
            lines.append(f"- {role}: {len(items)} files | possible-drum-oneshot flags: {len(flagged)}")
    return lines
