import { useEffect } from "react";
import { usePlayer } from "../player";
import { api } from "../api";
import { formatTime } from "../format";
import {
  PlayIcon,
  PauseIcon,
  PrevIcon,
  NextIcon,
  VolumeIcon,
} from "./Icons";

export function Player() {
  const p = usePlayer();

  // Keyboard shortcuts: space = play/pause, arrows = seek/skip.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.code === "Space") {
        e.preventDefault();
        p.toggle();
      } else if (e.code === "ArrowRight" && e.shiftKey) {
        p.next();
      } else if (e.code === "ArrowLeft" && e.shiftKey) {
        p.prev();
      } else if (e.code === "ArrowRight") {
        p.seek(Math.min(p.currentTime + 5, p.duration));
      } else if (e.code === "ArrowLeft") {
        p.seek(Math.max(p.currentTime - 5, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [p]);

  const t = p.current;

  return (
    <footer className="player">
      <div className="player-info">
        {t && t.album_id != null ? (
          <img
            className="player-cover"
            src={api.coverUrl(t.album_id)}
            alt=""
            onError={(e) => (e.currentTarget.style.visibility = "hidden")}
          />
        ) : (
          <div className="player-cover placeholder" />
        )}
        <div className="player-meta">
          <div className="player-title">{t ? t.title : "Nothing playing"}</div>
          <div className="player-sub">
            {t ? `${t.artist ?? "Unknown"} — ${t.album ?? ""}` : ""}
          </div>
        </div>
      </div>

      <div className="player-center">
        <div className="player-controls">
          <button onClick={p.prev} disabled={!t} title="Previous (Shift+←)">
            <PrevIcon />
          </button>
          <button
            className="play-btn"
            onClick={p.toggle}
            disabled={!t}
            title="Play/Pause (Space)"
          >
            {p.isPlaying ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
          </button>
          <button onClick={p.next} disabled={!t} title="Next (Shift+→)">
            <NextIcon />
          </button>
        </div>
        <div className="seek-row">
          <span className="time">{formatTime(p.currentTime)}</span>
          <input
            className="seek"
            type="range"
            min={0}
            max={p.duration || 0}
            step={0.1}
            value={p.currentTime}
            disabled={!t}
            onChange={(e) => p.seek(Number(e.target.value))}
          />
          <span className="time">{formatTime(p.duration)}</span>
        </div>
      </div>

      <div className="player-volume">
        <span title="Volume" className="vol-icon">
          <VolumeIcon size={18} />
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={p.volume}
          onChange={(e) => p.setVolume(Number(e.target.value))}
        />
      </div>
    </footer>
  );
}
