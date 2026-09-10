/**
 * Microphone capture as raw PCM → WAV.
 *
 * Uses AudioContext + ScriptProcessor for broad webview support (incl.
 * WebKitGTK) and encodes a 16-bit mono WAV client-side, so the backend
 * always receives a container it can read regardless of MediaRecorder
 * codec availability.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { concatPcm, encodeWavPcm16 } from "../../lib/wav";

export type RecorderState = "idle" | "recording" | "paused" | "stopped";

export interface MicDevice {
  deviceId: string;
  label: string;
}

export interface RecordedTake {
  blob: Blob;
  url: string;
  durationS: number;
}

export function useMicRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [take, setTake] = useState<RecordedTake | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState<MicDevice[]>([]);

  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const pausedRef = useRef(false);
  const accumulatedRef = useRef(0);
  const rafRef = useRef(0);

  const refreshDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setDevices(
        all
          .filter((d) => d.kind === "audioinput")
          .map((d, i) => ({
            deviceId: d.deviceId,
            label: d.label || `Microphone ${i + 1}`,
          })),
      );
    } catch {
      /* device listing is best-effort */
    }
  }, []);

  useEffect(() => {
    void refreshDevices();
  }, [refreshDevices]);

  const teardown = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
  }, []);

  useEffect(() => teardown, [teardown]);

  const start = useCallback(
    async (deviceId?: string) => {
      setError(null);
      setTake(null);
      chunksRef.current = [];
      accumulatedRef.current = 0;
      pausedRef.current = false;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            deviceId: deviceId ? { exact: deviceId } : undefined,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: false,
          },
        });
        streamRef.current = stream;
        const ctx = new AudioContext();
        ctxRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        source.connect(analyser);
        analyser.connect(processor);
        processor.connect(ctx.destination);
        processor.onaudioprocess = (e) => {
          if (pausedRef.current) return;
          const input = e.inputBuffer.getChannelData(0);
          chunksRef.current.push(new Float32Array(input));
          accumulatedRef.current += input.length;
        };

        setState("recording");
        // Device labels only appear after mic permission is granted.
        void refreshDevices();

        const levelData = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (ctxRef.current !== ctx) return;
          analyser.getByteTimeDomainData(levelData);
          let peak = 0;
          for (let i = 0; i < levelData.length; i += 1) {
                const v = Math.abs(levelData[i] - 128) / 128;
            if (v > peak) peak = v;
          }
          setLevel(peak);
          // Elapsed = recorded audio duration; pauses naturally don't count.
          setElapsed(accumulatedRef.current / ctx.sampleRate);
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (err) {
        setError(
          err instanceof DOMException && err.name === "NotAllowedError"
            ? "Microphone access was denied. Allow microphone access to record."
            : "Could not start the microphone. Check that one is connected.",
        );
        teardown();
      }
    },
    [refreshDevices, teardown],
  );

  const pause = useCallback(() => {
    pausedRef.current = true;
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    pausedRef.current = false;
    setState("recording");
  }, []);

  const stop = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const total = accumulatedRef.current;
    const pcm = concatPcm(chunksRef.current, total);
    const wav = encodeWavPcm16(pcm, ctx.sampleRate);
    const blob = new Blob([wav], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    const durationS = total / ctx.sampleRate;
    teardown();
    setLevel(0);
    setElapsed(durationS);
    setTake({ blob, url, durationS });
    setState("stopped");
  }, [teardown]);

  const discard = useCallback(() => {
    if (take) URL.revokeObjectURL(take.url);
    setTake(null);
    setElapsed(0);
    setState("idle");
  }, [take]);

  return {
    state,
    elapsed,
    level,
    take,
    error,
    devices,
    start,
    pause,
    resume,
    stop,
    discard,
  };
}
