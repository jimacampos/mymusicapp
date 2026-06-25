import { useEffect, useRef, useState } from "react";
import { PlaylistSummary, Track, api } from "../api";

interface Props {
  track: Track;
  playlists: PlaylistSummary[];
  onClose: () => void;
  onChanged: () => void;
}

export function AddToPlaylistMenu({
  track,
  playlists,
  onClose,
  onChanged,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const add = async (playlistId: number) => {
    if (busy) return;
    setBusy(true);
    try {
      await api.addToPlaylist(playlistId, track.id);
      onChanged();
      onClose();
    } catch (e) {
      alert("Could not add to playlist: " + e);
    } finally {
      setBusy(false);
    }
  };

  const createAndAdd = async () => {
    const name = window.prompt("New playlist name");
    if (!name || !name.trim()) return;
    setBusy(true);
    try {
      const pl = await api.createPlaylist(name.trim());
      await api.addToPlaylist(pl.id, track.id);
      onChanged();
      onClose();
    } catch (e) {
      alert("Could not create playlist: " + e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ctx-menu" ref={ref} role="menu">
      <div className="ctx-menu-head">Add to playlist</div>
      <button className="ctx-item" onClick={createAndAdd} disabled={busy}>
        + New playlist…
      </button>
      {playlists.length > 0 && <div className="ctx-sep" />}
      {playlists.map((pl) => (
        <button
          key={pl.id}
          className="ctx-item"
          onClick={() => add(pl.id)}
          disabled={busy}
        >
          {pl.name}
        </button>
      ))}
    </div>
  );
}
