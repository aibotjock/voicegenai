"""Layer A voice designs: parameter model + the six shipped presets.

A Design is a named, hashable set of Layer-A parameters. The DSP order is
fixed (see graph.build_plan); reordering requires a quality re-run.

Identity-preservation rule: a design may change character but not person.
Every shipped preset is run through the identity gate in the eval harness
(docs/quality/). A preset that drops the gate ships fixed or not at all.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Design:
    id: str
    name: str
    character: str = ""
    # pace (0.85..1.20), pause shaping at paragraph boundaries (ms)
    pace: float = 1.0
    pause_shaping_ms: int = 0
    # pitch (-12..+12 st) and formant (-2..+2 st), formant-locked
    pitch_st: float = 0.0
    formant_st: float = 0.0
    formant_lock: bool = True
    # EQ, 5 bands, each +/-6 dB
    eq_low_shelf_db: float = 0.0    # 150 Hz warmth
    eq_mud_db: float = 0.0          # 400 Hz
    eq_body_db: float = 0.0         # 600 Hz
    eq_presence_db: float = 0.0     # 3000 Hz
    eq_air_db: float = 0.0          # 12000 Hz air
    # dynamics
    comp_ratio: float = 0.0         # 0 = off; 2.0..4.0
    comp_threshold_db: float = -20.0
    deess: bool = True
    deess_threshold_db: float = -26.0
    deess_ratio: float = 4.0
    # loudness (ITU-R BS.1770-4 / EBU R128)
    lufs_target: float = -16.0
    true_peak_limit_db: float = -1.5
    # finalize
    pad_ms: int = 200
    # denoising on generated audio is a repair tool, off by default
    denoise: bool = False

    def __post_init__(self) -> None:
        if not (0.85 <= self.pace <= 1.20):
            raise ValueError("pace must be within 0.85..1.20")
        if not (-12 <= self.pitch_st <= 12):
            raise ValueError("pitch must be within -12..+12 st")
        if not (-2 <= self.formant_st <= 2):
            raise ValueError("formant must be within -2..+2 st")
        for f in ("eq_low_shelf_db", "eq_mud_db", "eq_body_db", "eq_presence_db", "eq_air_db"):
            if not (-6 <= getattr(self, f) <= 6):
                raise ValueError(f"{f} must be within +/-6 dB")
        if self.comp_ratio and not (2.0 <= self.comp_ratio <= 4.0):
            raise ValueError("comp_ratio must be 0 (off) or 2.0..4.0")
        if not (0 <= self.pause_shaping_ms <= 400):
            raise ValueError("pause_shaping_ms must be 0..400")
        if not (self.pad_ms == 0 or 50 <= self.pad_ms <= 1000):
            raise ValueError("pad_ms must be 50..1000 (0 allowed for raw)")

    def params_hash(self) -> str:
        d = {k: v for k, v in asdict(self).items() if k not in ("id", "name")}
        blob = json.dumps(d, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Shipped presets (defaults — tune by ear; each is gated by the harness)
# ---------------------------------------------------------------------------

BOARDROOM = Design(
    id="boardroom", name="Boardroom",
    character="authoritative, lower, steadier",
    pitch_st=-2.0, formant_st=-0.5, pace=0.95,
    eq_low_shelf_db=+1.5, eq_presence_db=+2.0,
    comp_ratio=3.0, comp_threshold_db=-20.0,
    lufs_target=-16.0,
)

KEYNOTE = Design(
    id="keynote", name="Keynote",
    character="crisp, energetic, broadcast-clean",
    pitch_st=0.0, formant_st=0.0, pace=1.0,
    eq_presence_db=+3.0, eq_air_db=+1.5,
    pause_shaping_ms=250,
    comp_ratio=2.5, comp_threshold_db=-18.0,
    lufs_target=-16.0,
)

CALM_EXPERT = Design(
    id="calm-expert", name="Calm Expert",
    character="reassuring, deliberate",
    pace=0.90,
    eq_low_shelf_db=+2.0, eq_presence_db=+1.0,
    comp_ratio=2.0, comp_threshold_db=-18.0,
    lufs_target=-16.0,
)

PODCAST = Design(
    id="podcast", name="Podcast/Video",
    character="natural, flat, consistent",
    pace=1.0,
    lufs_target=-16.0,
    comp_ratio=2.0, comp_threshold_db=-18.0,
    deess=True, deess_threshold_db=-26.0,
)

REHEARSAL_RAW = Design(
    id="rehearsal-raw", name="Rehearsal Raw",
    character="unprocessed self-check — no processing, original loudness",
    pad_ms=0,
)

PRESETS: dict[str, Design] = {
    d.id: d for d in (BOARDROOM, KEYNOTE, CALM_EXPERT, PODCAST, REHEARSAL_RAW)
}

BROADCAST_LUFS = -23.0
DIGITAL_LUFS = -16.0


def get_preset(preset_id: str, lufs_target: float | None = None) -> Design:
    d = PRESETS.get(preset_id)
    if d is None:
        raise KeyError(f"unknown preset {preset_id!r}; known: {sorted(PRESETS)}")
    if lufs_target is not None:
        return Design(
            **{**asdict(d), "lufs_target": lufs_target,
               "id": f"{d.id}-lufs{int(lufs_target)}"}
        )
    return d


def from_params(params: dict, preset_id: str = "custom",
                name: str = "Custom") -> Design:
    """Build a custom design from a UI parameter map (pro panel)."""
    known = {f.name for f in fields(Design)} - {"id", "name"}
    clean = {k: v for k, v in params.items() if k in known and v is not None}
    return Design(id=preset_id, name=name, **clean)
