import { useCallback, useEffect, useState } from "react";
import { PlaylistDetail, PlaylistSummary, Track, api } from "../api";
import { TrackList } from "../components/TrackList";
import { usePlayer } from "../player";

interface Props {
  playlistId: number;
  playlists: PlaylistSummary[];
  onBack: () => void;
  onChanged: () => void;
}

export function Playlist({ playlistId, playlists, onBack, onChanged }: Props) {
  const [playlist, setPlaylist] = useState<PlaylistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = usePlayer();

  const load = useCallback(() => {
    api
      .playlist(playlistId)
      .then(setPlaylist)
      .catch((e) => setError(String(e)));
  }, [playlistId]);

  useEffect(() => {
    setPlaylist(null);
    setError(null);
    load();
  }, [load]);

  const rename = async () => {
    if (!playlist) return;
    const name = window.prompt("Rename playlist", playlist.name);
    if (!name || !name.trim() || name.trim() === playlist.name) return;
    try {
      const updated = await api.renamePlaylist(playlist.id, name.trim());
      setPlaylist(updated);
      onChanged();
    } catch (e) {
      alert("Rename failed: " + e);
    }
  };

  const remove = async (track: Track) => {
    if (!playlist) return;
    try {
      const updated = await api.removeFromPlaylist(playlist.id, track.id);
      setPlaylist(updated);
      onChanged();
    } catch (e) {
      alert("Could not remove track: " + e);
    }
  };

  const move = async (index: number, dir: -1 | 1) => {
    if (!playlist) return;
    const target = index + dir;
    if (target < 0 || target >= playlist.tracks.length) return;
    const ids = playlist.tracks.map((t) => t.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    // Optimistic reorder for snappy UI.
    const reordered = ids.map((id) => playlist.tracks.find((t) => t.id === id)!);
    setPlaylist({ ...playlist, tracks: reordered });
    try {
      const updated = await api.reorderPlaylist(playlist.id, ids);
      setPlaylist(updated);
      onChanged();
    } catch (e) {
      alert("Reorder failed: " + e);
      load();
    }
  };

  if (error) return <div className="empty">Failed to load playlist: {error}</div>;
  if (!playlist) return <div className="empty">Loading…</div>;

  return (
    <div className="album-detail">
      <button className="back" onClick={onBack}>
        ← Back
      </button>
      <div className="album-header">
        <div className="album-hero placeholder">≣</div>
        <div className="album-header-info">
          <div className="eyebrow">Playlist</div>
          <h1 className="playlist-title" onClick={rename} title="Click to rename">
            {playlist.name}
          </h1>
          <div className="album-sub">
            {playlist.tracks.length} track
            {playlist.tracks.length === 1 ? "" : "s"}
          </div>
          <div className="header-actions">
            <button
              className="play-all"
              onClick={() => p.playQueue(playlist.tracks, 0)}
              disabled={playlist.tracks.length === 0}
            >
              ▶ Play
            </button>
            <button className="secondary-btn" onClick={rename}>
              Rename
            </button>
          </div>
        </div>
      </div>
      {playlist.tracks.length === 0 ? (
        <div className="empty">
          <p>This playlist is empty. Add tracks with the “⋯” menu.</p>
        </div>
      ) : (
        <TrackList
          tracks={playlist.tracks}
          showAlbum
          playlists={playlists}
          onPlaylistsChanged={onChanged}
          onRemove={remove}
          onMove={move}
        />
      )}
    </div>
  );
}
