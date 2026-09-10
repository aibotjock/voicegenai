/**
 * Load a locally-exported audio file for playback + waveform display.
 * Decoding happens off the render path; results are cached per path.
 */
import { useEffect, useState } from "react";
import { readLocalFileBlob } from "../../lib/fs/localFiles";

export interface LoadedAudio {
  url: string;
  peaks: number[];
  durationS: number | null;
}

interface State {
  status: "idle" | "loading" | "ready" | "error";
  audio: LoadedAudio | null;
  error: string | null;
}

const PEAK_COUNT = 120;

export function useAudioFile(path: string | null): State {
  const [state, setState] = useState<State>({
    status: "idle",
    audio: null,
    error: null,
  });

  useEffect(() => {
    if (!path) {
      setState({ status: "idle", audio: null, error: null });
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setState({ status: "loading", audio: null, error: null });

    (async () => {
      try {
        const blob = await readLocalFileBlob(path);
        objectUrl = URL.createObjectURL(blob);

        // Decode for peaks + exact duration. Failure to decode must not
        // block playback — the <audio> element can still handle the file.
        let peaks: number[] = [];
        let durationS: number | null = null;
        try {
          const buf = await blob.arrayBuffer();
          const ctx = new AudioContext();
          try {
            const decoded = await ctx.decodeAudioData(buf);
            durationS = decoded.duration;
            peaks = computePeaks(decoded, PEAK_COUNT);
          } finally {
            void ctx.close().catch(() => undefined);
          }
        } catch {
          peaks = [];
        }

        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setState({ status: "ready", audio: { url: objectUrl, peaks, durationS }, error: null });
      } catch {
        if (!cancelled) {
          setState({
            status: "error",
            audio: null,
            error: "Could not load the exported audio file.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return state;
}

function computePeaks(buffer: AudioBuffer, count: number): number[] {
  const data = buffer.getChannelData(0);
  const block = Math.max(1, Math.floor(data.length / count));
  const peaks: number[] = [];
  let max = 0;
  for (let i = 0; i < count; i += 1) {
    let peak = 0;
    const start = i * block;
    for (let j = start; j < Math.min(start + block, data.length); j += 16) {
      const v = Math.abs(data[j]);
      if (v > peak) peak = v;
    }
    peaks.push(peak);
    if (peak > max) max = peak;
  }
  return max > 0 ? peaks.map((p) => p / max) : peaks;
}
