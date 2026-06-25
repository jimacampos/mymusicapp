import { useEffect, useState } from "react";
import { AlbumDetail, PlaylistSummary, api } from "../api";
import { TrackList } from "../components/TrackList";
import { usePlayer } from "../player";

interface Props {
  albumId: number;
  playlists: PlaylistSummary[];
  onPlaylistsChanged: () => void;
  onBack: () => void;
}

export function Album({ albumId, playlists, onPlaylistsChanged, onBack }: Props) {
  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = usePlayer();

  useEffect(() => {
    setAlbum(null);
    setError(null);
    api
      .album(albumId)
      .then(setAlbum)
      .catch((e) => setError(String(e)));
  }, [albumId]);

  if (error) return <div className="empty">Failed to load album: {error}</div>;
  if (!album) return <div className="empty">Loading…</div>;

  return (
    <div className="album-detail">
      <button className="back" onClick={onBack}>
        ← Back
      </button>
      <div className="album-header">
        {album.has_cover ? (
          <img className="album-hero" src={api.coverUrl(album.id)} alt="" />
        ) : (
          <div className="album-hero placeholder">♪</div>
        )}
        <div className="album-header-info">
          <div className="eyebrow">Album</div>
          <h1>{album.title}</h1>
          <div className="album-sub">
            {album.artist}
            {album.year ? ` · ${album.year}` : ""} · {album.tracks.length} tracks
          </div>
          <button
            className="play-all"
            onClick={() => p.playQueue(album.tracks, 0)}
            disabled={album.tracks.length === 0}
          >
            ▶ Play
          </button>
        </div>
      </div>
      <TrackList
        tracks={album.tracks}
        playlists={playlists}
        onPlaylistsChanged={onPlaylistsChanged}
      />
    </div>
  );
}
