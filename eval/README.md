# Eval assets (spec §7)

- `eval_script_50.json` — the fixed 50-sentence evaluation script (committed,
  hashed; regenerated inputs are forbidden — a change re-runs the gates).
- `reference/` — the 100–120 s reference capture used by the harness and the
  bake-off. In production this is the user's own consent-gated capture.

## Reference stand-in (CI/eval)

The committed reference is a **stand-in**, not a user voice: utterances from
LibriSpeech `test-clean` (OpenSLR 12), which is distributed under
**CC BY 4.0** ( attribution: Vassil Panayotov, Daniel Povey et al., LibriSpeech
ASR corpus). Same-speaker utterances are concatenated with short silences to
reach the 100–120 s reference window, and the LibriSpeech ground-truth
transcripts provide the reference transcript required by reference-text
engines and by the identity/WER metrics.

Why a stand-in: the harness must be CI-runnable without recording a human;
the user's own profile replaces it in the shipped product (consent-gated).
The stand-in is used ONLY for: engine scorecards, DSP gate re-runs, and
pipeline validation — never shipped as a "voice."

## Provenance of the reference

Recorded in `reference_manifest.json`: source utterance paths, transcript,
concatenation script (seeded), license, and SHA-256 of the reference wav.
