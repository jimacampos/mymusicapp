import { PlaylistSummary } from "../api";

interface Props {
  playlists: PlaylistSummary[];
  onOpen: (id: number) => void;
  onCreate: () => void;
  onDelete: (playlist: PlaylistSummary) => void;
}

export function Playlists({ playlists, onOpen, onCreate, onDelete }: Props) {
  return (
    <div className="playlists-view">
      <div className="playlists-header">
        <h1>Playlists</h1>
        <button className="play-all" onClick={onCreate}>
          + New playlist
        </button>
      </div>
      {playlists.length === 0 ? (
        <div className="empty">
          <p>No playlists yet. Create one, then add tracks with the “⋯” menu.</p>
        </div>
      ) : (
        <ul className="playlist-list">
          {playlists.map((pl) => (
            <li key={pl.id} className="playlist-row">
              <button className="playlist-open" onClick={() => onOpen(pl.id)}>
                <span className="playlist-icon">≣</span>
                <span className="playlist-meta">
                  <span className="playlist-name">{pl.name}</span>
                  <span className="playlist-count">
                    {pl.track_count} track{pl.track_count === 1 ? "" : "s"}
                  </span>
                </span>
              </button>
              <button
                className="icon-btn"
                title="Delete playlist"
                onClick={() => onDelete(pl)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
