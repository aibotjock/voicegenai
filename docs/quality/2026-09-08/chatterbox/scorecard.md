# Presence Studio quality scorecard

- generated: 2026-09-09T04:01:13+00:00
- engine: `chatterbox`  (ResembleAI/chatterbox 2025.08.18)
- reference sha256: `a1e1a0d3a1a2eaed…`
- design: `podcast`

## Gates

| gate | target | measured | pass |
|---|---|---|---|
| WER | ≤ 0.03 | 0.0549 | ❌ |
| SECS raw | ≥ 0.80 | 0.920 | ✅ |
| SECS @Boardroom | ≥ 0.75 | 0.843 | ✅ |
| UTMOS | ≥ 4.0 | 4.34 | ✅ |
| Integrated loudness | ±0.5 LU | -16.32 LUFS | ✅ |
| True peak | ≤ -1.5 dBTP | -1.50 dBTP | ✅ |
| Join clicks | 0 | 5 | ❌ |

## Detail

- RTF (GPU synth): 0.39× realtime
- flagged segments (WER>8%): 11
- LRA: 2.72 LU
- identity at presets: raw=0.920, boardroom=0.843, keynote=0.924, calm-expert=0.911, podcast=0.916

**Overall: GATES FAILED — does not ship**
