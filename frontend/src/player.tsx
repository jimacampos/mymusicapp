import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  ReactNode,
} from "react";
import { Track, api } from "./api";

interface PlayerState {
  current: Track | null;
  queue: Track[];
  index: number;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  playQueue: (tracks: Track[], startIndex: number) => void;
  toggle: () => void;
  next: () => void;
  prev: () => void;
  seek: (time: number) => void;
  setVolume: (v: number) => void;
}

const PlayerContext = createContext<PlayerState | null>(null);

const VOL_KEY = "mymusic.volume";
const LAST_KEY = "mymusic.lastTrack";

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  if (audioRef.current === null) {
    audioRef.current = new Audio();
  }
  const audio = audioRef.current;

  const [queue, setQueue] = useState<Track[]>([]);
  const [index, setIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolumeState] = useState<number>(() => {
    const saved = localStorage.getItem(VOL_KEY);
    return saved !== null ? Number(saved) : 1;
  });

  const current = index >= 0 && index < queue.length ? queue[index] : null;

  // Wire up audio element event listeners once.
  useEffect(() => {
    const onTime = () => {
      setCurrentTime(audio.currentTime);
      if (
        "mediaSession" in navigator &&
        "setPositionState" in navigator.mediaSession
      ) {
        const d = audio.duration;
        if (Number.isFinite(d) && d > 0) {
          try {
            navigator.mediaSession.setPositionState({
              duration: d,
              position: Math.min(audio.currentTime, d),
              playbackRate: audio.playbackRate || 1,
            });
          } catch {
            /* ignore */
          }
        }
      }
    };
    const onDuration = () => setDuration(audio.duration || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => nextRef.current();
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("loadedmetadata", onDuration);
    audio.addEventListener("durationchange", onDuration);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("loadedmetadata", onDuration);
      audio.removeEventListener("durationchange", onDuration);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, [audio]);

  useEffect(() => {
    audio.volume = volume;
    localStorage.setItem(VOL_KEY, String(volume));
  }, [volume, audio]);

  const playIndex = useCallback(
    (tracks: Track[], i: number) => {
      const t = tracks[i];
      if (!t) return;
      audio.src = api.streamUrl(t.id);
      audio.play().catch(() => undefined);
      localStorage.setItem(LAST_KEY, String(t.id));
    },
    [audio]
  );

  const playQueue = useCallback(
    (tracks: Track[], startIndex: number) => {
      setQueue(tracks);
      setIndex(startIndex);
      playIndex(tracks, startIndex);
    },
    [playIndex]
  );

  const toggle = useCallback(() => {
    if (!current) return;
    if (audio.paused) audio.play().catch(() => undefined);
    else audio.pause();
  }, [audio, current]);

  const next = useCallback(() => {
    setIndex((i) => {
      const ni = i + 1;
      if (ni < queue.length) {
        playIndex(queue, ni);
        return ni;
      }
      audio.pause();
      return i;
    });
  }, [queue, playIndex, audio]);

  const prev = useCallback(() => {
    // If more than 3s in, restart the track instead of going back.
    if (audio.currentTime > 3) {
      audio.currentTime = 0;
      return;
    }
    setIndex((i) => {
      const pi = i - 1;
      if (pi >= 0) {
        playIndex(queue, pi);
        return pi;
      }
      audio.currentTime = 0;
      return i;
    });
  }, [queue, playIndex, audio]);

  // Keep a ref to `next` so the 'ended' listener always calls the latest.
  const nextRef = useRef(next);
  useEffect(() => {
    nextRef.current = next;
  }, [next]);

  const seek = useCallback(
    (time: number) => {
      audio.currentTime = time;
      setCurrentTime(time);
    },
    [audio]
  );

  const setVolume = useCallback((v: number) => {
    setVolumeState(Math.min(1, Math.max(0, v)));
  }, []);

  // iOS lock screen / Control Center integration (Media Session API).
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => audio.play().catch(() => undefined)],
      ["pause", () => audio.pause()],
      ["previoustrack", () => prev()],
      ["nexttrack", () => next()],
      [
        "seekto",
        (d) => {
          if (d.seekTime != null) seek(d.seekTime);
        },
      ],
      [
        "seekbackward",
        (d) => seek(Math.max(0, audio.currentTime - (d.seekOffset || 10))),
      ],
      [
        "seekforward",
        (d) =>
          seek(
            Math.min(audio.duration || 0, audio.currentTime + (d.seekOffset || 10))
          ),
      ],
    ];
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler);
      } catch {
        /* unsupported action */
      }
    }
    return () => {
      for (const [action] of handlers) {
        try {
          ms.setActionHandler(action, null);
        } catch {
          /* ignore */
        }
      }
    };
  }, [audio, next, prev, seek]);

  // Keep lock screen metadata (title/artist/album/artwork) in sync.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    if (!current) {
      navigator.mediaSession.metadata = null;
      return;
    }
    const artwork =
      current.album_id != null
        ? [
            {
              src: window.location.origin + api.coverUrl(current.album_id),
              sizes: "512x512",
              type: "image/jpeg",
            },
          ]
        : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: current.title || "Unknown",
      artist: current.artist || "Unknown",
      album: current.album || "",
      artwork,
    });
  }, [current]);

  // Reflect play/pause state on the lock screen.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.playbackState = current
      ? isPlaying
        ? "playing"
        : "paused"
      : "none";
  }, [isPlaying, current]);

  const value = useMemo<PlayerState>(
    () => ({
      current,
      queue,
      index,
      isPlaying,
      currentTime,
      duration,
      volume,
      playQueue,
      toggle,
      next,
      prev,
      seek,
      setVolume,
    }),
    [
      current,
      queue,
      index,
      isPlaying,
      currentTime,
      duration,
      volume,
      playQueue,
      toggle,
      next,
      prev,
      seek,
      setVolume,
    ]
  );

  return (
    <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>
  );
}

export function usePlayer(): PlayerState {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
