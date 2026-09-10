import { useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, Volume2 } from "lucide-react";
import { formatDuration } from "../../lib/format";
import { Waveform } from "./Waveform";
import "./audio.css";

interface AudioPlayerProps {
  /** Object URL for the audio. */
  src: string;
  /** Decoded peaks for the waveform; empty array → plain scrubber look. */
  peaks?: number[];
  /** Decoded duration (more exact than metadata); optional. */
  durationS?: number | null;
  title?: string;
}

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

/**
 * Integrated player: play/pause, waveform scrub, time, volume, speed,
 * restart. Never autoplays.
 */
export function AudioPlayer({ src, peaks = [], durationS, title }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    const audio = new Audio();
    audio.src = src;
    audio.preload = "auto";
    audioRef.current = audio;
    setPlaying(false);
    setTime(0);

    const onTime = () => setTime(audio.currentTime);
    const onMeta = () => setDuration(audio.duration || 0);
    const onEnd = () => setPlaying(false);
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("ended", onEnd);
    return () => {
      audio.pause();
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("ended", onEnd);
      audioRef.current = null;
    };
  }, [src]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed;
  }, [speed]);

  const total = durationS ?? duration;
  const progress = total > 0 ? time / total : 0;

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      void audio.play();
      setPlaying(true);
    }
  };

  const seek = (ratio: number) => {
    const audio = audioRef.current;
    if (!audio || total <= 0) return;
    audio.currentTime = ratio * total;
    setTime(audio.currentTime);
  };

  const restart = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    setTime(0);
  };

  return (
    <div className="player" aria-label={title ? `Audio player: ${title}` : "Audio player"}>
      {title ? <p className="player-title">{title}</p> : null}
      <div className="player-main">
        <button
          type="button"
          className="player-play"
          onClick={toggle}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <Pause size={18} fill="currentColor" aria-hidden="true" />
          ) : (
            <Play size={18} fill="currentColor" aria-hidden="true" />
          )}
        </button>
        <div className="player-track">
          <Waveform peaks={peaks} progress={progress} onSeek={seek} />
          <div className="player-times">
            <span>{formatDuration(time)}</span>
            <span>{formatDuration(total)}</span>
          </div>
        </div>
        <div className="player-side">
          <button
            type="button"
            className="btn btn-icon"
            onClick={restart}
            aria-label="Restart"
            title="Restart"
          >
            <RotateCcw size={15} aria-hidden="true" />
          </button>
          <label className="sr-only" htmlFor="player-speed">
            Playback speed
          </label>
          <select
            id="player-speed"
            className="select player-speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          <Volume2 size={16} aria-hidden="true" style={{ color: "var(--text-3)" }} />
          <label className="sr-only" htmlFor="player-volume">
            Volume
          </label>
          <input
            id="player-volume"
            className="slider player-volume"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
          />
        </div>
      </div>
    </div>
  );
}
