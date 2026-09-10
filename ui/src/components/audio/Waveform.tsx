import { useEffect, useRef } from "react";

interface WaveformProps {
  /** Normalized peaks 0..1, one per visual bar. */
  peaks: number[];
  /** Played fraction 0..1 — bars left of it are accented. */
  progress: number;
  onSeek?: (ratio: number) => void;
}

/**
 * Canvas waveform: decoded peaks, played region in accent, click/drag seek.
 * Lightweight — no animation loop, redraws only when inputs change.
 */
export function Waveform({ peaks, progress, onSeek }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(width * dpr));
    canvas.height = Math.max(1, Math.round(height * dpr));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const styles = getComputedStyle(canvas);
    const accent = styles.getPropertyValue("--accent").trim() || "#0b7285";
    const rest = styles.getPropertyValue("--border-strong").trim() || "#999";

    ctx.clearRect(0, 0, width, height);
    const n = peaks.length;
    if (n === 0) return;
    const barW = Math.max(2, Math.floor(width / n) - 1);
    const gap = 1;
    const mid = height / 2;
    for (let i = 0; i < n; i += 1) {
      const x = i * (barW + gap);
      if (x > width) break;
      const h = Math.max(2, peaks[i] * (height - 4));
      ctx.fillStyle = i / n <= progress ? accent : rest;
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") ctx.roundRect(x, mid - h / 2, barW, h, 2);
      else ctx.rect(x, mid - h / 2, barW, h);
      ctx.fill();
    }
  }, [peaks, progress]);

  const seekFromEvent = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onSeek) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    onSeek(Math.max(0, Math.min(1, ratio)));
  };

  return (
    <canvas
      ref={canvasRef}
      className="waveform"
      role="slider"
      aria-label="Seek in audio"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
      tabIndex={0}
      onMouseDown={(e) => {
        seekFromEvent(e);
        const onMove = (ev: MouseEvent) => {
          const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect();
          onSeek?.(Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width)));
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      }}
      onKeyDown={(e) => {
        if (!onSeek) return;
        if (e.key === "ArrowRight") onSeek(Math.min(1, progress + 0.02));
        if (e.key === "ArrowLeft") onSeek(Math.max(0, progress - 0.02));
      }}
    />
  );
}
