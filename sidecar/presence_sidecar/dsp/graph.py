"""Versioned DSP plan builder.

One function (build_plan) emits the complete processing plan for a Design.
The process order is FIXED and documented (reordering requires a quality
re-run of the eval harness):

  1. denoise          separate pre-stage (captures always; generated audio
                      opt-in repair, off by default) — not part of the graph
  2. resample 48 kHz
  3. Rubber Band      pitch-locked tempo (pace) + pitch + formant,
                      formant lock ON (no chipmunk; chipmunk is a defect)
  4. EQ, 5 bands      low shelf 150 / mud 400 / body 600 / presence 3000 /
                      air 12000, each +/-6 dB
  5. compressor       2:1..4:1, auto makeup (two-pass measured)
  6. de-esser         Python band-split gain reduction, 6-9 kHz
                      (FFmpeg has no native de-ess)
  7. true-peak limiter (pre-normalization safety net)
  8. loudness         two-pass EBU R128 loudnorm + independent pyloudnorm
                      verification
  9. finalize         post-loudnorm TP guard, DC-offset removal,
                      200 ms head/tail padding, 48 kHz/24-bit master

The plan is a data object (DspPlan); golden-file tests pin the exact filter
strings for fixed inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .design import Design

GRAPH_BUILDER_VERSION = "1.0.0"

# EQ, 5 bands. FFmpeg has no generic "type" param on equalizer (that is a
# width_type option): low/high shelves use the bass/treble filters, the
# three mids use the peaking equalizer. Q=1 for all bands.
# (filter function, frequency Hz, design attribute, description)
EQ_BANDS = (
    ("bass",      150.0,  "eq_low_shelf_db", "low shelf warmth"),
    ("equalizer", 400.0,  "eq_mud_db",       "mud cut"),
    ("equalizer", 600.0,  "eq_body_db",      "body"),
    ("equalizer", 3000.0, "eq_presence_db",  "mid presence"),
    ("treble",    12000.0, "eq_air_db",       "air"),
)


def _eq_filter(func: str, freq: float, gain: float) -> str:
    if func == "bass":
        return f"bass=g={_f(gain)}:f={_f(freq)}:t=q:w=1"
    if func == "treble":
        return f"treble=g={_f(gain)}:f={_f(freq)}:t=q:w=1"
    return f"equalizer=f={_f(freq)}:t=q:w=1:g={_f(gain)}"


@dataclass
class DeessConfig:
    enabled: bool = True
    band_lo: float = 6000.0
    band_hi: float = 9000.0
    threshold_db: float = -26.0
    ratio: float = 4.0
    attack_ms: float = 5.0
    release_ms: float = 80.0
    knee_db: float = 6.0


@dataclass
class FinalizeConfig:
    pad_ms: int = 200
    dc_remove: bool = True
    tp_guard: bool = True
    rate: int = 48000
    bits: int = 24


@dataclass
class DspPlan:
    design: Design
    builder_version: str = GRAPH_BUILDER_VERSION
    bypass: bool = False                 # Rehearsal Raw
    graph_a: str = ""                    # FFmpeg -af: resample..compressor
    deess: DeessConfig | None = None
    graph_b: str = ""                    # FFmpeg -af: limiter (pre-loudnorm)
    finalize: FinalizeConfig = field(default_factory=FinalizeConfig)
    lufs_target: float = -16.0
    tp_limit_db: float = -1.5

    def to_dict(self) -> dict:
        return {
            "builder_version": self.builder_version,
            "bypass": self.bypass,
            "graph_a": self.graph_a,
            "deess": vars(self.deess) if self.deess else None,
            "graph_b": self.graph_b,
            "finalize": vars(self.finalize),
            "lufs_target": self.lufs_target,
            "tp_limit_db": self.tp_limit_db,
            "design_params_hash": self.design.params_hash(),
        }


def _f(x: float) -> str:
    """Stable float formatting (no scientific, no -0.0)."""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s


def _ratio(st: float) -> float:
    """Semitones -> frequency ratio (ffmpeg rubberband takes ratios,
    not semitones: pitch range 0.01..100 where 2.0 = +1 octave)."""
    return 2.0 ** (st / 12.0)


def _build_graph_a(d: Design) -> str:
    """Resample -> Rubber Band (pace + pitch + formant) -> EQ -> compressor.

    ffmpeg's rubberband wrapper exposes pitch/tempo as ratios and formant as
    an enum (shifted|preserved). Identity rule: pitch shifts ship with
    formant preserved (formant lock — chipmunk output is a defect). An
    independent formant shift is done with the standard two-pass trick:
    shift pitch+formant together, then shift pitch back with formants
    preserved — net effect: pitch unchanged, formants moved.
    """
    parts = ["aresample=48000"]
    r_pitch = _ratio(d.pitch_st)
    r_formant = _ratio(d.formant_st)
    if d.pace != 1.0 or d.pitch_st != 0.0 or d.formant_st != 0.0:
        if d.formant_st != 0.0 and d.formant_lock:
            # pass 1: tempo + (pitch+formant) shifted together
            parts.append(
                f"rubberband=tempo={_f(d.pace)}:pitch={_f(r_pitch * r_formant)}:"
                f"formant=shifted"
            )
            # pass 2: pitch back down, formants held at the shifted position
            parts.append(
                f"rubberband=pitch={_f(1.0 / r_pitch)}:formant=preserved"
            )
        else:
            formant_mode = "preserved" if d.formant_lock else "shifted"
            parts.append(
                f"rubberband=tempo={_f(d.pace)}:pitch={_f(r_pitch)}:"
                f"formant={formant_mode}"
            )
    for func, freq, attr, _desc in EQ_BANDS:
        gain = getattr(d, attr)
        if abs(gain) >= 0.05:
            parts.append(_eq_filter(func, freq, gain))
    if d.comp_ratio >= 2.0:
        # makeup is auto: the runner measures pass-1 gain reduction and
        # re-runs with the measured makeup (see engine.run_dsp).
        parts.append(
            f"acompressor=threshold={_f(d.comp_threshold_db)}dB:"
            f"ratio={_f(d.comp_ratio)}:attack=10:release=100:knee=6:makeup=1dB"
        )
    return ",".join(parts)


def _build_graph_b(d: Design) -> str:
    """Everything before the two-pass loudnorm stage (limiter, etc.)."""
    limit = 10 ** (d.true_peak_limit_db / 20.0)
    return f"alimiter=limit={limit:.5f}:level=false"


def loudnorm_measure_graph(d: Design) -> str:
    """Pass 1: measurement only (JSON on stderr)."""
    return (
        f"loudnorm=I={_f(d.lufs_target)}:TP={_f(d.true_peak_limit_db)}:"
        f"LRA=11:print_format=json"
    )


def loudnorm_apply_graph(d: Design, measured: dict) -> str:
    """Pass 2: linear mode using pass-1 measurements.

    `measured` is the raw pass-1 JSON: its keys are input_i/input_tp/
    input_lra/input_thresh/target_offset; the loudnorm pass-2 parameters are
    measured_I/measured_TP/measured_LRA/measured_thresh/offset.
    """
    return (
        f"loudnorm=I={_f(d.lufs_target)}:TP={_f(d.true_peak_limit_db)}:LRA=11:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def build_plan(d: Design) -> DspPlan:
    if d.id.startswith("rehearsal-raw"):
        return DspPlan(
            design=d, bypass=True,
            finalize=FinalizeConfig(pad_ms=0, dc_remove=False, tp_guard=False),
        )
    deess = DeessConfig(
        enabled=d.deess,
        threshold_db=d.deess_threshold_db,
        ratio=d.deess_ratio,
    ) if d.deess else None
    return DspPlan(
        design=d,
        graph_a=_build_graph_a(d),
        deess=deess,
        graph_b=_build_graph_b(d),
        finalize=FinalizeConfig(pad_ms=d.pad_ms),
        lufs_target=d.lufs_target,
        tp_limit_db=d.true_peak_limit_db,
    )
