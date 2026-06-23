import { AlbumSummary, api } from "../api";

interface Props {
  albums: AlbumSummary[];
  onOpen: (id: number) => void;
}

export function Library({ albums, onOpen }: Props) {
  if (albums.length === 0) {
    return (
      <div className="empty">
        <h2>No albums yet</h2>
        <p>
          Point the scanner at your music folder:
          <br />
          <code>MUSIC_DIR=/path/to/music python scanner.py</code>
          <br />
          then hit <strong>Rescan</strong>.
        </p>
      </div>
    );
  }
  return (
    <div className="album-grid">
      {albums.map((a) => (
        <button key={a.id} className="album-card" onClick={() => onOpen(a.id)}>
          <div className="cover-wrap">
            {a.has_cover ? (
              <img
                src={api.coverUrl(a.id)}
                alt={a.title}
                loading="lazy"
                onError={(e) => (e.currentTarget.style.visibility = "hidden")}
              />
            ) : (
              <div className="cover placeholder">♪</div>
            )}
          </div>
          <div className="album-title">{a.title}</div>
          <div className="album-artist">{a.artist}</div>
          <div className="album-meta">
            {a.year ? `${a.year} · ` : ""}
            {a.track_count} track{a.track_count === 1 ? "" : "s"}
          </div>
        </button>
      ))}
    </div>
  );
}
