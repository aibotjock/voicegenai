"""Export pipeline: master WAV + MP3 + M4A with provenance + loudness report.

Formats (pinned encoder settings — part of the determinism contract):
  WAV  48 kHz / 24-bit PCM (master)
  MP3  320 kbps CBR
  M4A  256 kbps (AAC)

Every export gets: provenance embedded in file metadata + sidecar JSON +
loudness report (UI, sidecar text file, file metadata).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from .provenance import Provenance, embed_m4a, embed_mp3, embed_wav, write_sidecar


@dataclass
class ExportResult:
    master_wav: str
    mp3: str | None
    m4a: str | None
    sidecar: str
    report: dict


def _run(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y"] + args,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg export failed: {proc.stderr[-1500:]}")


def loudness_report_text(prov: Provenance) -> str:
    l = prov.loudness
    return (
        "Presence Studio loudness report\n"
        f"  integrated loudness: {l.get('integrated_lufs', float('nan')):.2f} LUFS\n"
        f"  true peak:           {l.get('true_peak_db', float('nan')):.2f} dBTP\n"
        f"  loudness range:      {l.get('lra_lu', float('nan')):.2f} LU\n"
        f"  standard:            ITU-R BS.1770-4 / EBU R128\n"
    )


def export(
    audio_path: str,
    outdir: str,
    prov: Provenance,
    formats: tuple[str, ...] = ("wav", "mp3", "m4a"),
    stem: str = "presence",
) -> ExportResult:
    """Export a processed audio file with provenance on every artifact."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    mp3_path = m4a_path = None

    # master WAV (48 kHz / 24-bit) — DSP output is already the master format
    wav_out = outdir / f"{stem}.wav"
    y, sr = sf.read(audio_path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    sf.write(str(wav_out), y, 48000, subtype="PCM_24")
    embed_wav(prov, str(wav_out))

    if "mp3" in formats:
        mp3_path = str(outdir / f"{stem}.mp3")
        _run(["-i", str(wav_out), "-codec:a", "libmp3lame", "-b:a", "320k",
              "-ar", "48000", mp3_path])
        embed_mp3(prov, mp3_path)
    if "m4a" in formats:
        m4a_path = str(outdir / f"{stem}.m4a")
        _run(["-i", str(wav_out), "-codec:a", "aac", "-b:a", "256k",
              "-ar", "48000", m4a_path])
        embed_m4a(prov, m4a_path)

    sidecar = write_sidecar(prov, str(wav_out))
    with open(outdir / f"{stem}.loudness.txt", "w", encoding="utf-8") as f:
        f.write(loudness_report_text(prov))

    return ExportResult(
        master_wav=str(wav_out), mp3=mp3_path, m4a=m4a_path,
        sidecar=sidecar, report=prov.to_dict(),
    )
