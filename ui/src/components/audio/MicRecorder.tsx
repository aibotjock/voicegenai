import { useEffect, useRef, useState } from "react";
import { Circle, Mic, Pause, Play, RotateCcw, Square } from "lucide-react";
import { formatDuration } from "../../lib/format";
import { Button } from "../ui/Button";
import { useMicRecorder, type RecordedTake } from "./useMicRecorder";
import "./audio.css";

interface MicRecorderProps {
  /** Called when the user submits a finished take. */
  onSubmit: (take: RecordedTake) => void;
  submitting?: boolean;
  /** Minimum recommended length, shown as guidance. */
  recommendedSeconds?: number;
}

/**
 * Professional mic capture: device picker, live input level, timer,
 * record / pause / stop, take playback, re-record, submit.
 */
export function MicRecorder({
  onSubmit,
  submitting = false,
  recommendedSeconds = 30,
}: MicRecorderProps) {
  const rec = useMicRecorder();
  const [deviceId, setDeviceId] = useState<string>("");
  const [playingTake, setPlayingTake] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const levelBars = 5;

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  const toggleTakePlayback = () => {
    if (!rec.take) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(rec.take.url);
      audioRef.current.onended = () => setPlayingTake(false);
    }
    if (playingTake) {
      audioRef.current.pause();
      setPlayingTake(false);
    } else {
      void audioRef.current.play();
      setPlayingTake(true);
    }
  };

  const rerecord = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    setPlayingTake(false);
    rec.discard();
  };

  return (
    <div className="recorder">
      <div className="recorder-top">
        {rec.devices.length > 1 ? (
          <select
            className="select recorder-device"
            aria-label="Microphone"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            disabled={rec.state === "recording" || rec.state === "paused"}
          >
            <option value="">Default microphone</option>
            {rec.devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="recorder-device-label">
            <Mic size={14} aria-hidden="true" /> Microphone
          </span>
        )}
        <span
          className="recorder-timer"
          role="timer"
          aria-label={`Recording time ${formatDuration(rec.elapsed)}`}
        >
          {formatDuration(rec.elapsed)}
        </span>
      </div>

      {/* live input level */}
      <div
        className="level-meter"
        aria-hidden={rec.state !== "recording" && rec.state !== "paused"}
        role="meter"
        aria-label="Input level"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(rec.level * 100)}
      >
        {Array.from({ length: levelBars }, (_, i) => {
          const threshold = (i + 1) / levelBars;
          return (
            <span
              key={i}
              className={
                rec.level >= threshold * 0.7
                  ? i >= levelBars - 1
                    ? "level-bar level-hot"
                    : "level-bar level-on"
                  : "level-bar"
              }
            />
          );
        })}
      </div>

      <p className="recorder-hint">
        {rec.state === "idle" &&
          `Record at least ${formatDuration(recommendedSeconds)} of natural speech. Speak like you would for your audience.`}
        {rec.state === "recording" &&
          (rec.elapsed < recommendedSeconds
            ? `Recording… keep going for ${formatDuration(Math.max(0, recommendedSeconds - rec.elapsed))} more.`
            : "Recording… that's long enough — you can stop when ready.")}
        {rec.state === "paused" && "Paused."}
        {rec.state === "stopped" && "Listen back, then use this recording or record again."}
      </p>

      {rec.error ? <p className="recorder-error">{rec.error}</p> : null}

      <div className="recorder-actions">
        {rec.state === "idle" && (
          <Button
            variant="primary"
            onClick={() => void rec.start(deviceId || undefined)}
          >
            <Circle size={12} fill="currentColor" aria-hidden="true" />
            Start recording
          </Button>
        )}
        {rec.state === "recording" && (
          <>
            <Button variant="secondary" onClick={rec.pause}>
              <Pause size={14} aria-hidden="true" /> Pause
            </Button>
            <Button variant="primary" onClick={rec.stop}>
              <Square size={12} fill="currentColor" aria-hidden="true" /> Stop
            </Button>
          </>
        )}
        {rec.state === "paused" && (
          <>
            <Button variant="secondary" onClick={rec.resume}>
              <Circle size={12} fill="currentColor" aria-hidden="true" /> Resume
            </Button>
            <Button variant="primary" onClick={rec.stop}>
              <Square size={12} fill="currentColor" aria-hidden="true" /> Stop
            </Button>
          </>
        )}
        {rec.state === "stopped" && rec.take && (
          <>
            <Button variant="secondary" onClick={toggleTakePlayback}>
              {playingTake ? (
                <Pause size={14} aria-hidden="true" />
              ) : (
                <Play size={14} aria-hidden="true" />
              )}
              {playingTake ? "Pause" : "Play back"}
            </Button>
            <Button variant="ghost" onClick={rerecord} disabled={submitting}>
              <RotateCcw size={14} aria-hidden="true" /> Re-record
            </Button>
            <Button
              variant="primary"
              onClick={() => onSubmit(rec.take!)}
              disabled={submitting}
            >
              {submitting ? "Checking recording…" : "Use this recording"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
